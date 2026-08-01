"""Syntactic context helpers — tell legitimate code tokens from human prose.

The detectors use these to avoid false positives: framework route params like
``[id]``, Angular bindings like ``[checked]``, regex char-classes like ``[a-z]``
and JS destructuring are *not* AI slop. Marketing buzzwords matter only in
human-visible prose, never in identifiers or code.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

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


# A `/` starts a regex literal (not division) only in expression position:
# after one of these characters, after `=>`, after a keyword, or at the start
# of the input. After an identifier/number/`)`/`]` it is division. `<`/`>` are
# deliberately absent — JSX closing tags (`</div>`) would misread as regexes.
_REGEX_PRECEDERS = frozenset("(,=:[!&|?{};+-*%~^")
_REGEX_KEYWORDS = frozenset({
    "return", "typeof", "case", "in", "of", "new", "delete", "void",
    "instanceof", "do", "else", "yield", "await", "throw",
})


def _regex_expr_position(text: str, i: int) -> bool:
    """True when a ``/`` at offset ``i`` sits where an expression may start."""
    k = i - 1
    while k >= 0 and text[k] in " \t\r\n":
        k -= 1
    if k < 0:
        return True
    p = text[k]
    if p in _REGEX_PRECEDERS:
        return True
    if p == ">" and k >= 1 and text[k - 1] == "=":  # arrow: x => /re/
        return True
    if p.isalnum() or p in "_$":
        w = k
        while w >= 0 and (text[w].isalnum() or text[w] in "_$"):
            w -= 1
        return text[w + 1: k + 1] in _REGEX_KEYWORDS
    return False


def _scan_regex(text: str, i: int, n: int) -> int | None:
    """End offset (past flags) of a regex literal opening at ``i``, or None.

    Honors escapes and ``[…]`` char classes (an unescaped ``/`` inside a class
    does not terminate). A newline before the closing ``/`` means it was not a
    regex after all (division) — return None and let the caller fall through.
    """
    j = i + 1
    in_class = False
    while j < n:
        cj = text[j]
        if cj == "\\":
            j += 2
            continue
        if cj == "\n":
            return None
        if in_class:
            if cj == "]":
                in_class = False
        elif cj == "[":
            in_class = True
        elif cj == "/":
            j += 1
            while j < n and text[j].isalpha():
                j += 1  # flags
            return j
        j += 1
    return None


def _lex(text: str, *, line_comment: str | None,
         block: tuple[str, str], templates: bool,
         regexes: bool = False,
         start: int = 0, end: int | None = None,
         stop_at_brace_depth: int | None = None,
         ) -> tuple[list[tuple[int, int]], list[tuple[int, int]], int]:
    """Lex ``text[start:end]`` into string/comment spans.

    When ``stop_at_brace_depth`` is set (template ``${…}`` expressions), stop
    once brace nesting returns to that depth after having entered deeper —
    so code *inside* interpolations is not marked as string content.

    Returns ``(strings, comments, index)`` where ``index`` is the first unconsumed
    offset (``end``, or the position after a closing ``}`` when brace-stopped).
    """
    strings: list[tuple[int, int]] = []
    comments: list[tuple[int, int]] = []
    n = len(text) if end is None else min(end, len(text))
    bo, bc = block
    i = start
    # Brace nesting for ${…} holes. Count only outside strings/comments so a
    # literal "}" inside a string does not close the interpolation early.
    brace_depth = 0
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
        if c in ("'", '"'):
            j = i + 1
            while j < n:
                cj = text[j]
                if cj == "\\":
                    j += 2
                    continue
                if cj == c:
                    j += 1
                    break
                if cj == "\n":  # unterminated quote — stop at EOL
                    break
                j += 1
            strings.append((i, min(j, n)))
            i = j
            continue
        if templates and c == "`":
            # Template literal: static chunks are strings; ${…} holes are code
            # (recursively lexed so nested templates/strings/comments work).
            seg = i  # include opening backtick in the first static span
            i += 1
            while i < n:
                cj = text[i]
                if cj == "\\":
                    i += 2
                    continue
                if cj == "`":
                    strings.append((seg, i + 1))
                    i += 1
                    break
                if cj == "$" and i + 1 < n and text[i + 1] == "{":
                    if seg < i:
                        strings.append((seg, i))
                    # Lex the expression; returns index past the closing `}`.
                    _, _, i = _lex(
                        text,
                        line_comment=line_comment,
                        block=block,
                        templates=True,
                        regexes=regexes,
                        start=i + 2,
                        end=n,
                        stop_at_brace_depth=0,
                    )
                    seg = i
                    continue
                i += 1
            else:
                # Unclosed template — mark remainder as string.
                strings.append((seg, n))
            continue
        if regexes and c == "/" and _regex_expr_position(text, i):
            # Regex literal: its `//`, quotes and braces are not code. Mark it
            # as a string-like span so exclude_strings drops matches inside it.
            j = _scan_regex(text, i, n)
            if j is not None:
                strings.append((i, j))
                i = j
                continue
        if stop_at_brace_depth is not None:
            if c == "{":
                brace_depth += 1
                i += 1
                continue
            if c == "}":
                if brace_depth == 0:
                    # Closes the ${ that opened before ``start``.
                    return strings, comments, i + 1
                brace_depth -= 1
                i += 1
                continue
        i += 1
    return strings, comments, i


@lru_cache(maxsize=64)
def code_masks(text: str, ext: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """``(string_spans, comment_spans)`` for a source file; ``([], [])`` if unknown.

    Cached per ``(text, ext)`` — several rules mask the same file, so the lex
    runs once. Treat the returned lists as immutable.
    """
    ext = ext.lower()
    if ext in _JS_EXT:
        s, c, _ = _lex(text, line_comment="//", block=("/*", "*/"),
                       templates=True, regexes=True)
        return s, c
    if ext in _CSS_EXT:
        s, c, _ = _lex(text, line_comment=None, block=("/*", "*/"), templates=False)
        return s, c
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


# Script bodies in HTML/SFC files — comments inside them are human prose
# (AI-leak / buzzword residue lands in Vue/Svelte <script> as often as .js).
_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.I)
_SCRIPT_CLOSE = re.compile(r"</script\s*>", re.I)


def _script_bodies(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each ``<script>…</script>`` body (content only)."""
    out: list[tuple[int, int]] = []
    pos = 0
    n = len(text)
    while pos < n:
        m = _SCRIPT_OPEN.search(text, pos)
        if m is None:
            break
        body_start = m.end()
        close = _SCRIPT_CLOSE.search(text, body_start)
        if close is None:
            out.append((body_start, n))
            break
        out.append((body_start, close.start()))
        pos = close.end()
    return out


