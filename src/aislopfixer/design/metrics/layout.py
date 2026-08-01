"""Layout doctrine: symmetry, alignment, and whether the page ever breaks.

Three habits give a generated page away from across the room, before any text
is read:

* every grid has equal columns, usually three;
* every section header is centred;
* nothing ever escapes the container — no full-bleed band, no asymmetric split.

None of these is wrong on its own. A page that does all three, in every
section, has made one layout decision and repeated it, which is what the
measurements below report.
"""

from __future__ import annotations

from ..models import Axis, Document, Element, Evidence, Observation
from .util import cap_evidence, evidence_for

_HEADINGS = frozenset({"h1", "h2", "h3"})
_MIN_GRIDS = 2
_MIN_HEADINGS = 3
_CENTER_AT = 0.7
_MIN_SECTIONS_FOR_BREAK = 4

# Escapes from the single centred column. Any one of these is enough to show
# the layout was considered; their total absence across a whole site is the
# signal.
#
# ``w-full`` is deliberately absent. It means "fill your parent", which is what
# almost every block element in every codebase already does — counting it as an
# escape gave `nuxt-website` 3478 container breaks and handed a full structure
# bonus to every repository large enough to contain a button.
_BREAK_VALUES = {
    ("layout", "max-width"): {"none", "full", "screen"},
    ("layout", "width"): {"screen"},
}
# How far below a band an escape still counts as *that band's* escape. A break
# is a statement about the page's column; one made inside a card is not.
_BREAK_REACH = 2


def band_breaks(docs: list[Document]) -> int:
    """Escapes from the centred column made at band level, across the project."""
    found = 0
    for doc in docs:
        for idx in doc.sections:
            frontier = [(idx, 0)]
            while frontier:
                i, depth = frontier.pop(0)
                if _breaks_container(doc.elements[i]):
                    found += 1
                    break
                if depth < _BREAK_REACH:
                    frontier.extend((c, depth + 1)
                                    for c in doc.elements[i].children[:4])
    return found


def _grid_containers(docs: list[Document]) -> list[tuple[Document, Element, str]]:
    """Every element that establishes a grid, with its column count."""
    out: list[tuple[Document, Element, str]] = []
    for doc in docs:
        for el in doc.elements:
            cols = [d for d in el.decls if d.axis is Axis.LAYOUT and d.prop == "grid-cols"]
            if not cols:
                continue
            # The base value if there is one, otherwise the widest breakpoint —
            # `grid-cols-1 md:grid-cols-3` is a three-column grid.
            widest = max(cols, key=lambda d: (_num(d.value), bool(d.variant)))
            out.append((doc, el, widest.value))
    return out


def _num(value: str) -> int:
    return int(value) if value.isdigit() else 0


def _uneven_tracks(value: str) -> bool:
    """True for a track list whose columns are not all the same width.

    ``grid-template-columns: 7fr 4fr`` is an asymmetric grid stated directly,
    with no child spanning anything. Reading only ``col-span`` found asymmetry
    in utility projects and missed it in every CSS one — the same design,
    scored differently for how it was written.

    The utility spelling of that track list is ``grid-cols-[7fr_4fr]``: an
    escape hatch, brackets and all, with underscores where the CSS has spaces.
    Splitting the raw value on whitespace found one track there and called the
    grid symmetric — the same asymmetry, missed in the other dialect this time.
    """
    tracks = value.strip("[]").replace("_", " ").split()
    return len(tracks) > 1 and len(set(tracks)) > 1


def _has_span_variety(doc: Document, el: Element) -> bool:
    """True when the grid's children do not all occupy one column."""
    for d in el.decls:
        if d.axis is Axis.LAYOUT and d.prop == "grid-cols" and _uneven_tracks(d.value):
            return True
    spans = set()
    for ci in el.children:
        child = doc.elements[ci]
        found = [d.value for d in child.decls
                 if d.axis is Axis.LAYOUT and d.prop in ("col-span", "col-start")]
        spans.add(found[0] if found else "1")
    return len(spans) > 1


def _breaks_container(el: Element) -> bool:
    for d in el.decls:
        allowed = _BREAK_VALUES.get((d.axis.value, d.prop))
        if allowed and d.value in allowed:
            return True
    return False


