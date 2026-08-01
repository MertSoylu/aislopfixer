"""Resolve JSX component usages back to the markup they render.

Componentisation hides the template. A generated Next.js page writes its band
padding once, inside a ``<Section>`` wrapper, and then uses that wrapper eight
times — so the source contains a single ``py-20`` where the rendered page
contains eight identical bands. Measuring the source literally would report
that page as having *more* rhythm variety than the HTML version of the same
design, which is exactly backwards.

This module closes that gap with a deliberately shallow resolution: find each
component's root element in the file that defines it, and hand every usage of
that component the root's own declarations plus its first-descendant chain —
the same reach the rhythm metric searches. Nothing is expanded into the tree,
so element counts and cluster signatures stay honest; usages simply stop being
blank.

Resolution is one level deep on purpose. Transitive inlining would need real
scope and prop analysis, and a wrong expansion would corrupt every downstream
distribution — a missing band is a smaller error than an invented one.
"""

from __future__ import annotations

import os
import re

from ..models import Decl, Document, Element

# `export default function Page(`, `function Card(`, `const Grid = (`,
# `const Grid: FC<P> = (`. Anything that binds a capitalised name to a value.
_DEF = re.compile(
    r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Z]\w*)\s*[(<]"
    r"|^[ \t]*(?:export\s+)?(?:default\s+)?const\s+([A-Z]\w*)\s*(?::[^=\n]*)?=",
    re.M,
)
_INHERIT_REACH = 3      # matches rhythm._PADDING_REACH
_SECTION_TAGS = frozenset({"section", "header", "footer", "main", "article", "nav"})


def _definitions(doc: Document) -> list[tuple[int, str]]:
    """``(offset, name)`` of every component definition in a file."""
    return sorted(
        (m.start(), m.group(1) or m.group(2))
        for m in _DEF.finditer(doc.text)
    )


def _roots(doc: Document) -> dict[str, int]:
    """``{component name: index of the element it returns}``.

    A component's returned JSX is at stack depth 0 — function bodies are not
    elements — so the root is the first depth-0 element after the definition.
    """
    defs = _definitions(doc)
    if not defs:
        return {}
    out: dict[str, int] = {}
    for i, el in enumerate(doc.elements):
        if el.depth != 0:
            continue
        name = ""
        for offset, candidate in defs:
            if offset < el.start:
                name = candidate
            else:
                break
        if name and name not in out:
            out[name] = i
    return out


_SFC_EXTS = {".vue", ".svelte", ".astro"}
_NOT_MARKUP = frozenset({"script", "style", "template"})


def sfc_component(doc: Document) -> tuple[str, int] | None:
    """``(component name, root element)`` for a single-file component.

    A ``.vue`` / ``.svelte`` / ``.astro`` file *is* a component, named after
    itself — there is no ``function Card()`` to find. Without this, a Vue or
    Svelte project's components resolve to nothing and every page built out of
    them measures as a handful of empty tags.
    """
    stem, ext = os.path.splitext(os.path.basename(doc.rel_path))
    if ext.lower() not in _SFC_EXTS or not stem[:1].isupper():
        return None
    for i, el in enumerate(doc.elements):
        if el.tag in _NOT_MARKUP:
            continue
        return stem, i
    return None


def _inherited_decls(doc: Document, idx: int) -> list[Decl]:
    """The root's declarations plus those of its first-descendant chain."""
    out: list[Decl] = list(doc.elements[idx].decls)
    frontier = [(idx, 0)]
    while frontier:
        i, depth = frontier.pop(0)
        if depth >= _INHERIT_REACH:
            continue
        for child in doc.elements[i].children[:2]:
            out.extend(doc.elements[child].decls)
            frontier.append((child, depth + 1))
    return out


def resolve(docs: list[Document]) -> None:
    """Attach rendered declarations to every component usage, in place."""
    # `const Card = styled.div\`…\`` binds a capitalised name to a value, so the
    # JSX definition scanner claims it — and then hands it the *next* element in
    # the file as its root, which belongs to something else entirely. A styled
    # component's root is its own template literal; nothing in the markup.
    styled_names = {sd.name for doc in docs for sd in doc.styled}

    roots: dict[str, tuple[Document, int]] = {}
    for doc in docs:
        sfc = sfc_component(doc)
        if sfc is not None:
            roots.setdefault(sfc[0], (doc, sfc[1]))
        for name, idx in _roots(doc).items():
            if name in styled_names:
                continue
            roots.setdefault(name, (doc, idx))

    cache: dict[str, tuple[list[Decl], bool, str]] = {}
    for name, (doc, idx) in roots.items():
        # No ``renders_tag`` for a JSX component: its markup is expanded by
        # :mod:`..render`, and a usage that survives unexpanded did so because a
        # cap was hit — under-reporting is the intended direction there.
        cache[name] = (_inherited_decls(doc, idx),
                       doc.elements[idx].tag in _SECTION_TAGS, "")
    # A `styled.section` component has no JSX root to find, but it renders one
    # element, with a known tag and known declarations — which is exactly what a
    # usage inherits. Registered after the JSX roots so a component that has
    # both keeps its markup, which is the fuller reading of the two.
    for doc in docs:
        for sd in doc.styled:
            cache.setdefault(sd.name, (sd.decls, sd.tag in _SECTION_TAGS, sd.tag))

    for doc in docs:
        own = {n: i for n, i in _roots(doc).items() if n not in styled_names}
        sfc = sfc_component(doc)
        if sfc is not None:
            own.setdefault(*sfc)
        for i, el in enumerate(doc.elements):
            if not el.is_component or el.tag not in cache:
                continue
            if own.get(el.tag) == i:
                continue          # the definition itself, not a usage
            decls, section_like, tag = cache[el.tag]
            el.inherited = decls
            el.section_like = section_like
            el.renders_tag = tag


def is_section(doc: Document, el: Element) -> bool:
    """True for a real section tag or a component that renders one."""
    return el.tag in _SECTION_TAGS or el.section_like