def _script_comment_spans(text: str) -> list[tuple[int, int]]:
    """Comment spans inside ``<script>`` blocks, absolute offsets into ``text``."""
    out: list[tuple[int, int]] = []
    for a, b in _script_bodies(text):
        if a >= b:
            continue
        # Slice-local masks, then shift. .js masks cover // and /* */ for TS/JS.
        _, comments = code_masks(text[a:b], ".js")
        out.extend((a + ca, a + cb) for ca, cb in comments)
    return out


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


@lru_cache(maxsize=64)
def prose_regions(text: str, kind: str, ext: str | None = None) -> list[tuple[int, int]]:
    """Absolute spans of human-visible prose for the given file kind.

    Cached per ``(text, kind, ext)`` — several rules mine the same file's
    prose. Treat the returned list as immutable.

    For code files the *comments* are the human-written prose — an AI tell like
    "as an AI language model" or a wall of buzzwords leaks into a JSDoc block
    just as easily as into page copy. Pass ``ext`` (e.g. ``".ts"``) to mine those
    comment spans; without it, code files return ``[]`` (identifiers are never
    prose).

    HTML/SFC (``.vue`` / ``.svelte`` / ``.astro`` / ``.html``): text nodes *and*
    comments inside ``<script>`` blocks — models dump residue into both.
    """
    if kind == "html":
        return _html_text_spans(text) + _script_comment_spans(text)
    if kind == "jsx":
        # Module-scope comments are prose too (same as pure .js via ext).
        regions = _jsx_text_spans(text)
        if ext:
            _, comments = code_masks(text, ext)
            regions = regions + comments
        return regions
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
