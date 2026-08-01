"""Vertical rhythm: the single most reliable tell in a generated page.

A designed page varies its band spacing by role — the hero breathes, a dense
comparison section tightens, two same-coloured bands merge. A generated page
gives every ``<section>`` the same ``py-20`` and every container the same
``max-w-7xl mx-auto px-4``, because there was no reason to make it otherwise.

So this module measures concentration, not values: what share of the page's
sections carry the *same* vertical padding, and how many distinct container
widths exist at all. Both are scale-free and both survive a project that uses
its own tokens — a token system with one band value is still one decision.
"""

from __future__ import annotations

from collections import Counter

from ..models import Axis, Document, Evidence, Observation
from .util import cap_evidence, dominant_share, evidence_for, styled_decls

# How deep to look for the band's padding. Generated markup routinely puts it on
# an inner container (`<section><div class="max-w-7xl mx-auto px-4 py-20">`), so
# reading only the section element would find nothing on the most templated
# pages of all — the exact opposite of the intended measurement.
_PADDING_REACH = 3
_MIN_SECTIONS = 4
_UNIFORM_AT = 0.6
_MAX_COLLAPSED = 2      # distinct band values above which rhythm exists
_GAP_UNIFORM_AT = 0.75
_MIN_GAPS = 4


def _vertical_padding(doc: Document, idx: int, reach: int = _PADDING_REACH) -> str:
    """The band padding of a section, searched through its first descendants."""
    stack = [(idx, 0)]
    while stack:
        i, depth = stack.pop(0)
        el = doc.elements[i]
        for prop in ("padding-y", "padding", "padding-top", "padding-bottom"):
            for d in el.rendered:
                if d.variant or d.axis is not Axis.SPACE or d.prop != prop:
                    continue
                return d.value
        if depth < reach:
            stack.extend((c, depth + 1) for c in el.children[:2])
    return ""


def section_rhythm(docs: list[Document]) -> tuple[list[str], list[Evidence]]:
    """Band padding value of every page section, with where each came from."""
    values: list[str] = []
    evidence: list[Evidence] = []
    for doc in docs:
        for idx in doc.sections:
            el = doc.elements[idx]
            if el.tag in ("nav", "header", "footer"):
                continue           # chrome, not a content band
            value = _vertical_padding(doc, idx)
            if not value:
                continue
            values.append(value)
            evidence.append(evidence_for(doc, el, f"py-{value}"))
    return values, evidence


def _collect(docs: list[Document], axis: Axis, prop: str
             ) -> tuple[list[str], list[Evidence]]:
    values: list[str] = []
    evidence: list[Evidence] = []
    for doc in docs:
        for el in doc.elements:
            for d in el.decls:
                if d.axis is axis and d.prop == prop and not d.variant:
                    values.append(d.value)
                    evidence.append(evidence_for(doc, el, d.raw))
    return values, evidence


