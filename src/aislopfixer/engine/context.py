"""Syntactic context helpers — tell legitimate code tokens from human prose.

The detectors use these to avoid false positives: framework route params like
``[id]``, Angular bindings like ``[checked]``, regex char-classes like ``[a-z]``
and JS destructuring are *not* AI slop. Marketing buzzwords matter only in
human-visible prose, never in identifiers or code.
"""

from __future__ import annotations

import os
import re

# --------------------------------------------------------------------- kinds
_HTML_LIKE = {".html", ".htm", ".vue", ".svelte", ".astro", ".xml"}
_JSX_LIKE = {".jsx", ".tsx"}  # mined like HTML: visible text sits between tags
_MD_LIKE = {".md", ".mdx"}


def file_kind(path: str) -> str:
    """Coarse classification used to locate human-visible prose."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _HTML_LIKE:
        return "html"
    if ext in _JSX_LIKE:
        return "jsx"
    if ext in _MD_LIKE:
        return "md"
    return "code"


# -------------------------------------------------------------- prose regions
_TAG_RE = re.compile(r"<[^>]*>", re.S)
_SKIP_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_SKIP_INTERP = re.compile(
    r"\$\{[^{}]*\}|\{\{[^{}]*\}\}|\{[^{}]*\}"
)
_MD_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_MD_INLINE = re.compile(r"`[^`]*`")


def _gaps(blocked: list[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    """Complement of ``blocked`` spans within ``[0, n)``."""
    spans: list[tuple[int, int]] = []
    last = 0
    for a, b in sorted(blocked):
        if last < a:
            spans.append((last, a))
        last = max(last, b)
    if last < n:
        spans.append((last, n))
    return spans


def _html_text_spans(text: str) -> list[tuple[int, int]]:
    """Text-node spans (between tags), excluding <script>/<style> bodies
    and template interpolations ({...} / {{...}} / ${...})."""
    blocked = [(m.start(), m.end()) for m in _SKIP_BLOCK.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _SKIP_INTERP.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _TAG_RE.finditer(text)]
    return _gaps(blocked, len(text))


def _md_text_spans(text: str) -> list[tuple[int, int]]:
    """Everything except fenced and inline code."""
    blocked = [(m.start(), m.end()) for m in _MD_FENCE.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _MD_INLINE.finditer(text)]
    return _gaps(blocked, len(text))


def prose_regions(text: str, kind: str) -> list[tuple[int, int]]:
    """Absolute spans of human-visible prose for the given file kind.

    Pure code files return ``[]`` — their tokens are never marketing prose.
    """
    if kind in ("html", "jsx"):
        return _html_text_spans(text)
    if kind == "md":
        return _md_text_spans(text)
    return []


def in_any(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    """True if ``[start, end)`` is fully contained in one of ``spans``."""
    return any(a <= start and end <= b for a, b in spans)


# ------------------------------------------------------------- self-annotation
ANNOT_MARKER = "aislopfixer:"


def on_annotation_line(text: str, pos: int) -> bool:
    """True if the line containing ``pos`` is one of our own annotations.

    Prevents the tool from re-flagging comments it inserted earlier.
    """
    ls = text.rfind("\n", 0, pos) + 1
    nl = text.find("\n", pos)
    le = len(text) if nl == -1 else nl
    return ANNOT_MARKER in text[ls:le]
