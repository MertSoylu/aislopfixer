"""Source text → :class:`~aislopfixer.design.models.Document`.

One entry point, :func:`parse_document`, so the rest of the engine never has to
know which dialect a file is written in. Every style source an element can draw
from — utility classes, inline style, and the stylesheet rules that match its
class — is resolved into the same ``Decl`` list hanging off the element.
"""

from __future__ import annotations

import os

from ..models import Document, Element
from .classes import decode_classes
from .components import resolve as resolve_components
from .css import class_index, decl_from_css, parse_css
from .markup import JS_EXTS, MARKUP_EXTS, parse_markup, style_blocks
from .theme import ThemeIndex, load_theme

STYLE_EXTS = {".css", ".scss", ".sass", ".less", ".pcss", ".postcss"}
PROSE_EXTS = {".md"}

__all__ = ["parse_document", "resolve_components", "resolve_stylesheets",
           "kind_of", "STYLE_EXTS", "ThemeIndex", "load_theme"]


def kind_of(rel_path: str) -> str:
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in MARKUP_EXTS or ext in JS_EXTS:
        return "markup"
    if ext in STYLE_EXTS:
        return "style"
    return "other"


def parse_document(rel_path: str, abs_path: str, text: str,
                   theme: ThemeIndex | None = None) -> Document:
    """Parse one source file into elements, rules and resolved declarations."""
    ext = os.path.splitext(rel_path)[1].lower()
    kind = kind_of(rel_path)
    doc = Document(rel_path=rel_path, abs_path=abs_path, text=text, kind=kind,
                   theme=theme)

    if kind == "style":
        doc.css_rules, doc.custom_props = parse_css(text)
        return doc

    if kind != "markup":
        return doc

    doc.elements = parse_markup(text, ext)
    for a, b in style_blocks(text):
        rules, custom = parse_css(text[a:b], a)
        doc.css_rules.extend(rules)
        doc.custom_props.update(custom)

    idx = class_index(doc.css_rules)
    for el in doc.elements:
        _attach(el, idx, theme)
    return doc


def resolve_stylesheets(docs: list[Document]) -> None:
    """Attach the rules of *external* stylesheets to the elements they match.

    A rule reaches an element through its class name, and until now only a rule
    written inside the same file did: ``<style>`` blocks were indexed per
    document and a ``site.css`` next to the page was read for its vocabulary and
    then never connected to anything. So a plain HTML page with a stylesheet
    measured as a page with **no declarations at all** — no rhythm, no grids, no
    container, no contrast. Every structural metric was looking at an unstyled
    document and reporting that it had made no decisions.

    The corpus's clean-side twin pair is what surfaced it: the same design in
    utilities and in CSS, and only one of them had a page to measure.

    Same approximation as the single-file index and for the same reason: only
    single-class selectors, no specificity resolution. A compound selector
    attached to the wrong element corrupts the rhythm distribution, which is
    the one measurement that has to be exact.
    """
    index: dict[str, list] = {}
    for doc in docs:
        if doc.kind != "style":
            continue
        for name, decls in class_index(doc.css_rules).items():
            index.setdefault(name, []).extend(decls)
    if not index:
        return
    for doc in docs:
        if doc.kind != "markup":
            continue
        for el in doc.elements:
            for name in el.classes:
                el.decls.extend(index.get(name, ()))


def _attach(el: Element, css_by_class: dict[str, list],
            theme: ThemeIndex | None = None) -> None:
    """Fill ``el.decls`` from every style source that reaches this element."""
    decls = decode_classes(el.classes, theme)
    for prop, value in el.inline_style.items():
        decls.extend(decl_from_css(prop, value))
    for name in el.classes:
        rule_decls = css_by_class.get(name)
        if rule_decls:
            decls.extend(rule_decls)
    el.decls = decls