def analyze(docs: list[Document]) -> tuple[list[Observation], float]:
    """Rhythm observations plus the SPACE axis repetition score (0..100)."""
    out: list[Observation] = []
    shares: list[float] = []

    bands, band_ev = section_rhythm(docs)
    if len(bands) >= _MIN_SECTIONS:
        value, share = dominant_share(bands)
        shares.append(share)
        distinct = len(set(bands))
        # Both gates are needed. A dominant share alone flags a page that uses
        # three band values and happens to reuse one of them twice — which is
        # exactly what this observation's own prescription asks for. "Collapsed"
        # means the page has one or two rhythms, not that it has a favourite.
        if share >= _UNIFORM_AT and distinct <= _MAX_COLLAPSED:
            n = sum(1 for b in bands if b == value)
            out.append(Observation(
                axis=Axis.SPACE,
                id="space.uniform_rhythm",
                title="Dikey ritim tek değere çökmüş",
                detail=(
                    f"{len(bands)} bölümün {n}'i aynı dikey boşluğu kullanıyor "
                    f"(py-{value}); sayfanın tamamında {distinct} farklı bant "
                    f"değeri var. Tasarlanmış bir sayfada bölüm boşluğu role "
                    f"göre değişir: hero geniş nefes alır, yoğun bölümler "
                    f"sıkışır, aynı zeminli ardışık bölümler birleşir. Tek "
                    f"değer, ritmin hiç düşünülmediğini gösterir — ve okuyucuya "
                    f"sayfanın her yerinin aynı önemde olduğunu söyler."
                ),
                severity=round(min(1.0, share), 3),
                stat=f"%{share * 100:.0f} aynı (py-{value})",
                evidence=cap_evidence([e for e in band_ev if e.value == f"py-{value}"]),
                prescription=(
                    "Bölümlere rol ver ve her role kendi ritmini yaz: hero için "
                    "en geniş, anlatı bölümleri için orta, yoğun/liste bölümleri "
                    "için dar. En az üç farklı bant değeri hedefle."
                ),
            ))

    widths, width_ev = _collect(docs, Axis.LAYOUT, "max-width")
    if len(widths) >= 3:
        value, share = dominant_share(widths)
        shares.append(share)
        distinct = len(set(widths))
        if distinct <= 2 and share >= 0.7:
            out.append(Observation(
                axis=Axis.SPACE,
                id="space.single_container",
                title="Tek container genişliği",
                detail=(
                    f"Sayfadaki {len(widths)} genişlik sınırının {distinct} "
                    f"farklı değeri var, baskın olan max-w-{value}. Her şeyin "
                    f"aynı kutuya girmesi sayfayı tek bir sütuna indirger; "
                    f"okuma ölçüsü, geniş medya ve tam genişlik kırılmaları "
                    f"farklı sınırlar ister."
                ),
                severity=round(min(1.0, share), 3),
                stat=f"{distinct} farklı genişlik",
                evidence=cap_evidence(width_ev),
                prescription=(
                    "En az üç ölçü tanımla: okuma ölçüsü (~65ch), içerik ölçüsü, "
                    "ve geniş/tam genişlik. Metin bloklarını okuma ölçüsüne, "
                    "grid'leri içerik ölçüsüne bağla."
                ),
            ))

    gaps, gap_ev = _collect(docs, Axis.SPACE, "gap")
    if len(gaps) >= _MIN_GAPS:
        value, share = dominant_share(gaps)
        shares.append(share)
        if share >= _GAP_UNIFORM_AT:
            out.append(Observation(
                axis=Axis.SPACE,
                id="space.uniform_gap",
                title="Tek boşluk değeri her grid'de",
                detail=(
                    f"{len(gaps)} grid/flex boşluğunun %{share * 100:.0f}'i "
                    f"gap-{value}. Yatay ve dikey boşluk aynı olduğunda ızgara "
                    f"kart tablosuna benzer; tasarlanmış ızgaralar genelde "
                    f"satır aralığını sütun aralığından geniş tutar."
                ),
                severity=round(min(1.0, share * 0.8), 3),
                stat=f"%{share * 100:.0f} gap-{value}",
                evidence=cap_evidence(gap_ev),
                prescription=(
                    "gap yerine gap-x / gap-y ayır ve satır aralığını sütun "
                    "aralığından belirgin şekilde büyük yap."
                ),
            ))

    repetition = 100.0 * (sum(shares) / len(shares)) if shares else 0.0
    return out, round(repetition, 1)


_MIN_SHARED_ROLES = 2
_MIN_SHARED_USAGES = 3


