"""Helpers for turning regex spans into Finding objects."""

from __future__ import annotations

from .models import Category, Finding, Fixability, Severity, SourceFile


def line_col(text: str, offset: int) -> tuple[int, int]:
    """Return a 1-based (line, column) for a character offset."""
    line = text.count("\n", 0, offset) + 1
    last_nl = text.rfind("\n", 0, offset)
    col = offset - last_nl  # last_nl == -1 -> col = offset + 1
    return line, col


def line_bounds(text: str, offset: int) -> tuple[int, int]:
    """Start (inclusive) and end (exclusive) offsets of the line at offset."""
    start = text.rfind("\n", 0, offset) + 1
    nl = text.find("\n", offset)
    end = len(text) if nl == -1 else nl
    return start, end


def make_snippet(text: str, start: int, end: int) -> str:
    """The full source line(s) spanned by [start, end)."""
    ls, _ = line_bounds(text, start)
    _, le = line_bounds(text, max(start, end - 1))
    return text[ls:le]


def build_finding(
    sf: SourceFile,
    *,
    rule_id: str,
    category: Category,
    severity: Severity,
    message: str,
    start: int,
    end: int,
    fixability: Fixability = Fixability.MANUAL,
    suggested_fix: str = "",
    replacement: str = "",
    replace_template: str | None = None,
    prompt_label: str | None = None,
    expand_line: bool = False,
) -> Finding:
    """Construct a Finding, computing line/col/snippet from the span."""
    text = sf.text
    if expand_line:
        start, end = line_bounds(text, start)
    line, col = line_col(text, start)
    return Finding(
        rule_id=rule_id,
        category=category,
        severity=severity,
        message=message,
        file=sf.rel_path,
        abs_path=sf.abs_path,
        line=line,
        col=col,
        start=start,
        end=end,
        snippet=make_snippet(text, start, end),
        matched_text=text[start:end],
        fixability=fixability,
        suggested_fix=suggested_fix,
        replacement=replacement,
        replace_template=replace_template,
        prompt_label=prompt_label,
    )
