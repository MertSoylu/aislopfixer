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


def ext_of(path: str) -> str:
    """Lower-cased file extension including the dot (``.js``), or ``""``."""
    return os.path.splitext(path)[1].lower()


# ------------------------------------------------------- code-aware masking
# A tolerant single-pass scanner (not a parser) that marks the byte spans of
# string literals and comments in a source file. Code rules use it to avoid
# matching inside strings/comments (e.g. ``eval(`` shown in a "don't use eval"
# comment, or ``// ...`` printed inside a template literal); the comment spans
# also double as a prose source for code files (see :func:`prose_regions`).
_JS_EXT = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"}
_CSS_EXT = {".css"}


def _lex(text: str, *, line_comment: str | None,
         block: tuple[str, str], templates: bool
         ) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    strings: list[tuple[int, int]] = []
    comments: list[tuple[int, int]] = []
    n = len(text)
    bo, bc = block
    i = 0
    while i < n:
        c = text[i]
        if line_comment and text.startswith(line_comment, i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            comments.append((i, j))
            i = j
            continue
        if text.startswith(bo, i):
            k = text.find(bc, i + len(bo))
            j = n if k == -1 else k + len(bc)
            comments.append((i, j))
            i = j
            continue
        if c in ("'", '"') or (templates and c == "`"):
            j = i + 1
            while j < n:
                cj = text[j]
                if cj == "\\":
                    j += 2
                    continue
                if cj == c:
                    j += 1
                    break
                if c != "`" and cj == "\n":  # unterminated quote — stop at EOL
                    break
                j += 1
            strings.append((i, min(j, n)))
            i = j
            continue
        i += 1
    return strings, comments


def code_masks(text: str, ext: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """``(string_spans, comment_spans)`` for a source file; ``([], [])`` if unknown."""
    ext = ext.lower()
    if ext in _JS_EXT:
        return _lex(text, line_comment="//", block=("/*", "*/"), templates=True)
    if ext in _CSS_EXT:
        return _lex(text, line_comment=None, block=("/*", "*/"), templates=False)
    return [], []


def point_in(spans: list[tuple[int, int]], pos: int) -> bool:
    """True if offset ``pos`` falls inside one of ``spans`` (half-open)."""
    return any(a <= pos < b for a, b in spans)


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


def _subtract(spans: list[tuple[int, int]],
              holes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove ``holes`` sub-ranges from ``spans`` (both lists half-open)."""
    if not holes:
        return spans
    holes = sorted(holes)
    out: list[tuple[int, int]] = []
    for a, b in spans:
        cur = a
        for ha, hb in holes:
            if hb <= cur or ha >= b:
                continue
            if ha > cur:
                out.append((cur, ha))
            cur = max(cur, hb)
            if cur >= b:
                break
        if cur < b:
            out.append((cur, b))
    return out


def _html_text_spans(text: str) -> list[tuple[int, int]]:
    """Text-node spans (between tags), excluding <script>/<style> bodies
    and template interpolations ({...} / {{...}} / ${...})."""
    blocked = [(m.start(), m.end()) for m in _SKIP_BLOCK.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _SKIP_INTERP.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _TAG_RE.finditer(text)]
    return _gaps(blocked, len(text))


def _jsx_text_spans(text: str) -> list[tuple[int, int]]:
    """Visible text nodes in JSX/TSX — only the gaps *flanked by tags*.

    Unlike HTML, a JSX/TSX file is mostly JavaScript: imports, hooks, function
    bodies and expressions live at module/function scope, *outside* any tag.
    Treating every non-tag gap as prose (as HTML does) flags code identifiers
    like ``const leverage = synergy()`` as buzzwords. A real JSX text node sits
    between a tag-close ``>`` and the next tag-open ``<``; module/expression code
    does not. Interpolations ({...} / ${...}) inside a node are still removed.
    """
    blocked = [(m.start(), m.end()) for m in _SKIP_BLOCK.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _TAG_RE.finditer(text)]
    nodes = [
        (a, b)
        for a, b in _gaps(blocked, len(text))
        if a > 0 and text[a - 1] == ">" and b < len(text) and text[b] == "<"
    ]
    # Only ``{...}`` that *opens inside a text node* is a JSX interpolation. A
    # brace-free component body — ``function Page() { return <p>hi</p> }`` — would
    # otherwise have its whole ``{ … }`` matched as one interpolation and wipe out
    # the prose it contains. The enclosing body brace opens in code (outside any
    # node), so the start-position test excludes it.
    interp = [
        (m.start(), m.end())
        for m in _SKIP_INTERP.finditer(text)
        if any(a <= m.start() < b for a, b in nodes)
    ]
    return _subtract(nodes, interp)


def _md_text_spans(text: str) -> list[tuple[int, int]]:
    """Everything except fenced and inline code."""
    blocked = [(m.start(), m.end()) for m in _MD_FENCE.finditer(text)]
    blocked += [(m.start(), m.end()) for m in _MD_INLINE.finditer(text)]
    return _gaps(blocked, len(text))


def prose_regions(text: str, kind: str, ext: str | None = None) -> list[tuple[int, int]]:
    """Absolute spans of human-visible prose for the given file kind.

    For code files the *comments* are the human-written prose — an AI tell like
    "as an AI language model" or a wall of buzzwords leaks into a JSDoc block
    just as easily as into page copy. Pass ``ext`` (e.g. ``".ts"``) to mine those
    comment spans; without it, code files return ``[]`` (identifiers are never
    prose).
    """
    if kind == "html":
        return _html_text_spans(text)
    if kind == "jsx":
        return _jsx_text_spans(text)
    if kind == "md":
        return _md_text_spans(text)
    if kind == "code" and ext:
        _, comments = code_masks(text, ext)
        return comments
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
