"""Per-project persistence under ``<root>/.aislopfixer/``.

A scanned project grows a small ``.aislopfixer`` folder that remembers what the
user already dealt with, so re-running the tool does not nag about the same
things twice:

* ``allowlist.json`` — signatures the user marked "not slop" (see
  :mod:`aislopfixer.allowlist`).
* ``ledger.json`` — every finding the user resolved (fixed / annotated / ignored)
  or skipped, with its signature, location, status and timestamp.
* ``report.md`` — a human-readable snapshot of the latest scan and what happened
  to each finding.

On the next scan, :meth:`Store.filter` drops anything in the allowlist *and*
anything the ledger records as already resolved. Skipped findings are recorded
for the report but intentionally re-surface — "skip" means "later", not "never".

The folder is hidden (dot-prefixed), so the scanner's own walk skips it and the
report/ledger are never themselves scanned.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .allowlist import Allowlist
from .engine.models import Category, Finding, Status
from .engine.scoring import project_score_from_findings

DIRNAME = ".aislopfixer"
LEDGER = "ledger.json"
REPORT = "report.md"

# Statuses whose findings must NOT come back on the next scan.
_SUPPRESS = {Status.FIXED.value, Status.ANNOTATED.value, Status.IGNORED.value}

_STATUS_ICON = {
    Status.FIXED.value: "✓",
    Status.ANNOTATED.value: "✎",
    Status.IGNORED.value: "⊘",
    Status.SKIPPED.value: "→",
    Status.OPEN.value: "▲",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """Owns the project's ``.aislopfixer`` folder: allowlist, ledger and report."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.dir = self.root / DIRNAME
        self.allowlist = Allowlist(root)
        self._ledger: dict[tuple[str, str, str, int], dict] = {}
        self._load_ledger()

    # ------------------------------------------------------------------- ledger
    def _load_ledger(self) -> None:
        try:
            data = json.loads((self.dir / LEDGER).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for e in data.get("entries", []):
            key = (e.get("rule_id", ""), e.get("value", ""),
                   e.get("file", ""), e.get("line", 0))
            self._ledger[key] = e

    def _save_ledger(self) -> None:
        data = {"version": 1, "entries": list(self._ledger.values())}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / LEDGER).write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    def record(self, f: Finding) -> None:
        """Persist how a finding was handled (its status drives suppression)."""
        key = (f.rule_id, f.matched_text, f.file, f.line)
        self._ledger[key] = {
            "rule_id": f.rule_id,
            "value": f.matched_text,
            "file": f.file,
            "line": f.line,
            "category": f.category.value,
            "message": f.message,
            "status": f.status.value,
            "updated": _now(),
        }
        self._save_ledger()

    def _suppressed(self) -> set[tuple[str, str, str]]:
        return {
            (e["rule_id"], e["value"], e["file"])
            for e in self._ledger.values()
            if e.get("status") in _SUPPRESS
        }

    # -------------------------------------------------------------------- query
    def filter(self, findings: list[Finding]) -> list[Finding]:
        """Drop findings the user vetted (allowlist) or already resolved (ledger)."""
        sigs = self._suppressed()
        kept = self.allowlist.filter(findings)
        return [f for f in kept if (f.rule_id, f.matched_text, f.file) not in sigs]

    # ------------------------------------------------------------------- report
    def write_report(self, findings: list[Finding], target: str | None = None) -> None:
        """Write a human-readable ``report.md`` snapshot of the scan + outcomes."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / REPORT).write_text(
                self._render_report(findings, target), encoding="utf-8"
            )
        except OSError:
            pass

    def _render_report(self, findings: list[Finding], target: str | None) -> str:
        n = len(findings)
        fixed = [f for f in findings if f.status in (Status.FIXED, Status.ANNOTATED)]
        ignored = [f for f in findings if f.status is Status.IGNORED]
        skipped = [f for f in findings if f.status is Status.SKIPPED]
        remaining = [f for f in findings if f.status is Status.OPEN]

        lines: list[str] = []
        lines.append("# AI Slop Fixer — Report")
        lines.append("")
        if target:
            lines.append(f"- **Target:** `{target}`")
        lines.append(f"- **Last scan:** {_now()}")
        lines.append(f"- **Slop score:** {round(project_score_from_findings(findings) * 100)}/100")
        lines.append(
            f"- **Found:** {n}  ·  **Resolved:** {len(fixed)}  ·  "
            f"**Not slop:** {len(ignored)}  ·  **Skipped:** {len(skipped)}  ·  "
            f"**Remaining:** {len(remaining)}"
        )
        lines.append("")

        lines.append("## By category")
        lines.append("")
        lines.append("| Category | Found | Resolved |")
        lines.append("|---|---|---|")
        for cat in Category:
            cf = [f for f in findings if f.category is cat]
            if not cf:
                continue
            cr = sum(
                1 for f in cf
                if f.status in (Status.FIXED, Status.ANNOTATED, Status.IGNORED)
            )
            lines.append(f"| {cat.value} | {len(cf)} | {cr} |")
        lines.append("")

        resolved = fixed + ignored
        if resolved:
            lines.append("## Resolved")
            lines.append("")
            for f in resolved:
                lines.append(self._report_line(f))
            lines.append("")

        if remaining:
            lines.append("## Remaining")
            lines.append("")
            for f in remaining:
                lines.append(self._report_line(f))
            lines.append("")

        if n == 0:
            lines.append("No issues found. This project is clean. ✓")
            lines.append("")

        lines.append("---")
        lines.append("_Resolved and not-slop items above are remembered; re-running "
                     "the scan will not report them again._")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _report_line(f: Finding) -> str:
        icon = _STATUS_ICON.get(f.status.value, "•")
        token = f.matched_text.strip()
        token = f" — `{token}`" if token else ""
        return f"- {icon} `{f.file}:{f.line}` — {f.rule_id} — {f.message}{token}"
