"""Tolerant markup scanner: source text → an element tree with style attached.

Not a parser — a scanner, in the same spirit as :mod:`.lexer`. It must survive
JSX expressions, Vue directives, Svelte blocks, Astro frontmatter and plain
broken HTML without ever raising, because a design report that dies on one
malformed file is useless.

What it must get right, and why:

* **Tag detection in JS-first files.** ``useState<Foo>()`` and ``a < b`` are not
  elements. The guard is the character before ``<``: if the previous
  non-whitespace character is an identifier char or ``)``/``]``, the ``<`` is an
  operator or a type argument, never a tag. In markup-first files that guard is
  wrong (``hello<br>`` is a real tag after a letter), so it applies only to
  ``.jsx``/``.tsx``/``.js``/``.ts``.
* **Class values that are expressions.** ``className={cn("px-4", open && "bg-x")}``
  carries the design decisions; every string literal inside the braces is
  harvested. This is why the decoder sees ``bg-x`` even in a conditional.
* **Style in three places.** A ``py-20`` utility, an inline ``style``, and a CSS
  rule matching the element's class all express the same decision. All three
  are normalized to the same :class:`~aislopfixer.design.models.Decl` props by
  :mod:`.classes` and :mod:`.css`; this module only collects the raw sources.
"""

from __future__ import annotations

import re

from ..models import Element
from .expr import class_tokens
from .lexer import code_masks, point_in

# Markup-first formats: tags are the default reading of ``<``.
MARKUP_EXTS = {".html", ".htm", ".vue", ".svelte", ".astro", ".mdx"}
# JS-first formats: ``<`` is usually an operator; tags need the guard below.
JS_EXTS = {".jsx", ".tsx", ".js", ".ts", ".mjs", ".cjs"}

VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

# Tags whose body is not markup. <style> content is handed to the CSS parser by
# the caller; <script> content is code and must never enter the element tree.
RAW_TAGS = frozenset({"script", "style", "template"})
# …except in a single-file component, where `<template>` *is* the markup root.
# Reading it as raw text made every .vue file in a project measure as empty —
# the tool reported "no design code here" about a whole Vue front end.
SFC_EXTS = {".vue", ".svelte", ".astro"}
SFC_RAW_TAGS = RAW_TAGS - {"template"}

# Astro keeps its module code in a leading `---` fence. It is JavaScript, so a
# `<` in it is an operator; scanning starts after the fence. MDX uses the same
# fence for YAML frontmatter, where a `<` is not markup either.
_FRONTMATTER = re.compile(r"\A\s*---\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_FRONTMATTER_EXTS = {".astro", ".mdx"}

# MDX is JSX with markdown around it, and the markdown half carries two things
# that look like tags and are not: a fenced code block (``` ```tsx ``` — full of
# real JSX that documents an API rather than rendering a page) and an autolink
# (`<https://hono.dev>`). Both are blanked to spaces rather than cut out, so
# every offset the transformer later writes at still points where it did.
_MDX_FENCE = re.compile(r"^([ \t]*)(`{3,}|~{3,})[^\n]*\n.*?^\1?\2[ \t]*$",
                        re.M | re.S)
_MDX_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MDX_AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]*://[^\s<>]*>|<[^\s<>@]+@[^\s<>]+>")


def _blank(text: str, pattern: re.Pattern[str]) -> str:
    """Replace every match with spaces of the same length (offsets survive)."""
    def spaces(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return pattern.sub(spaces, text)


def mdx_body(text: str) -> str:
    """``text`` with the markdown half of an MDX file masked out.

    Length-preserving on purpose: :class:`~aislopfixer.design.models.Element`
    offsets index the *original* source, and the transformer rewrites spans in
    it.
    """
    return _blank(_blank(_blank(text, _MDX_FENCE), _MDX_INLINE_CODE),
                  _MDX_AUTOLINK)

_TAG_START = re.compile(r"[A-Za-z][A-Za-z0-9._:-]*")
_IDENT_TAIL = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$)]")

