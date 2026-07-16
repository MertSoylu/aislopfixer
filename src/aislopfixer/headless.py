"""Headless (non-TUI) scan mode for CI pipelines, pre-commit hooks and scripts.

``aislopfixer <path> --check`` runs the exact same pipeline as the TUI —
including the project's ``.aislopfixer`` memory, so anything the user already
fixed or marked not-slop stays suppressed — and prints the remaining findings
as plain text, JSON or SARIF 2.1.0 (``--sarif``, for GitHub code scanning).
The exit code makes it a gate:

* ``0`` — nothing at or above the ``--fail-on`` severity;
* ``1`` — at least one finding at/above the threshold;
* ``2`` — bad invocation (path missing / not a directory).

``--fix`` additionally applies the safe automatic fixes (the same
confidence-gated set as the TUI's "fix all auto") before reporting, and
records them so future scans stay quiet about them. Fixing runs to a bounded
fixpoint: a fix can unmask a finding the removed slop was hiding, so the scan
+ fix cycle repeats (≤ :data:`MAX_FIX_PASSES`) until nothing new applies —
and every applied fix is listed line-by-line in the output.

``--prompt`` renders the remaining findings as a fix brief for an AI coding
assistant (see :mod:`aislopfixer.prompter`); combined with ``--fix`` that is
"auto-fix the safe ones, brief the agent on the rest":
``aislopfixer . --fix --prompt > fix-brief.md``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from . import __version__, fixer
from .config import Config
from .engine.models import Finding, Severity, Status
from .engine.scoring import project_score_from_findings
from .pipeline import scan_project
from .store import Store

# Keep in sync with screens/results.py — the TUI's bulk-auto-fix floor.
AUTO_FIX_FLOOR = 0.60
# Fixing can surface findings the removed slop was masking (strip an emoji
# header and a bare boilerplate heading appears). Re-scan and re-fix until no
# new automatic fix applies, bounded so a pathological cycle cannot loop.
MAX_FIX_PASSES = 3

_SEV_ORDER = {"info": 0, "warning": 1, "error": 2}

# When the output stream cannot encode our punctuation (legacy Windows
# consoles: cp1252 and narrower), degrade to ASCII lookalikes instead of
# letting `errors="replace"` pepper the report with question marks.
_ASCII_FALLBACK = str.maketrans({
    "—": "-", "–": "-", "·": "|", "…": "...",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "→": "->", "✓": "+", "⊘": "x", "▲": "!",
})


def _fit_encoding(text: str, stream: TextIO) -> str:
    """Return ``text`` as-is when the stream can encode it, else ASCII-degraded."""
    enc = getattr(stream, "encoding", None)
    if not enc:
        return text
    try:
        text.encode(enc)
    except (UnicodeEncodeError, LookupError):
        return text.translate(_ASCII_FALLBACK)
    return text


def run_check(
    path: str,
    *,
    as_json: bool = False,
    as_sarif: bool = False,
    as_prompt: bool = False,
    fix: bool = False,
    fail_on: str | None = None,
    min_confidence: float | None = None,
    use_store: bool = True,
    stream: TextIO | None = None,
) -> int:
    """Scan ``path`` headlessly; print findings; return the process exit code.

    ``fail_on`` / ``min_confidence`` left as ``None`` fall back to the
    project's ``.aislopfixer.toml``, then to ``"warning"`` / ``0.0``.
    """
    out = stream if stream is not None else sys.stdout
    # Rule messages carry non-ASCII (em-dashes, quotes); on legacy Windows
    # consoles (cp1252 & narrower) print must degrade, never crash.
    try:
        out.reconfigure(errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    target = Path(path).expanduser()
    if not target.is_dir():
        print(f"aislopfixer: not a directory: {path}", file=sys.stderr)
        return 2

    config = Config.load(str(target))
    if fail_on is None:
        fail_on = config.fail_on or "warning"
    if min_confidence is None:
        min_confidence = config.min_confidence or 0.0

    store = Store(str(target)) if use_store else None
    findings = scan_project(str(target), store=store, config=config)

    fixed: list[Finding] = []
    if fix:
        for _ in range(MAX_FIX_PASSES):
            batch = _apply_auto_fixes(findings, store)
            fixed.extend(batch)
            if not batch:
                break
            # Fixes can unmask new findings — rescan until stable (bounded).
            findings = scan_project(str(target), store=store, config=config)
        if store is not None:
            still_open = [f for f in findings if f.status is Status.OPEN]
            store.write_report(fixed + still_open, str(target))

    reported = sorted(
        (
            f for f in findings
            if f.status is Status.OPEN and f.confidence >= min_confidence
        ),
        key=lambda f: (f.file, f.line, f.col),
    )

    if as_prompt:
        from .prompter import render_fix_prompt

        rendered = render_fix_prompt(reported, target=path)
    elif as_sarif:
        rendered = _render_sarif(reported)
    elif as_json:
        rendered = _render_json(str(target), reported, fixed)
    else:
        rendered = _render_text(str(target), reported, fixed)
    out.write(_fit_encoding(rendered, out))

    threshold = _SEV_ORDER.get(fail_on)
    if threshold is None:  # "never"
        return 0
    failing = any(_SEV_ORDER[f.severity.value] >= threshold for f in reported)
    return 1 if failing else 0


def _apply_auto_fixes(findings: list[Finding], store: Store | None) -> list[Finding]:
    """Apply the confidence-gated AUTO fixes; record them; return those fixed.

    Fixes are applied high-offset-first so earlier deletes do not invalidate
    later spans before ``fixer._locate`` can re-anchor them.
    """
    from .engine.models import Fixability

    targets = [
        f for f in findings
        if (
            f.status is Status.OPEN
            and f.fixability is Fixability.AUTO
            and f.confidence >= AUTO_FIX_FLOOR
        )
    ]
    targets.sort(key=lambda f: (f.file, f.start), reverse=True)
    done: list[Finding] = []
    touched: set[str] = set()
    for f in targets:
        if fixer.apply_fix(f, None):
            done.append(f)
            touched.add(f.file)
            if store is not None:
                store.record(f, flush=False)
    if store is not None and done:
        store.flush()
    if touched:
        # Deletes shift the lines below them — re-anchor the still-open
        # findings in the edited files so the report carries real positions.
        fixer.reanchor([f for f in findings if f.file in touched])
    return done


# ------------------------------------------------------------------ rendering
def _one_line(s: str, n: int = 80) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _render_text(target: str, reported: list[Finding], fixed: list[Finding]) -> str:
    lines: list[str] = []
    # Say exactly what --fix changed — a bare count asks for blind trust.
    for f in sorted(fixed, key=lambda f: (f.file, f.line, f.col)):
        what = _one_line(f.matched_text) or f.message
        action = (
            f"replaced `{what}` with `{_one_line(f.replacement)}`"
            if f.replacement else f"removed `{what}`"
        )
        lines.append(f"{f.file}:{f.line}:{f.col}: fixed [{f.rule_id}] {action}")
    if fixed:
        lines.append("")
    for f in reported:
        lines.append(
            f"{f.file}:{f.line}:{f.col}: "
            f"{f.severity.value} [{f.rule_id}] {f.message} "
            f"({round(f.confidence * 100)}%)"
        )
    if reported:
        lines.append("")
    n_files = len({f.file for f in reported})
    score = round(project_score_from_findings(reported) * 100)
    summary = f"{len(reported)} finding(s) in {n_files} file(s) - slop score {score}/100"
    if fixed:
        summary += f" - {len(fixed)} fixed automatically (backups: *.aislopfixer.bak)"
    if not reported:
        summary = "no slop found" + (
            f" - {len(fixed)} fixed automatically (backups: *.aislopfixer.bak)"
            if fixed else ""
        )
    lines.append(summary)
    lines.append("")
    return "\n".join(lines)


def _render_json(target: str, reported: list[Finding], fixed: list[Finding]) -> str:
    by_sev = {s.value: 0 for s in Severity}
    for f in reported:
        by_sev[f.severity.value] += 1
    payload = {
        "tool": "aislopfixer",
        "version": __version__,
        "path": target,
        "slop_score": round(project_score_from_findings(reported) * 100),
        "total": len(reported),
        "auto_fixed": len(fixed),
        "fixed": [
            {
                "rule_id": f.rule_id,
                "file": f.file,
                "line": f.line,
                "col": f.col,
                "message": f.message,
                "matched_text": f.matched_text,
                "replacement": f.replacement,
            }
            for f in sorted(fixed, key=lambda f: (f.file, f.line, f.col))
        ],
        "by_severity": by_sev,
        "findings": [
            {
                "rule_id": f.rule_id,
                "category": f.category.value,
                "severity": f.severity.value,
                "file": f.file,
                "line": f.line,
                "col": f.col,
                "message": f.message,
                "matched_text": f.matched_text,
                "confidence": round(f.confidence, 3),
                "fixability": f.fixability.value,
                "suggested_fix": f.suggested_fix,
            }
            for f in reported
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


_SARIF_LEVEL = {"info": "note", "warning": "warning", "error": "error"}


def _render_sarif(reported: list[Finding]) -> str:
    """SARIF 2.1.0 — feeds GitHub code scanning (`upload-sarif`) and IDEs."""
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for f in reported:
        rules.setdefault(
            f.rule_id,
            {
                "id": f.rule_id,
                "shortDescription": {"text": f.message},
                "help": {"text": f.suggested_fix or f.message},
                "properties": {"category": f.category.value},
            },
        )
        results.append(
            {
                "ruleId": f.rule_id,
                "level": _SARIF_LEVEL[f.severity.value],
                "message": {"text": f.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": f.file.replace("\\", "/"),
                                "uriBaseId": "SRCROOT",
                            },
                            "region": {
                                "startLine": f.line,
                                "startColumn": f.col,
                                "snippet": {"text": f.matched_text[:512]},
                            },
                        }
                    }
                ],
                "properties": {
                    "confidence": round(f.confidence, 3),
                    "fixability": f.fixability.value,
                },
            }
        )
    doc = {
        "$schema": (
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
            "Schemata/sarif-schema-2.1.0.json"
        ),
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "aislopfixer",
                        "version": __version__,
                        "informationUri": (
                            "https://www.npmjs.com/package/@mertsoylu/aislopfixer"
                        ),
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
