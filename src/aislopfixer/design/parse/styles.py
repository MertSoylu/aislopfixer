"""Styles a React project keeps outside the class attribute.

Half of real React never writes a utility class. It writes
``className={styles.card}`` against a ``Card.module.css``, or it writes
``styled.div`…` `` and never names a class at all — and to a scanner that only
reads class *tokens*, both are empty. An empty report reads as a clean one, so
the tool was quietly telling a whole dialect of the ecosystem that it had no
design to measure.

Two resolutions, both deliberately literal:

* **CSS Modules** — an ``import styles from "./Card.module.css"`` is followed to
  the stylesheet, and every ``styles.card`` in a class attribute picks up that
  file's ``.card`` rule. The local name is irrelevant (``styles``, ``s``,
  ``css``); the *import specifier* is what resolves.
* **CSS-in-JS** — ``const Card = styled.div`…` `` is read as a component
  definition whose root is a ``div`` carrying those declarations, which is
  exactly the shape :mod:`.components` already resolves usages against.

Nothing is guessed. A declaration whose value is an interpolation
(``color: ${p => p.theme.accent}``) is not read as a colour, and an import that
resolves to no file in the project is not matched by name — both are *counted*,
and the count reaches the report. A measurement that silently skips half a
project is worse than one that says how much it skipped.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..models import Decl, Document, Element
from .css import class_index, decl_from_css
from .expr import skip_string

__all__ = ["StyledDef", "scan_styled", "resolve_styles", "module_imports"]

_STYLE_EXTS = (".css", ".scss", ".sass", ".less", ".pcss", ".postcss")

# `import styles from "./Card.module.css"`, `import * as s from …`.
_IMPORT = re.compile(
    r"""import\s+(?:\*\s+as\s+)?([A-Za-z_$][\w$]*)\s+from\s*['"]([^'"\n]+)['"]"""
)


def module_imports(text: str) -> dict[str, str]:
    """``{local name: specifier}`` for every CSS-Module import in a file."""
    out: dict[str, str] = {}
    for m in _IMPORT.finditer(text):
        spec = m.group(2)
        if ".module." in spec and spec.lower().endswith(_STYLE_EXTS):
            out[m.group(1)] = spec
    return out


def _normalize(rel_path: str) -> str:
    return rel_path.replace("\\", "/").lstrip("./")


def _resolve_spec(from_rel: str, spec: str) -> str:
    """Specifier → project-relative path, as the bundler would resolve it."""
    if spec.startswith("."):
        base = os.path.dirname(from_rel)
        return _normalize(os.path.normpath(os.path.join(base, spec)))
    # A bare or aliased specifier (`@/styles/Card.module.css`) cannot be
    # resolved without the bundler's config; the basename fallback in
    # :func:`resolve_styles` handles it, and says so when it cannot.
    return _normalize(spec)


# ---------------------------------------------------------------- CSS-in-JS
# `const Card = styled.div`, `export const Wrap = styled(Card)`, and the
# `.attrs(…)` / generic-parameter forms that sit between the call and the
# template literal.
_STYLED = re.compile(
    r"""(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*"""
    r"""(?::[^=\n]*)?=\s*styled\s*"""
    r"""(?:\.\s*([A-Za-z][\w]*)|\(\s*([A-Za-z_$][\w$.]*)\s*\))""",
    re.M,
)
_HOLE = "\x00"
_INTERP = re.compile(r"\$\{")
_DECL = re.compile(r"([-A-Za-z][-\w]*)\s*:\s*([^;{}]+)")
# A nested block's prelude (`&:hover`, `@media …`, `${Card}:hover`) is not a
# declaration; only the declarations inside it are read.
_MAX_STYLED = 400        # definitions read per file — reported when hit


@dataclass
class StyledDef:
    """One ``styled.tag`…` `` component: its name, its tag, its declarations."""

    name: str
    tag: str
    decls: list[Decl] = field(default_factory=list)
    line: int = 1
    start: int = 0
    unreadable: int = 0    # declarations whose value was an interpolation


def _mask_interpolations(body: str) -> tuple[str, int]:
    """Replace every ``${…}`` with a marker; returns the text and the count."""
    out: list[str] = []
    i, n, holes = 0, len(body), 0
    last = 0
    while i < n:
        if body[i] == "\\":
            i += 2
            continue
        if body[i] == "$" and body[i + 1:i + 2] == "{":
            depth = 0
            j = i + 1
            while j < n:
                c = body[j]
                if c in "\"'`":
                    j = skip_string(body, j)
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            out.append(body[last:i])
            out.append(_HOLE)
            holes += 1
            i = last = j
            continue
        i += 1
    out.append(body[last:])
    return "".join(out), holes


def _flatten_decls(body: str) -> tuple[list[tuple[str, str]], int]:
    """Every ``prop: value`` in a styled template, at any nesting depth.

    Nested blocks (``&:hover { … }``, ``@media … { … }``) contribute their own
    declarations — they are design decisions the component makes — while their
    preludes are skipped, because a selector is not a property.
    """
    masked, _ = _mask_interpolations(body)
    pairs: list[tuple[str, str]] = []
    unreadable = 0
    for chunk in re.split(r"[{}]", masked):
        for m in _DECL.finditer(chunk):
            prop, value = m.group(1).strip().lower(), m.group(2).strip()
            if not prop or not value or prop.startswith("&"):
                continue
            if _HOLE in prop:
                unreadable += 1
                continue
            if _HOLE in value:
                # `color: ${p => p.theme.accent}` is a value this tool cannot
                # read. Guessing a colour here would move the palette score for
                # a reason nobody could check.
                unreadable += 1
                continue
            pairs.append((prop, value))
    return pairs, unreadable


def scan_styled(text: str) -> list[StyledDef]:
    """Every ``styled`` component defined in one file."""
    out: list[StyledDef] = []
    for m in _STYLED.finditer(text):
        if len(out) >= _MAX_STYLED:
            break
        tick = text.find("`", m.end())
        if tick < 0 or text[m.end():tick].count("\n") > 1:
            continue
        end = skip_string(text, tick)
        pairs, unreadable = _flatten_decls(text[tick + 1:max(tick + 1, end - 1)])
        decls: list[Decl] = []
        for prop, value in pairs:
            decls.extend(decl_from_css(prop, value))
        if not decls and not unreadable:
            continue
        out.append(StyledDef(
            name=m.group(1),
            # `styled(Card)` extends another component; its own tag is unknown,
            # so it is recorded as a plain box rather than guessed at.
            tag=(m.group(2) or "div").lower(),
            decls=decls,
            line=1 + text.count("\n", 0, m.start()),
            start=m.start(),
            unreadable=unreadable,
        ))
    return out


# ------------------------------------------------------------------ resolving
def _members(raw: str, local: str) -> list[str]:
    """Class names reached through ``local`` in one attribute value."""
    pattern = re.compile(
        rf"\b{re.escape(local)}\s*(?:\.\s*([A-Za-z_$][\w$]*)"
        rf"|\[\s*['\"]([^'\"\]]+)['\"]\s*\])"
    )
    return [m.group(1) or m.group(2) for m in pattern.finditer(raw)]


def _class_attr_raw(el: Element) -> str:
    if not el.class_attr:
        return ""
    return el.attrs.get(el.class_attr, "")


def resolve_styles(docs: list[Document]) -> None:
    """Wire CSS Modules and CSS-in-JS into the element tree, in place.

    Cross-file by nature — a module stylesheet is a different document from the
    component that imports it — so this runs once after the walk, next to
    :func:`~.components.resolve`.
    """
    by_path: dict[str, Document] = {}
    by_name: dict[str, list[Document]] = {}
    for doc in docs:
        if doc.kind != "style" or ".module." not in doc.rel_path:
            continue
        by_path[_normalize(doc.rel_path)] = doc
        by_name.setdefault(os.path.basename(doc.rel_path).lower(), []).append(doc)

    index: dict[str, dict[str, list[Decl]]] = {}
    for doc in docs:
        if doc.kind != "markup":
            continue
        doc.styled = scan_styled(doc.text)
        doc.unreadable_styles = sum(s.unreadable for s in doc.styled)

        imports = module_imports(doc.text)
        if not imports:
            continue
        bound: dict[str, dict[str, list[Decl]]] = {}
        for local, spec in imports.items():
            target = by_path.get(_resolve_spec(doc.rel_path, spec))
            if target is None:
                # Last resort: a unique file with that name. Ambiguous names are
                # left unresolved rather than attached to the wrong stylesheet —
                # a wrong attachment corrupts every distribution downstream.
                same = by_name.get(os.path.basename(spec).lower(), [])
                target = same[0] if len(same) == 1 else None
            if target is None:
                doc.unresolved_modules += 1
                continue
            key = _normalize(target.rel_path)
            if key not in index:
                index[key] = class_index(target.css_rules)
            bound[local] = index[key]

        if not bound:
            continue
        for el in doc.elements:
            raw = _class_attr_raw(el)
            if not raw:
                continue
            for local, table in bound.items():
                if local not in raw:
                    continue
                for name in _members(raw, local):
                    hit = table.get(name)
                    if hit:
                        el.decls.extend(hit)
                        el.module_classes.append(name)