# Class-bearing attributes across every dialect we read.
CLASS_ATTRS = ("class", "className", ":class", "class:list", "v-bind:class")
STYLE_ATTRS = ("style", ":style", "v-bind:style")

_WS = re.compile(r"\s+")


# A tag's attribute list is bounded: past this many characters without a ``>``
# the ``<`` was a comparison operator, not a tag.
_TAG_SCAN_LIMIT = 4000
# Characters that can follow a type-argument list but never follow an element's
# opening tag: `useState<Foo>(`, `Array<string>;`, `x: Map<a,b> = …`.
_GENERIC_FOLLOWERS = frozenset("(),;=>.:|&?[]{}")


def _prev_nonspace(text: str, i: int) -> str:
    k = i - 1
    while k >= 0 and text[k] in " \t\r\n":
        k -= 1
    return text[k] if k >= 0 else ""


def _looks_like_generic(text: str, attrs: dict[str, str], past: int, n: int) -> bool:
    """True when a ``<Name…>`` candidate reads as a TS type-argument list.

    Only consulted when the character before ``<`` is an identifier char, which
    is where the ambiguity lives: ``hello<br/>`` in JSX text has the same shape
    as ``useState<Foo>``. Attributes settle most cases (a type list has none
    that carry values); the follower character settles the rest.
    """
    if any(v for v in attrs.values()):
        return False       # real attribute values — an element
    j = past
    while j < n and text[j] in " \t\r\n":
        j += 1
    return j >= n or text[j] in _GENERIC_FOLLOWERS


def _skip_string(text: str, i: int, quote: str) -> int:
    """Index just past a quoted attribute value opening at ``i``."""
    j = i + 1
    n = len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == quote:
            return j + 1
        j += 1
    return n


def _skip_braced(text: str, i: int) -> int:
    """Index just past a brace-balanced ``{…}`` expression opening at ``i``.

    Quotes inside are skipped whole so ``{cn("}")}`` does not close early.
    """
    depth = 0
    j = i
    n = len(text)
    while j < n:
        c = text[j]
        if c in "\"'`":
            j = _skip_string(text, j, c)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def _parse_attrs(text: str, i: int, limit: int) -> tuple[dict[str, str], dict[str, tuple[int, int]], int, bool, bool]:
    """Read attributes from ``i`` up to the tag's ``>``.

    Returns ``(values, spans, index_past_gt, self_closing, closed)``. ``spans``
    holds the offsets of each attribute's *value text* (without the quotes) so
    the transformer can rewrite a class list in place. ``closed`` is False when
    no ``>`` was found before ``limit`` — the candidate was not a tag at all.
    """
    values: dict[str, str] = {}
    spans: dict[str, tuple[int, int]] = {}
    n = min(limit, len(text))
    self_closing = False
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "/":
            self_closing = True
            i += 1
            continue
        if c == ">":
            return values, spans, i + 1, self_closing, True
        if c == "{":
            i = _skip_braced(text, i)  # {...spread} / Svelte shorthand
            continue
        m = re.compile(r"[^\s=/>{}\"']+").match(text, i)
        if m is None:
            i += 1
            continue
        name = m.group(0)
        i = m.end()
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i < n and text[i] == "=":
            i += 1
            while i < n and text[i] in " \t\r\n":
                i += 1
            if i < n and text[i] in "\"'":
                q = text[i]
                j = _skip_string(text, i, q)
                values[name] = text[i + 1:max(i + 1, j - 1)]
                spans[name] = (i + 1, max(i + 1, j - 1))
                i = j
            elif i < n and text[i] == "{":
                j = _skip_braced(text, i)
                values[name] = text[i:j]
                spans[name] = (i, j)
                i = j
            else:
                m2 = re.compile(r"[^\s>]*").match(text, i)
                values[name] = m2.group(0) if m2 else ""
                spans[name] = (i, m2.end() if m2 else i)
                i = m2.end() if m2 else i + 1
        else:
            values[name] = ""
    return values, spans, n, self_closing, False


