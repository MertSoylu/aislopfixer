"""The tree the browser gets, not the tree the author typed.

Componentisation hides the template. A generated Next.js page writes one
``<Section>`` with ``py-20`` and uses it six times; it writes one ``<Card>`` and
renders it fifteen times through three ``{items.map(…)}`` calls. Measured
literally, that page has one band, one card and one grid — so the componentised
version of a template scores better than the copy-pasted HTML version of the
*same design*, which is exactly backwards.

:func:`render_documents` closes that gap by building a second, virtual tree per
page: component usages are replaced by what they render, ``{children}`` is
spliced back in at the slot, and a ``.map`` over an array whose length can be
*read from the source* repeats its child that many times. The result is handed
only to the metrics that measure the rendered page — rhythm, layout and
repetition. Decision density keeps reading the authored tree, because writing a
value once is one decision no matter how often it renders.

Nothing here guesses:

* a map over an array whose length cannot be read repeats **once**, not three
  times;
* a component whose definition is not in the project is emitted as-is;
* recursion, unbounded nesting and huge arrays are capped, and the caps are
  chosen so that hitting one under-reports rather than invents.

Every virtual element carries the source position of the **usage** that brought
it into the page, never the definition's. The usage is always inside the file
being reported on, so evidence offsets stay valid even when the component lives
in another file — and "this band is here" is what a reader needs, while "this
class is written there" is what the authored tree already says.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .models import Document, Element
from .parse.classes import decode_classes
from .parse.components import _definitions, sfc_component
from .parse.css import class_index, decl_from_css
from .parse.expr import class_tokens, skip_group, skip_string
from .parse.markup import inner_text

# Caps. Each one under-reports when hit: a truncated expansion looks *less*
# repetitive than the page really is, which is the safe direction to be wrong.
_MAX_ELEMENTS = 4000     # virtual elements per page
_MAX_REPEAT = 12         # copies one `.map` may contribute
_MAX_NEST = 6            # component-inside-component depth

_CHILDREN = re.compile(r"\{\s*(?:props\s*\.\s*)?children\s*\}")
_MAP_CALL = re.compile(r"([A-Za-z_$][\w$]*)\s*\.\s*map\s*\(")
_EACH = re.compile(r"\{#each\s+([A-Za-z_$][\w$]*)")          # Svelte
_V_FOR = re.compile(r"\bin\s+([A-Za-z_$][\w$]*)\s*$")        # Vue `item in ITEMS`
_PARAM_IDENT = re.compile(r"^([A-Za-z_$][\w$]*)")
_BIND_PREFIX = ("v-bind:", ":")


class _Component:
    """A component definition: where its markup is and what props it takes."""

    __slots__ = ("doc", "root", "params")

    def __init__(self, doc: Document, root: int, params: tuple[str, ...]):
        self.doc = doc
        self.root = root
        self.params = params


class _Env:
    """What a component was called with.

    ``props`` feeds the class-expression evaluator; ``counts`` carries the
    lengths of array props, which is the only way a ``{items.map(…)}`` inside a
    component can know how many times it runs.
    """

    __slots__ = ("props", "counts")

    def __init__(self, props: dict[str, str], counts: dict[str, int]):
        self.props = props
        self.counts = counts


_EMPTY = _Env({}, {})


class _Slot:
    """The children a component usage was given, waiting for ``{children}``.

    Carried down the component's whole subtree — the host is wherever the
    placeholder is written, which is rarely the root — and consumed once, so a
    component that mentions ``children`` in two branches does not render its
    content twice.
    """

    __slots__ = ("doc", "indices", "env", "host", "used")

    def __init__(self, doc: Document, indices: list[int], env: _Env, host: Element):
        self.doc = doc
        self.indices = indices
        self.env = env
        self.host = host
        self.used = False


# ------------------------------------------------------------- reading source
def _params(text: str, offset: int) -> tuple[str, ...]:
    """Destructured prop names of the definition starting at ``offset``.

    ``function Section({ id, tone, children }: Props)`` →
    ``("id", "tone", "children")``. Knowing the full list is what lets an
    *unpassed* prop read as ``undefined`` rather than as unknown, which is the
    difference between picking a ternary branch and unioning both.
    """
    open_paren = text.find("(", offset)
    if open_paren < 0 or open_paren - offset > 200:
        return ()
    end = skip_group(text, open_paren)
    inside = text[open_paren + 1:max(open_paren + 1, end - 1)]
    brace = inside.find("{")
    if brace < 0:
        return ()
    pattern = inside[brace:skip_group(inside, brace)]
    out: list[str] = []
    for part in pattern.strip("{} \t\r\n").split(","):
        m = _PARAM_IDENT.match(part.strip())
        if m is not None:
            out.append(m.group(1))
    return tuple(out)


_DEFINE_PROPS = re.compile(r"defineProps\s*(<[^>]*>)?\s*\(")
_EXPORT_LET = re.compile(r"^[ \t]*export\s+let\s+([A-Za-z_$][\w$]*)", re.M)
_ASTRO_PROPS = re.compile(r"const\s*(\{[^}]*\})\s*=\s*Astro\.props")


def _pattern_names(pattern: str) -> list[str]:
    """Identifiers bound by a ``{a, b: c, d = 1}`` destructuring pattern."""
    out: list[str] = []
    for part in pattern.strip("{}<> \t\r\n").split(","):
        m = _PARAM_IDENT.match(part.strip().lstrip("?"))
        if m is not None:
            out.append(m.group(1))
    return out


def _sfc_params(text: str) -> tuple[str, ...]:
    """Prop names a single-file component declares.

    Knowing the list is what lets an *unpassed* prop read as absent rather than
    as unknown — the difference between ``<Section>`` rendering the plain band
    and rendering both branches of its own conditional at once.
    """
    out: list[str] = _EXPORT_LET.findall(text)              # Svelte
    m = _ASTRO_PROPS.search(text)                           # Astro
    if m is not None:
        out += _pattern_names(m.group(1))
    m = _DEFINE_PROPS.search(text)                          # Vue
    if m is not None:
        if m.group(1):
            out += _pattern_names(m.group(1))
        body = text[m.end() - 1:skip_group(text, m.end() - 1)]
        inner = body[1:-1].strip()
        if inner.startswith(("{", "[")):
            out += (_pattern_names(inner) if inner[0] == "{"
                    else [t.strip(" \t\r\n\"'") for t in inner[1:-1].split(",")])
    return tuple(dict.fromkeys(n for n in out if n))


def _components(docs: list[Document]) -> dict[str, _Component]:
    """Every component definition in the project, by name."""
    out: dict[str, _Component] = {}
    # A `const Card = styled.div\`…\`` binds a capitalised name and has no JSX
    # at all, so the definition scanner would hand it the next element in the
    # file — a root belonging to something else, expanded at every usage.
    styled_names = {sd.name for doc in docs for sd in doc.styled}
    for doc in docs:
        sfc = sfc_component(doc)
        if sfc is not None:
            out.setdefault(sfc[0], _Component(doc, sfc[1], _sfc_params(doc.text)))
        defs = _definitions(doc)
        if not defs:
            continue
        for i, el in enumerate(doc.elements):
            if el.depth != 0:
                continue
            offset = -1
            name = ""
            for at, candidate in defs:
                if at < el.start:
                    offset, name = at, candidate
                else:
                    break
            if name and name not in out and name not in styled_names:
                out[name] = _Component(doc, i, _params(doc.text, offset))
    return out


def _array_length(doc: Document, name: str) -> int:
    """Entry count of a module-level array literal named ``name``, else 0.

    Memoised on the document. A component used eight times asked the same
    question eight times, and each answer was a regex over the whole file — on
    `nuxt-website` that was 2 482 full-text scans inside one render.
    """
    found = doc.arrays.get(name)
    if found is not None:
        return found
    m = re.search(rf"\b(?:const|let|var)\s+{re.escape(name)}\b[^=\n]{{0,80}}=\s*\[",
                  doc.text)
    length = 0 if m is None else _literal_length(doc.text[m.end() - 1:])
    doc.arrays[name] = length
    return length


def _literal_length(src: str) -> int:
    """Entry count of the array literal starting at ``src[0] == '['``."""
    if not src.startswith("["):
        return 0
    body = src[1:max(1, skip_group(src, 0) - 1)]
    if not body.strip():
        return 0
    depth = 0
    count = 1
    j, n = 0, len(body)
    while j < n:
        c = body[j]
        if c in "\"'`":
            j = skip_string(body, j)
            continue
        if c in "([{":
            j = skip_group(body, j)
            continue
        if c == "," and depth == 0:
            count += 1
        j += 1
    # A trailing comma is punctuation, not an entry.
    return count - 1 if body.rstrip().endswith(",") else count


# ------------------------------------------------------------------- binding
def _attr_expr(raw: str) -> str:
    """An attribute value as an expression: ``{x}`` → ``x``, ``y`` → ``"y"``."""
    raw = raw.strip()
    if raw.startswith("{") and skip_group(raw, 0) == len(raw):
        return raw[1:-1].strip()
    return '"' + raw.replace('"', '\\"') + '"'


def _bind(usage: Element, comp: _Component, doc: Document, outer: _Env) -> _Env:
    """The environment a component body sees for one usage."""
    props: dict[str, str] = {p: "undefined" for p in comp.params}
    counts: dict[str, int] = {}
    for name, raw in usage.attrs.items():
        if name in ("key", "ref"):
            continue
        if not raw:
            # A bare attribute is a true boolean in every dialect: `<Section muted>`.
            props[name] = "true"
            continue
        bound = next((p for p in _BIND_PREFIX if name.startswith(p)), "")
        if bound:
            # Vue's `:items="FEATURES"` — the value is an expression, not the
            # string "FEATURES". Reading it as a literal bound every prop to
            # its own name.
            name, expr = name[len(bound):], raw.strip()
        else:
            expr = _attr_expr(raw)
        props[name] = expr
        if expr.startswith("["):
            counts[name] = _literal_length(expr)
        elif expr.isidentifier():
            counts[name] = outer.counts.get(expr) or _array_length(doc, expr)
    return _Env(props, counts)


def _file_loops(doc: Document) -> list[tuple[int, int, str]]:
    """Every loop in the file, once: ``(start, end, array name)``, in order.

    Scanned per *document* rather than per element. The per-element version
    sliced out the element's whole inner region and ran two regexes over the
    copy, and a page's root element is the whole file — 4 304 of those on
    ``nuxt-website``, the single largest cost left in the expansion after the
    component files stopped being expanded.
    """
    out: list[tuple[int, int, str]] = []
    for m in _MAP_CALL.finditer(doc.text):
        paren = m.end() - 1
        out.append((paren, skip_group(doc.text, paren), m.group(1)))
    for m in _EACH.finditer(doc.text):
        close = doc.text.find("{/each}", m.end())
        out.append((m.start(), len(doc.text) if close < 0 else close, m.group(1)))
    out.sort()
    return out


def _repeat_ranges(doc: Document, el: Element) -> list[tuple[int, int, str]]:
    """``(start, end, array name)`` of each loop written inside this element.

    Three dialects, one meaning: JSX's ``items.map(…)``, Svelte's
    ``{#each items as …}`` and — handled by the caller, since it lives on the
    child — Vue's ``v-for``.
    """
    return [(a, min(b, el.inner_end), name)
            for a, b, name in _file_loops(doc)
            if el.inner_start <= a < el.inner_end]


def _multiplicity(doc: Document, el: Element, child: Element, env: _Env,
                  cache: dict | None = None) -> int:
    name = ""
    v_for = child.attrs.get("v-for", "")
    if v_for:
        m = _V_FOR.search(v_for.strip().rstrip(")"))
        name = m.group(1) if m is not None else ""
    if not name:
        key = (doc.rel_path, el.start)
        ranges = None if cache is None else cache.get(key)
        if ranges is None:
            # One scan per parent, not one per child: a component used eight
            # times re-scanned the same region eight times, and on a real repo
            # that was the second-largest cost in the whole expansion. The
            # file's loops themselves are found once per document, below.
            if cache is None:
                ranges = _repeat_ranges(doc, el)
            else:
                loops = cache.get(("loops", doc.rel_path))
                if loops is None:
                    loops = _file_loops(doc)
                    cache[("loops", doc.rel_path)] = loops
                ranges = [(a, min(b, el.inner_end), found)
                          for a, b, found in loops
                          if el.inner_start <= a < el.inner_end]
                cache[key] = ranges
        for start, end, found in ranges:
            if start <= child.start < end:
                name = found
                break
    if not name:
        return 1
    n = env.counts.get(name) or _array_length(doc, name)
    return max(1, min(_MAX_REPEAT, n)) if n else 1


def _slot_gaps(doc: Document, el: Element) -> str:
    """Text directly inside ``el`` — its children's own spans removed."""
    parts: list[str] = []
    cursor = el.inner_start
    for ci in el.children:
        child = doc.elements[ci]
        parts.append(doc.text[cursor:child.start])
        cursor = max(cursor, child.inner_end)
    parts.append(doc.text[cursor:el.inner_end])
    return "".join(parts)


def _direct_text(doc: Document, el: Element) -> str:
    """Visible text belonging to ``el`` itself, not to its descendants."""
    gaps = _slot_gaps(doc, el)
    return inner_text(gaps, 0, len(gaps))


def _aggregate_text(elements: list[Element]) -> None:
    """Roll direct text back up the virtual tree, in place.

    Section role classification reads a band's whole text, and after expansion
    a band's text lives in nodes that came from three different places. Children
    are always emitted after their parent, so one reverse pass is enough.
    """
    for i in range(len(elements) - 1, -1, -1):
        el = elements[i]
        parts = [el.own_text] + [elements[c].own_text for c in el.children]
        el.own_text = " ".join(p for p in parts if p)


# ------------------------------------------------------------------ emitting
class _Builder:
    def __init__(self, page: Document, comps: dict[str, _Component]):
        self.page = page
        self.comps = comps
        self.out: list[Element] = []
        self.css: dict[str, dict[str, list]] = {}
        self.loops: dict[tuple[str, int], list] = {}
        self.expanded = False
        self.capped = False

    def _index(self, doc: Document) -> dict[str, list]:
        got = self.css.get(doc.rel_path)
        if got is None:
            got = class_index(doc.css_rules)
            self.css[doc.rel_path] = got
        return got

    def _clone(self, doc: Document, el: Element, env: _Env,
               at: Element, parent: int, depth: int) -> Element:
        """A virtual copy of ``el`` positioned at the usage site ``at``."""
        classes, decls = el.classes, el.decls
        raw = el.attrs.get(el.class_attr, "") if el.class_attr else ""
        if env.props and raw.strip().startswith(("{", "[")):
            resolved = class_tokens(raw, env.props)
            if resolved != classes:
                classes = resolved
                decls = decode_classes(classes, doc.theme)
                for prop, value in el.inline_style.items():
                    decls.extend(decl_from_css(prop, value))
                index = self._index(doc)
                for name in classes:
                    decls.extend(index.get(name, ()))
        if el.is_component and el.inherited:
            # Reached only when the usage was *not* expanded: a `styled.div`
            # whose markup is a template literal, a recursion cap, a component
            # defined outside the scan. In the rendered tree that element really
            # does carry what it renders, and every structural metric reads
            # ``decls`` — leaving them on ``inherited`` alone made a whole
            # CSS-in-JS project measure as a page of empty tags.
            decls = decls + el.inherited
        return Element(
            # `<Title>` from `styled.h2` draws an `h2`, and every metric that
            # reads tags — heading alignment, section detection, copy — is
            # asking about what the browser gets, not what the source called it.
            tag=el.renders_tag or el.tag,
            attrs=el.attrs,
            classes=classes,
            inline_style=el.inline_style,
            start=at.start,
            end=at.end,
            line=at.line,
            depth=depth,
            parent=parent,
            inner_start=at.inner_start,
            inner_end=at.inner_end,
            own_text=_direct_text(doc, el),
            class_attr=el.class_attr,
            # A virtual element is only rewritable when it *is* the authored
            # one; a copy spliced in from a component definition has no span of
            # its own in this file.
            class_span=el.class_span if at is el else None,
            attr_classes=el.attr_classes if at is el else [],
            decls=decls,
            # Only reached for an element that was *not* expanded — an unknown
            # component, or a `styled.section` whose markup lives in a template
            # literal. Dropping what it renders here would make exactly those
            # projects measure as empty tags.
            inherited=el.inherited,
            section_like=el.section_like,
            module_classes=el.module_classes,
        )

    def emit(self, doc: Document, idx: int, env: _Env, at: Element,
             parent: int, depth: int, stack: tuple[str, ...],
             slot: _Slot | None) -> None:
        if len(self.out) >= _MAX_ELEMENTS:
            self.capped = True
            return
        el = doc.elements[idx]

        comp = self.comps.get(el.tag) if el.is_component else None
        if (comp is not None and el.tag not in stack
                and len(stack) < _MAX_NEST
                and not (comp.doc is doc and comp.root == idx)):
            self.expanded = True
            inner = _Slot(doc, list(el.children), env, el) if el.children else None
            self.emit(comp.doc, comp.root, _bind(el, comp, doc, env), el,
                      parent, depth, stack + (el.tag,), inner)
            return

        if el.tag == "slot":
            # A single-file component marks its hole with an element rather than
            # a placeholder in the text. The `<slot>` itself never renders, so
            # the usage's children take its place, not a place inside it.
            self._fill(slot, parent, depth - 1)
            return

        here = len(self.out)
        self.out.append(self._clone(doc, el, env, at, parent, depth))
        if parent >= 0:
            self.out[parent].children.append(here)

        for ci in el.children:
            child = doc.elements[ci]
            copies = _multiplicity(doc, el, child, env, self.loops)
            if copies >= _MAX_REPEAT:
                self.capped = True
            for _ in range(copies):
                self.emit(doc, ci, env, child, here, depth + 1, stack, slot)

        if slot is not None and _CHILDREN.search(_slot_gaps(doc, el)):
            self._fill(slot, here, depth)

    def _fill(self, slot: _Slot | None, parent: int, depth: int) -> None:
        """Emit a component usage's own children into its slot, once."""
        if slot is None or slot.used:
            return
        slot.used = True
        for ci in slot.indices:
            child = slot.doc.elements[ci]
            for _ in range(_multiplicity(slot.doc, slot.host, child, slot.env,
                                         self.loops)):
                self.emit(slot.doc, ci, slot.env, child, parent, depth + 1, (), None)


_WRAPPER_TAGS = frozenset({"template", "script", "style"})


def _page_roots(doc: Document) -> list[int]:
    """Top-level elements that actually render.

    A single-file component wraps its markup in ``<template>``, which is not an
    element the browser draws; its children are the real roots. ``<script>`` and
    ``<style>`` never enter the rendered tree at all.
    """
    out: list[int] = []
    for i, el in enumerate(doc.elements):
        if el.depth != 0:
            continue
        if el.tag == "template":
            out.extend(el.children)
        elif el.tag not in _WRAPPER_TAGS:
            out.append(i)
    return out


_COMPONENT_DIRS = frozenset({"components", "component", "widgets", "partials"})


def _in_components_dir(rel_path: str) -> bool:
    """True when a file sits under the directory every framework keeps parts in."""
    parts = rel_path.replace("\\", "/").lower().split("/")[:-1]
    return any(p in _COMPONENT_DIRS for p in parts)


def _used_names(docs: list[Document], comps: dict[str, _Component]) -> set[str]:
    used: set[str] = set()
    for doc in docs:
        for i, el in enumerate(doc.elements):
            if not el.is_component:
                continue
            comp = comps.get(el.tag)
            if comp is not None and not (comp.doc is doc and comp.root == i):
                used.add(el.tag)
    return used


def _renders_differently(doc: Document) -> bool:
    """True when a usage renders something the authored element does not say.

    A `styled.h2` usage is an ``h2`` carrying the component's declarations, and
    neither fact is on the authored element. Without this the "nothing changed"
    shortcut handed the authored tree straight to the structural metrics, and a
    CSS-in-JS project measured as a page of empty custom tags.
    """
    return any(el.renders_tag or (el.is_component and el.inherited)
               for el in doc.elements)


def render_documents(docs: list[Document]) -> list[Document]:
    """Parallel documents whose element trees are what each page renders.

    A document with nothing to expand is returned **unchanged** — the same
    object — so plain HTML projects take exactly the path they always did.
    """
    comps = _components(docs)
    if not comps and not any(_renders_differently(d) for d in docs):
        return docs
    used = _used_names(docs, comps)
    # A component's own file is not a page, and expanding it standalone builds a
    # virtual tree no metric asks for: the pages that use it already contain it,
    # expanded there, with the props they passed. On `nuxt-website` that was
    # most of the cost — eighteen documents hitting the 4 000-element cap, half
    # of them files like `AppFooter.vue`.
    #
    # `used` alone could not decide it. A component nothing renders — or one
    # reached only from a `.md` page, or through an auto-import the scanner does
    # not follow — looked exactly like a route. What settles it is where the
    # file lives: a single-file component under a `components/` directory is a
    # component by the convention every one of these frameworks shares, and a
    # page never is. Capitalisation alone is not the signal — `App.vue` is
    # capitalised and *is* the page — and JSX has no signal at all, since
    # `export default function Page()` is a definition too. There the `used`
    # test stands exactly as it was.
    skip = {
        (comp.doc.rel_path, comp.root)
        for name, comp in comps.items() if name in used
    }
    skip |= {(doc.rel_path, found[1]) for doc in docs
             if _in_components_dir(doc.rel_path)
             and (found := sfc_component(doc)) is not None}

    out: list[Document] = []
    for doc in docs:
        if doc.kind != "markup" or not doc.elements:
            out.append(doc)
            continue
        builder = _Builder(doc, comps)
        for i in _page_roots(doc):
            if (doc.rel_path, i) in skip:
                continue
            builder.emit(doc, i, _EMPTY, doc.elements[i], -1, 0, (), None)
        if (not builder.expanded and len(builder.out) == len(doc.elements)
                and not _renders_differently(doc)):
            out.append(doc)          # nothing changed — keep the authored tree
            continue
        _aggregate_text(builder.out)
        # `_sections` is derived from the element tree, and this document has a
        # different one. `replace` copies every field, so leaving it alone
        # handed the rendered page the authored page's band list.
        out.append(replace(doc, elements=builder.out,
                           render_capped=builder.capped, _sections=None))
    return out