def shared_band_wrappers(docs: list[Document]) -> list[Observation]:
    """One component wrapping bands that need different rhythms.

    This is the observation the *transform* cannot act on, and saying so is the
    point. The tool's prescription for a collapsed rhythm is "give each band its
    role's spacing" — and on a componentised page there is one ``<Section>``
    carrying the padding for the hero, the features and the FAQ alike. Rewriting
    its class list gives all six bands the same new value, so the fix lands and
    the measurement does not move.

    Nothing here is a plan: it reads the *authored* tree, where the usages still
    exist, and reports which component serves how many roles. Splitting it is
    DOM work, which the transform is not allowed to do — and a limit the user
    can only otherwise discover by reading the diff.
    """
    from ..parse.components import _roots, sfc_component
    from .sections import ROLE_LABEL, classify

    roots: dict[str, tuple[Document, int]] = {}
    styled_roots: dict[str, tuple[Document, object]] = {}
    for doc in docs:
        for sd in doc.styled:
            styled_roots.setdefault(sd.name, (doc, sd))
    for doc in docs:
        sfc = sfc_component(doc)
        if sfc is not None:
            roots.setdefault(sfc[0], (doc, sfc[1]))
        for name, idx in _roots(doc).items():
            if name not in styled_roots:
                roots.setdefault(name, (doc, idx))

    usages: dict[str, list[tuple[str, Document, int]]] = {}
    for doc in docs:
        own = dict(_roots(doc))
        sfc = sfc_component(doc)
        if sfc is not None:
            own.setdefault(*sfc)
        for idx in doc.sections:
            el = doc.elements[idx]
            if not el.is_component or own.get(el.tag) == idx:
                continue
            if el.tag not in roots and el.tag not in styled_roots:
                continue
            usages.setdefault(el.tag, []).append((classify(doc, idx), doc, idx))

    out: list[Observation] = []
    for name, seen in sorted(usages.items()):
        roles = [r for r, _, _ in seen if r not in ("nav", "footer")]
        distinct = sorted(set(roles))
        if len(distinct) < _MIN_SHARED_ROLES or len(roles) < _MIN_SHARED_USAGES:
            continue
        anchor = _wrapper_anchor(roots, styled_roots, name)
        if anchor is None:
            continue          # it wraps bands but does not carry their rhythm
        def_doc, band_ev = anchor
        labels = ", ".join(ROLE_LABEL.get(r, r) for r in distinct)
        out.append(Observation(
            axis=Axis.SPACE,
            id="space.shared_band_wrapper",
            title=f"Bant ritmi tek bileşende toplanmış: <{name}>",
            detail=(
                f"`{name}` bileşeni {len(roles)} bölümü sarıyor ve bu bölümler "
                f"{len(distinct)} farklı role hizmet ediyor ({labels}). Dikey "
                f"ritim bu bileşenin kökünde tek bir sınıf listesi olarak "
                f"duruyor, dolayısıyla o listeye ne yazılırsa {len(roles)} "
                f"bandın hepsine aynı anda yazılır. **Aracın buraya "
                f"uygulayabileceği bir düzeltme yok:** dönüşüm yalnızca sınıf "
                f"listelerini değiştirir, bileşeni bölmek DOM işidir. "
                f"Bu yüzden bu sayfada role göre ritim verilemedi."
            ),
            severity=round(min(1.0, 0.45 + 0.1 * len(distinct)), 3),
            stat=f"{len(roles)} bant · {len(distinct)} rol · 1 sarmalayıcı",
            evidence=cap_evidence(
                [band_ev] + [evidence_for(d, d.elements[i], ROLE_LABEL.get(r, r))
                             for r, d, i in seen]),
            prescription=(
                f"`{name}`'ı role göre böl: bant boşluğunu bir prop'a bağla "
                f"(`<{name} rhythm=\"hero\">`) ya da hero/anlatı/yoğun için "
                f"ayrı sarmalayıcılar yaz. Sonra her kullanım kendi ritmini "
                f"alabilir — şu anda hepsi tek bir değeri paylaşmak zorunda."
            ),
        ))
    return out


_BAND_PROPS = ("padding-y", "padding", "padding-top", "padding-bottom")


def _is_band_padding(decls) -> bool:
    return any(d.axis is Axis.SPACE and not d.variant and d.prop in _BAND_PROPS
               for d in decls)


def _wrapper_anchor(roots, styled_roots, name):
    """``(document, evidence)`` for where a wrapper's band padding is written.

    ``None`` when the component wraps bands but does not carry their rhythm —
    then splitting it would not buy the page anything, and saying so would be a
    complaint about a component that is not in the way.
    """
    hit = roots.get(name)
    if hit is not None:
        doc, idx = hit
        frontier = [(idx, 0)]
        while frontier:
            i, depth = frontier.pop(0)
            if _is_band_padding(doc.elements[i].decls):
                return doc, evidence_for(doc, doc.elements[i], f"<{name}>")
            if depth < _PADDING_REACH:
                frontier.extend((c, depth + 1) for c in doc.elements[i].children[:2])
    hit = styled_roots.get(name)
    if hit is not None:
        doc, sd = hit
        if _is_band_padding(sd.decls):
            # A `styled.section` is even harder for the transform than a
            # componentised one: there is no class attribute to rewrite at all.
            return doc, next(
                (ev for d, ev in styled_decls(doc) if d.prop in _BAND_PROPS),
                evidence_for(doc, doc.elements[0], f"<{name}>"),
            )
    return None


def rhythm_values(docs: list[Document]) -> Counter:
    """Band-padding histogram — used by the transformer to pick new values."""
    bands, _ = section_rhythm(docs)
    return Counter(bands)