def extract_classes(raw: str, env: dict[str, str] | None = None) -> list[str]:
    """Every class token in an attribute value, expression or not.

    A plain value splits on whitespace; an expression is evaluated by
    :func:`~aislopfixer.design.parse.expr.class_tokens`, which returns the union
    of every branch unless ``env`` binds the props that decide one. A
    conditional class is still a design decision, and dropping it would
    under-count exactly the files that took the most care.
    """
    return class_tokens(raw, env)


_CAMEL = re.compile(r"([a-z0-9])([A-Z])")


def extract_inline_style(raw: str) -> dict[str, str]:
    """Inline ``style`` as normalized kebab-case declarations.

    Handles both the CSS string form (``style="color:red"``) and the JSX object
    form (``style={{ marginTop: 8 }}``); the latter's camelCase keys are
    converted so both feed the same vocabulary.
    """
    if not raw:
        return {}
    out: dict[str, str] = {}
    raw = raw.strip()
    if raw.startswith("{"):
        body = raw.strip("{} \t\r\n")
        for part in re.split(r",(?![^(]*\))", body):
            if ":" not in part:
                continue
            k, _, v = part.partition(":")
            k = k.strip().strip("'\"")
            v = v.strip().strip("'\"").rstrip(",")
            if not k or not v:
                continue
            out[_CAMEL.sub(r"\1-\2", k).lower()] = v
        return out
    for part in raw.split(";"):
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k and v:
            out[k] = v
    return out


def _attach_classes(el: Element, attrs: dict[str, str],
                    spans: dict[str, tuple[int, int]]) -> None:
    """Collect classes from *every* class-bearing attribute on an element.

    An element can carry more than one at once: Vue's
    ``class="card" :class="{ active: on }"`` and Svelte's
    ``class="card" class:active={on}`` both name a static list and a dynamic
    one. Reading only the first was losing whichever came second, which in a
    Vue project is usually the one the state actually changes.

    ``class_attr`` / ``class_span`` still point at the single plain attribute —
    the transformer rewrites text, and only one of these is plain text.
    """
    seen: set[str] = set()
    for name, value in attrs.items():
        if name in CLASS_ATTRS:
            found = extract_classes(value)
        elif name.startswith("class:") and name != "class:list":
            found = [name[len("class:"):]]     # Svelte `class:active={on}`
        else:
            continue
        for token in found:
            if token not in seen:
                seen.add(token)
                el.classes.append(token)
    for name in CLASS_ATTRS:
        if name in attrs:
            el.class_attr = name
            el.class_span = spans.get(name)
            el.attr_classes = extract_classes(attrs[name])
            return


_TAG_STRIP = re.compile(r"<[^>]*>", re.S)
_INTERP_STRIP = re.compile(r"\{\{[^{}]*\}\}|\{[^{}]*\}")


def inner_text(text: str, a: int, b: int) -> str:
    """Visible text of ``text[a:b]`` — tags and interpolations removed."""
    if a >= b:
        return ""
    s = _TAG_STRIP.sub(" ", text[a:b])
    s = _INTERP_STRIP.sub(" ", s)
    return _WS.sub(" ", s).strip()


def _raw_body_end(text: str, tag: str, i: int) -> int:
    """Offset of the closing tag for a raw-text element, or EOF."""
    m = re.compile(rf"</{re.escape(tag)}\s*>", re.I).search(text, i)
    return m.start() if m else len(text)


