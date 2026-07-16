"""Drive the registered rules over source files."""

from __future__ import annotations

from . import rules as _rules  # noqa: F401  (import registers all rules)
from .context import on_annotation_line
from .models import Finding, SourceFile
from .registry import CROSS_RULES, FILE_RULES
from .scoring import corroborate, score_finding

# Above this many findings in one file, skip the O(n²) containment pass — its
# noise-reduction is not worth the cost on a pathological file.
_CONTAINMENT_CAP = 400


def _backfill_confidence(findings: list[Finding]) -> list[Finding]:
    """Set each finding's confidence unless a rule already pinned one."""
    for f in findings:
        if not f.pinned and not f.confidence:
            f.confidence = score_finding(f)
    return findings


def _rank(f: Finding) -> tuple[float, int]:
    return (f.confidence, f.severity.rank)


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Collapse findings on an identical non-empty span, keeping the strongest.

    When two rules flag the exact same span, the higher-confidence (then
    higher-severity) finding wins instead of "whichever ran first". Zero-length
    spans (doc-level / summary findings) are never deduped.
    """
    at: dict[tuple[str, int, int], int] = {}
    out: list[Finding] = []
    for f in findings:
        if f.start < f.end:
            key = (f.file, f.start, f.end)
            if key in at:
                i = at[key]
                if _rank(f) > _rank(out[i]):
                    out[i] = f
                continue
            at[key] = len(out)
        out.append(f)
    return out


def _drop_contained(findings: list[Finding]) -> list[Finding]:
    """Drop a finding strictly contained within a larger *same-category* one.

    A nested match of the same concern (e.g. an inner span inside the line span
    another rule of the same family already flagged) adds no information. Spans
    of different categories are kept — they are distinct concerns on one line.
    """
    spans = [
        (f.start, f.end, f.category, i)
        for i, f in enumerate(findings)
        if f.start < f.end
    ]
    if len(spans) > _CONTAINMENT_CAP:
        return findings
    drop: set[int] = set()
    for as_, ae, ac, ai in spans:
        for bs, be, bc, bi in spans:
            if ai == bi or bc is not ac:
                continue
            if bs <= as_ and ae <= be and (bs, be) != (as_, ae):
                drop.add(ai)
                break
    return [f for i, f in enumerate(findings) if i not in drop]


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
    # what a previous fix session wrote into the file. Zero-span findings are
    # doc-level (density aggregates anchored at offset 0), not "on" any line.
    out = [
        f for f in out
        if f.start == f.end or not on_annotation_line(sf.text, f.start)
    ]
    out = _backfill_confidence(out)        # confidence first: dedupe keeps the strongest
    out = _drop_contained(_collapse_repeats(_dedupe(out)))
    return corroborate(out)                # boost when AI tells co-occur in this file


def run_cross_rules(files: list[SourceFile]) -> list[Finding]:
    """Run every cross-file rule against the full file set."""
    out: list[Finding] = []
    for rule in CROSS_RULES:
        out.extend(rule.scan_all(files))
    return _backfill_confidence(out)


def scan_all(files: list[SourceFile]) -> list[Finding]:
    """Convenience: run all rules over all files.

    File-rule findings are corroborated once inside :func:`run_file_rules`;
    after cross-rules join, confidences are recomputed so import/duplicate
    tells co-boost with same-file authorship signals.
    """
    from .scoring import reset_and_corroborate

    out: list[Finding] = []
    for sf in files:
        out.extend(run_file_rules(sf))
    out.extend(run_cross_rules(files))
    return reset_and_corroborate(out)
