"""Which documents the measurement is *about*, when a project holds more than one site.

``next-saas-stripe-starter`` is the case that forced this. It is not a landing
template, it is a whole application with a marketing route inside it: 1 505
elements, most of them from the dashboard. The label describes
``app/(marketing)`` and the scan describes the repository, so the number is
right about something nobody asked about.

``Project.subdir`` — scan a smaller root — could not fix it. Pointing the scan
at the route leaves ``components/`` outside, and then component expansion
collapses: the tool measures the marketing route as eleven empty tags.

So the split is **root versus scope**. The whole tree is read: every component,
every stylesheet, the theme config. What the scope filters is which documents
the *measurement is about*, and a document is about the scope when

* its path is under one of the scope prefixes, or
* it defines a component that a document already in scope renders,
  transitively — a marketing page's ``<Hero>`` belongs to the marketing route
  wherever the repository keeps it, and a dashboard's ``<DataTable>`` does not.

Stylesheets are always in scope. A CSS file has no route; it applies to
whatever loads it, and dropping one would take the project's own tokens out of
the vocabulary of the pages that use them.

This is a scope, never a threshold. With no scope given nothing is filtered and
the numbers are exactly what they were.
"""

from __future__ import annotations

from .models import Document

_MAX_ROUNDS = 12       # component nesting depth; deeper is a cycle, not a tree


def normalise(prefixes) -> tuple[str, ...]:
    """Scope prefixes as forward-slash paths with no leading or trailing slash."""
    out = []
    for raw in prefixes or ():
        cleaned = str(raw).replace("\\", "/").strip().strip("/")
        if cleaned:
            out.append(cleaned)
    return tuple(dict.fromkeys(out))


def under(rel_path: str, prefixes: tuple[str, ...]) -> bool:
    """True when ``rel_path`` sits at or below any of ``prefixes``."""
    norm = rel_path.replace("\\", "/")
    return any(norm == p or norm.startswith(p + "/") for p in prefixes)


def _defines(doc: Document) -> set[str]:
    """Component names this document defines.

    Read through the same scanners :mod:`.parse.components` uses rather than a
    regex over the file: a loose ``const [A-Z]…`` match pulled a docs sidebar
    and a pile of ``.mdx`` into a marketing route's scope, because a file that
    names a capitalised local is not a file that exports a component.
    """
    from .parse.components import _roots, sfc_component

    names = {sd.name for sd in doc.styled}
    names.update(_roots(doc))
    sfc = sfc_component(doc)
    if sfc is not None:
        names.add(sfc[0])
    return names


def _uses(doc: Document) -> set[str]:
    """Component names this document renders — usages the parser actually saw."""
    return {el.tag for el in doc.elements if el.is_component}


def select(docs: list[Document], prefixes) -> list[Document]:
    """The documents in scope, in the order they were given.

    Returns ``docs`` unchanged when no scope is set — the common path stays the
    path it always was, so a scan with no scope cannot drift from one with the
    feature absent.
    """
    prefixes = normalise(prefixes)
    if not prefixes:
        return docs

    markup = [d for d in docs if d.kind == "markup"]
    defines = {name: d.rel_path for d in markup for name in _defines(d)}
    keep = {d.rel_path for d in markup if under(d.rel_path, prefixes)}
    by_path = {d.rel_path: d for d in markup}

    frontier = set(keep)
    for _ in range(_MAX_ROUNDS):
        wanted: set[str] = set()
        for path in frontier:
            for name in _uses(by_path[path]):
                target = defines.get(name)
                if target is not None and target not in keep:
                    wanted.add(target)
        if not wanted:
            break
        keep |= wanted
        frontier = wanted

    return [d for d in docs if d.kind != "markup" or d.rel_path in keep]


def note(prefixes, docs: list[Document], kept: list[Document]) -> str:
    """One line naming the scope and what it cost, or ``""`` when unscoped."""
    prefixes = normalise(prefixes)
    if not prefixes:
        return ""
    all_markup = sum(1 for d in docs if d.kind == "markup")
    in_markup = sum(1 for d in kept if d.kind == "markup")
    return (
        f"Kapsam sınırlandı: yalnızca {', '.join(prefixes)} altındaki sayfalar "
        f"ölçüldü ({in_markup}/{all_markup} işaretleme dosyası — bu sayfaların "
        f"kullandığı bileşenler nerede dururlarsa dursunlar dahil). Ağacın "
        f"tamamı okundu; süzülen şey ölçümün *neyi anlattığı*, ne kadarını "
        f"gördüğü değil."
    )