def parse_markup(text: str, ext: str) -> list[Element]:
    """Scan ``text`` into an element list in document order.

    ``parent``/``children``/``depth`` are filled in; unmatched closing tags and
    unclosed elements are tolerated (the stack is popped to the nearest match,
    or left alone when there is none).
    """
    ext = ext.lower()
    js_mode = ext in JS_EXTS
    raw_tags = SFC_RAW_TAGS if ext in SFC_EXTS else RAW_TAGS
    if ext == ".mdx":
        text = mdx_body(text)
    strings: list[tuple[int, int]] = []
    if js_mode:
        strings, _comments = code_masks(text, ext)

    elements: list[Element] = []
    stack: list[int] = []
    n = len(text)
    i = 0
    if ext in _FRONTMATTER_EXTS:
        m = _FRONTMATTER.match(text)
        if m is not None:
            i = m.end()
    line = 1
    line_at = 0  # offset up to which ``line`` has been counted

    def line_of(pos: int) -> int:
        nonlocal line, line_at
        if pos >= line_at:
            line += text.count("\n", line_at, pos)
            line_at = pos
            return line
        return 1 + text.count("\n", 0, pos)

    while i < n:
        lt = text.find("<", i)
        if lt == -1:
            break
        # HTML comment / doctype / CDATA
        if text.startswith("<!--", lt):
            end = text.find("-->", lt)
            i = n if end == -1 else end + 3
            continue
        if text.startswith("<!", lt) or text.startswith("<?", lt):
            end = text.find(">", lt)
            i = n if end == -1 else end + 1
            continue
        if js_mode and point_in(strings, lt):
            i = lt + 1
            continue

        closing = text.startswith("</", lt)
        m = _TAG_START.match(text, lt + (2 if closing else 1))
        if m is None:
            i = lt + 1
            continue
        tag = m.group(0)
        norm = tag.lower() if tag[:1].islower() else tag

        if closing:
            # `</` is unambiguous in every dialect — never guard it. Guarding it
            # left every JSX element unclosed, which nested the whole page into
            # one subtree and made the depth-based section detection meaningless.
            gt = text.find(">", m.end())
            i = n if gt == -1 else gt + 1
            for k in range(len(stack) - 1, -1, -1):
                if elements[stack[k]].tag == norm:
                    for idx in stack[k:]:
                        elements[idx].inner_end = lt
                    del stack[k:]
                    break
            continue

        attrs, spans, past, self_closing, closed = _parse_attrs(
            text, m.end(), min(n, lt + _TAG_SCAN_LIMIT)
        )
        if not closed:
            i = lt + 1
            continue
        if js_mode and _prev_nonspace(text, lt) in _IDENT_TAIL and \
                _looks_like_generic(text, attrs, past, n):
            # `useState<Foo>()`, `Record<string, number>` — a type argument
            # list, not an element. The test rests on shape: no attributes, and
            # a follower character that only occurs in expression position.
            i = lt + 1
            continue
        el = Element(
            tag=norm,
            attrs=attrs,
            classes=[],
            inline_style={},
            start=lt,
            end=past,
            line=line_of(lt),
            depth=len(stack),
            parent=stack[-1] if stack else -1,
        )
        el.inner_start = past
        el.inner_end = past
        _attach_classes(el, attrs, spans)
        for name in STYLE_ATTRS:
            if name in attrs:
                el.inline_style = extract_inline_style(attrs[name])
                break

        idx = len(elements)
        elements.append(el)
        if el.parent >= 0:
            elements[el.parent].children.append(idx)

        if norm.lower() in raw_tags:
            body_end = _raw_body_end(text, tag, past)
            el.inner_start, el.inner_end = past, body_end
            close = text.find(">", body_end)
            i = n if close == -1 else close + 1
            continue

        if self_closing or norm in VOID_TAGS:
            el.inner_start = el.inner_end = past
            i = past
            continue

        stack.append(idx)
        i = past

    for idx in stack:               # unclosed at EOF
        elements[idx].inner_end = n
    for el in elements:
        if el.inner_end < el.inner_start:
            el.inner_end = el.inner_start
        el.own_text = inner_text(text, el.inner_start, el.inner_end)
    return elements


def style_blocks(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each ``<style>`` body — fed to the CSS parser."""
    out: list[tuple[int, int]] = []
    for m in re.finditer(r"<style\b[^>]*>", text, re.I):
        end = _raw_body_end(text, "style", m.end())
        if end > m.end():
            out.append((m.end(), end))
    return out