def analyze(docs: list[Document]) -> tuple[list[Observation], float]:
    """Layout observations plus the LAYOUT axis repetition score (0..100)."""
    out: list[Observation] = []
    shares: list[float] = []

    grids = _grid_containers(docs)
    if len(grids) >= _MIN_GRIDS:
        symmetric = [(d, e, c) for d, e, c in grids if not _has_span_variety(d, e)]
        share = len(symmetric) / len(grids)
        shares.append(share)
        if share >= 0.9:
            triads = [g for g in grids if g[2] == "3"]
            extra = (
                f" Bunların {len(triads)} tanesi üç sütunlu — özellik/fiyat/"
                f"yorum üçlüsü şablonun imzası."
                if len(triads) >= 2 else ""
            )
            out.append(Observation(
                axis=Axis.LAYOUT,
                id="layout.symmetric_grids",
                title="Bütün ızgaralar eşit sütunlu",
                detail=(
                    f"{len(grids)} ızgaranın {len(symmetric)}'i eşit genişlikte "
                    f"sütunlardan oluşuyor; hiçbir çocuk sütun atlamıyor."
                    f"{extra} Eşit ızgara içeriğin hepsinin aynı ağırlıkta "
                    f"olduğunu söyler — ki hiçbir sayfada doğru değildir."
                ),
                severity=round(min(1.0, share), 3),
                stat=f"{len(symmetric)}/{len(grids)} simetrik",
                evidence=cap_evidence([evidence_for(d, e, f"grid-cols-{c}")
                                       for d, e, c in symmetric]),
                prescription=(
                    "En az bir ızgarayı asimetrik yap: 12 sütunlu bir taban "
                    "üzerinde ilk kartı col-span-7, diğerlerini col-span-5 gibi "
                    "dağıt. Hangi içeriğin daha önemli olduğunu düzenle söyle."
                ),
            ))

    centered, headings = _heading_alignment(docs)
    if len(headings) >= _MIN_HEADINGS:
        share = len(centered) / len(headings)
        shares.append(share)
        if share >= _CENTER_AT:
            out.append(Observation(
                axis=Axis.LAYOUT,
                id="layout.center_monoculture",
                title="Her başlık ortalanmış",
                detail=(
                    f"{len(headings)} bölüm başlığının {len(centered)}'i "
                    f"ortalanmış. Ortalanmış metin kısa satırlarda işe yarar; "
                    f"her bölümde tekrarlandığında sayfa bir sunum slaytı "
                    f"dizisine döner ve okuyucunun gözü sol kenar boyunca "
                    f"tutunacak bir hat bulamaz."
                ),
                severity=round(min(1.0, share), 3),
                stat=f"%{share * 100:.0f} ortalı",
                evidence=cap_evidence(centered),
                prescription=(
                    "Hero dışındaki bölüm başlıklarını sola hizala ve açıklama "
                    "metnini okuma ölçüsüyle (max-w-[38ch] gibi) sınırla."
                ),
            ))

    total_sections = sum(len(doc.sections) for doc in docs)
    if total_sections >= _MIN_SECTIONS_FOR_BREAK:
        breaks = [
            evidence_for(doc, el)
            for doc in docs for el in doc.elements if _breaks_container(el)
        ]
        asymmetric = any(_has_span_variety(d, e) for d, e, _ in grids)
        if not breaks and not asymmetric:
            shares.append(1.0)
            out.append(Observation(
                axis=Axis.LAYOUT,
                id="layout.no_break",
                title="Sayfa hiç kırılmıyor",
                detail=(
                    f"{total_sections} bölümün hiçbiri container'ın dışına "
                    f"çıkmıyor ve hiçbir ızgara asimetrik değil. Ortalanmış "
                    f"tek sütun, baştan sona. Bir sayfaya ritim veren şey "
                    f"tam da bu kırılmalardır: tam genişlik bir görsel, kenara "
                    f"taşan bir kart, iki farklı ölçü."
                ),
                severity=0.75,
                stat="0 kırılma",
                evidence=[],
                prescription=(
                    "En az bir tam genişlik bandı (görsel, alıntı ya da veri "
                    "şeridi) ve bir asimetrik bölüm ekle."
                ),
            ))

    repetition = 100.0 * (sum(shares) / len(shares)) if shares else 0.0
    return out, round(repetition, 1)


def _heading_alignment(docs: list[Document]) -> tuple[list[Evidence], list[Evidence]]:
    """``(centered headings, all headings)`` as evidence lists.

    A heading counts as centred when the alignment is on the heading itself or
    on an ancestor — ``text-center`` on the section wrapper is how generated
    markup nearly always does it.
    """
    centered: list[Evidence] = []
    every: list[Evidence] = []
    for doc in docs:
        for el in doc.elements:
            if el.tag not in _HEADINGS:
                continue
            ev = evidence_for(doc, el, el.own_text[:60])
            every.append(ev)
            node = el
            hops = 0
            while node is not None and hops < 4:
                if any(d.prop == "text-align" and d.value == "text-center"
                       for d in node.decls):
                    centered.append(ev)
                    break
                node = doc.elements[node.parent] if node.parent >= 0 else None
                hops += 1
    return centered, every
