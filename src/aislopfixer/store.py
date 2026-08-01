"""Per-project memory under ``<root>/.aislopfixer/``.

Small on purpose. The old store existed to suppress individual findings the
user had already dealt with; a design report has nothing to suppress — it is a
measurement, and hiding part of a measurement makes the number wrong. What is
worth remembering instead is what the *user decided*:

* ``state.json`` — which archetype this project settled on, which observations
  the user has said they are living with, and the score history so a run can be
  compared with the last one.
* ``report.md`` — a readable snapshot, so the numbers can be diffed across
  commits without opening the TUI.

The system stylesheet the transformer emits lives in the same folder, which is
also why the folder is dot-prefixed: the scanner's walk skips it, so the tool
never measures its own output.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .design.models import Axis, DesignReport

DIRNAME = ".aislopfixer"
STATE = "state.json"
REPORT = "report.md"
_HISTORY_KEEP = 40


class Store:
    """Reads and writes one project's ``.aislopfixer`` folder."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.dir = self.root / DIRNAME
        self._state: dict = {}
        self._load()

    # ------------------------------------------------------------------ state
    def _load(self) -> None:
        try:
            loaded = json.loads((self.dir / STATE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        self._state = loaded if isinstance(loaded, dict) else {}

    def _save(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / STATE).write_text(
                json.dumps(self._state, indent=2, ensure_ascii=False),
                encoding="utf-8", newline="\n",
            )
        except OSError:
            pass

    @property
    def archetype(self) -> str | None:
        value = self._state.get("archetype")
        return value if isinstance(value, str) else None

    def set_archetype(self, key: str) -> None:
        self._state["archetype"] = key
        self._save()

    @property
    def applied_axes(self) -> set[str]:
        """Axis ids this project has already had the transform applied for.

        Remembered so a second run opens on the work that is left rather than
        on everything again: the usual first step is "take the colours, leave
        the layout alone", and the usual second step is the rest of it.
        """
        value = self._state.get("applied_axes", [])
        return {v for v in value if isinstance(v, str)} if isinstance(value, list) else set()

    def add_applied_axes(self, axes) -> None:
        self._state["applied_axes"] = sorted(self.applied_axes | set(axes))
        self._save()

    def clear_applied_axes(self) -> None:
        """After an undo there is nothing applied to resume from."""
        self._state["applied_axes"] = []
        self._save()

    @property
    def accepted(self) -> set[str]:
        """Observation keys the user has chosen to live with."""
        value = self._state.get("accepted", [])
        return set(value) if isinstance(value, list) else set()

    def toggle_accepted(self, key: str) -> bool:
        """Flip one observation's accepted flag; returns the new state."""
        acc = self.accepted
        now = key not in acc
        acc.add(key) if now else acc.discard(key)
        self._state["accepted"] = sorted(acc)
        self._save()
        return now

    def record_run(self, report: DesignReport, applied: int = 0) -> None:
        """Append this run's headline numbers to the history."""
        history = self.history
        history.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "decisions": report.decision_density,
            "repetition": report.repetition,
            "template": report.template_score,
            "edits": applied,
        })
        self._state["history"] = history[-_HISTORY_KEEP:]
        self._save()

    @property
    def history(self) -> list[dict]:
        value = self._state.get("history", [])
        return list(value) if isinstance(value, list) else []

    @property
    def previous(self) -> dict | None:
        """The last recorded run, for a before/after line in the report."""
        history = self.history
        return history[-1] if history else None

    # ----------------------------------------------------------------- report
    def write_report(self, report: DesignReport, system=None) -> str | None:
        """Write ``report.md``; returns the path, or ``None`` on failure."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / REPORT
            path.write_text(render_report(report, system), encoding="utf-8",
                            newline="\n")
            return str(path)
        except OSError:
            return None


def render_report(report: DesignReport, system=None) -> str:
    """The markdown snapshot written after each run."""
    lines = [
        "# Tasarım raporu",
        "",
        f"_{datetime.now().strftime('%Y-%m-%d %H:%M')} · {report.root}_",
        "",
        f"**Şablon skoru: {report.template_score:.0f}/100** — {report.verdict}",
        "",
        f"- Karar yoğunluğu: **{report.decision_density:.0f}**/100",
        f"- Tekrar: **{report.repetition:.0f}**/100",
        f"- {report.files_scanned} dosya · {report.elements} eleman",
        "",
        "## Eksenler",
        "",
        "| Eksen | Karar | Tekrar | Varsayılan | Hüküm |",
        "|---|---:|---:|---:|---|",
    ]
    for axis in Axis:
        score = report.axes.get(axis)
        if score is None or not score.measured:
            lines.append(f"| {axis.label} | — | — | — | kullanılmıyor |")
            continue
        lines.append(
            f"| {axis.label} | {score.decision_score:.0f} | "
            f"{score.repetition:.0f} | %{score.default_share * 100:.0f} | "
            f"{score.verdict} |"
        )

    if system is not None:
        lines += ["", "## Türetilen sistem", ""]
        lines += [f"- **{label}:** {value}" for label, value in system.summary()]

    lines += ["", "## Gözlemler", ""]
    if not report.observations:
        lines.append("_Yok._")
    for obs in report.observations:
        lines += [
            f"### {obs.title}  ·  `{obs.id}`  ·  {obs.stat}",
            "",
            obs.detail,
            "",
        ]
        if obs.evidence:
            lines.append("Kanıt:")
            lines += [f"- `{e.file}:{e.line}` — {e.snippet[:110]}"
                      for e in obs.evidence[:6]]
            lines.append("")
        if obs.prescription:
            lines += [f"**Yapılacak:** {obs.prescription}", ""]
    return "\n".join(lines) + "\n"
