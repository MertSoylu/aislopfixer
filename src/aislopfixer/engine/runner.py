"""Drive the registered rules over source files."""

from __future__ import annotations

from . import rules as _rules  # noqa: F401  (import registers all rules)
from .context import on_annotation_line
from .models import Finding, SourceFile
from .registry import CROSS_RULES, FILE_RULES
from .scoring import score_finding


def _backfill_confidence(findings: list[Finding]) -> list[Finding]:
    """Set each finding's confidence unless a rule already pinned one."""
    for f in findings:
        f.confidence = f.confidence or score_finding(f)
    return findings


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Drop findings that target an identical non-empty span (keep first).

    Zero-length spans (doc-level / summary findings) are never deduped.
    """
    seen: set[tuple[str, int, int]] = set()
    out: list[Finding] = []
    for f in findings:
        if f.start < f.end:
            key = (f.file, f.start, f.end)
            if key in seen:
                continue
            seen.add(key)
        out.append(f)
    return out


# Rules whose repeats inside one file add no information: the same brand, person
# or address placeholder shows up once per mention. One finding per distinct
# value is enough — the rest are noise (e.g. "Acme" five times on an About page).
_COLLAPSE_PREFIXES = (
    "placeholder.company",
    "placeholder.name",
    "placeholder.address",
)


def _collapse_repeats(findings: list[Finding]) -> list[Finding]:
    """Keep the first occurrence of each repeated low-value placeholder per file."""
    seen: set[tuple[str, str]] = set()
    out: list[Finding] = []
    for f in findings:
        if f.rule_id.startswith(_COLLAPSE_PREFIXES):
            sig = (f.rule_id, f.matched_text.lower())
            if sig in seen:
                continue
            seen.add(sig)
        out.append(f)
    return out


def run_file_rules(sf: SourceFile) -> list[Finding]:
    """Run every per-file rule against a single file."""
    out: list[Finding] = []
    for rule in FILE_RULES:
        out.extend(rule.scan(sf))
    # Drop findings that live on our own annotation comments — never re-flag
    # what a previous fix session wrote into the file.
    out = [f for f in out if not on_annotation_line(sf.text, f.start)]
    return _backfill_confidence(_collapse_repeats(_dedupe(out)))


def run_cross_rules(files: list[SourceFile]) -> list[Finding]:
    """Run every cross-file rule against the full file set."""
    out: list[Finding] = []
    for rule in CROSS_RULES:
        out.extend(rule.scan_all(files))
    return _backfill_confidence(out)


def scan_all(files: list[SourceFile]) -> list[Finding]:
    """Convenience: run all rules over all files."""
    out: list[Finding] = []
    for sf in files:
        out.extend(run_file_rules(sf))
    out.extend(run_cross_rules(files))
    return out
