"""Concrete single-property tells that sit under the aggregate scores.

The vocabulary metric says an axis has no decisions; these say *which* decision
is missing, which is what makes a report actionable. Two shapes of tell:

* **monoculture** — a property used many times with exactly one value. One
  radius on forty elements is not a shape language, it is a default nobody
  changed.
* **absence** — a property that a designed page always tunes and this one never
  does. Display type without any tracking or line-height adjustment is the
  clearest example: every real typographic decision leaves a trace, and no
  trace means no decision.
"""

from __future__ import annotations

import re
from collections import Counter

from ..models import Axis, Document, Element, Evidence, Observation, Origin
from .util import cap_evidence, evidence_for, styled_decls

# (axis, prop, minimum uses, title, detail, prescription)
_MONOCULTURE: list[tuple[Axis, str, int, str, str, str]] = [
    (Axis.SHAPE, "radius", 6, "Tek köşe yarıçapı",
     "Projedeki {n} yuvarlatma kullanımının hepsi aynı değerde ({v}). "
     "Biçim dili olan bir arayüzde konteyner, kontrol ve rozet farklı "
     "yarıçaplar taşır; tek değer, köşelerin hiç düşünülmediğini gösterir.",
     "Üç kademeli bir yarıçap dili tanımla: konteyner (geniş), kontrol (orta), "
     "rozet/etiket (tam yuvarlak) — ve bazı yüzeyleri keskin bırak."),
    (Axis.MATERIAL, "shadow", 4, "Tek gölge katmanı",
     "{n} yükseltme kullanımının hepsi aynı gölge ({v}). Gölge derinliği "
     "anlatır; tek değer her şeyin aynı düzlemde olduğunu, yani derinliğin "
     "hiç kullanılmadığını söyler.",
     "Yükseklik katmanları tanımla (yüzey / kalkık / yüzen) ve her kartı "
     "kalkık yapma; gölgeyi yalnızca gerçekten üstte olan şeye ver."),
    (Axis.MOTION, "duration", 3, "Tek geçiş süresi",
     "{n} geçişin hepsi {v}ms. Renk değişimi ile düzen değişimi aynı sürede "
     "olduğunda hareket bilgi taşımaz, sadece gecikme yaratır.",
     "Süreyi role bağla: renk/opaklık 120–160ms, boyut/konum 220–320ms, "
     "sayfa geçişleri daha uzun. Kendi easing eğrini tanımla."),
]

_GLASS = re.compile(r"^backdrop-blur")
_TRANSITION_ALL_MIN = 3
_DISPLAY_MIN = 3


def _uses(docs: list[Document], axis: Axis, prop: str
          ) -> tuple[list[str], list[Evidence]]:
    """Every use of one property, from markup *and* stylesheets.

    Stylesheets have to be included or a project that declares its second font
    family, third radius or fourth shadow in CSS reads as a monoculture — the
    exact projects that did the work would be the ones accused of skipping it.
    """
    from ..parse.css import decl_from_css

    values: list[str] = []
    evidence: list[Evidence] = []
    for doc in docs:
        for el in doc.elements:
            for d in el.decls:
                if d.axis is axis and d.prop == prop and not d.variant:
                    values.append(d.value)
                    evidence.append(evidence_for(doc, el, d.raw or d.value))
        for d, ev in styled_decls(doc):
            if d.axis is axis and d.prop == prop and not d.variant:
                values.append(d.value)
                evidence.append(ev)
        for rule in doc.css_rules:
            for css_prop, css_value in rule.decls.items():
                for d in decl_from_css(css_prop, css_value):
                    if d.axis is axis and d.prop == prop:
                        values.append(d.value)
    return values, evidence


def analyze(docs: list[Document]) -> tuple[list[Observation], dict[Axis, float]]:
    """Property-level tells plus their per-axis repetition contribution."""
    out: list[Observation] = []
    shares: dict[Axis, list[float]] = {}

    for axis, prop, min_uses, title, detail, fix in _MONOCULTURE:
        values, evidence = _uses(docs, axis, prop)
        if len(values) < min_uses:
            continue
        distinct = set(values)
        shares.setdefault(axis, []).append(1.0 if len(distinct) == 1 else
                                           1.0 / len(distinct))
        if len(distinct) != 1:
            continue
        value = next(iter(distinct)) or "varsayılan"
        out.append(Observation(
            axis=axis, id=f"{axis.value}.mono_{prop}", title=title,
            detail=detail.format(n=len(values), v=value),
            severity=round(min(1.0, 0.5 + len(values) / 40.0), 3),
            stat=f"{len(values)} kullanım · 1 değer",
            evidence=cap_evidence(evidence),
            prescription=fix,
        ))

    out.extend(_mono_type(docs, shares))
    out.extend(_no_type_choice(docs, shares))
    out.extend(_untuned_display(docs, shares))
    out.extend(_transition_all(docs, shares))
    out.extend(_uniform_card(docs, shares))
    return out, {a: sum(v) / len(v) * 100.0 for a, v in shares.items() if v}


# Typography's monoculture measure. Every other axis had one — radius, shadow,
# duration — and the type axis's repetition came from two *absence* tests only,
# both of which stand down when the project's config tunes its ramp. The result
# was an axis that discriminated backwards: `cruip-landing`, whose forty
# headings are written with two sizes, scored 0 type repetition, while
# `solid-site` scored 77.8.
#
# Same shape and the same two gates as `space.uniform_rhythm`: a dominant share
# alone would flag a page that has three sizes and happens to reuse one of them,
# which is what the prescription asks for. "Collapsed" means the page has one or
# two values, not that it has a favourite.
_TYPE_MONO: tuple[tuple[str, int, int, str, str, str], ...] = (
    ("font-size", 10, 2, "Yazı ölçeği tek değere çökmüş",
     "Metin taşıyan {n} elemanın {k}'i aynı boyutta ({v}); sayfanın tamamında "
     "{d} farklı boyut var. Bir tipografik ölçek hiyerarşi kurar: başlık, ara "
     "başlık, gövde, yardımcı metin ayrı adımlardır. Tek adım, okuyucuya "
     "sayfadaki her cümlenin aynı ağırlıkta olduğunu söyler.",
     "En az üç adımlı bir ölçek kur ve rollere bağla — display, bölüm başlığı, "
     "gövde, meta. Adımlar arasında gözle görülür bir oran bırak."),
    ("font-weight", 8, 2, "Tek yazı ağırlığı",
     "Ağırlık bildiren {n} elemanın {k}'i aynı ağırlıkta ({v}); {d} farklı "
     "değer var. Ağırlık, boyut büyütmeden vurgu kurmanın yoludur; tek değer "
     "onu kullanılmamış bırakır.",
     "Gövde ile başlık ağırlığını ayır ve üçüncü bir adım (yarı kalın ya da "
     "hafif) tanımla; vurguyu her yerde boyutla kurma."),
    ("line-height", 6, 2, "Tek satır aralığı",
     "Satır aralığı bildiren {n} elemanın {k}'i aynı değerde ({v}); {d} farklı "
     "değer var. Bir başlık ile bir paragraf aynı satır aralığını istemez: "
     "büyük punto sıkışır, gövde nefes ister.",
     "Satır aralığını punto ile birlikte ayarla: display için 1.0–1.15, gövde "
     "için 1.5–1.7. Ölçeğini yazıyorsan her adıma kendi aralığını ver."),
)
_MONO_AT = 0.7          # dominant share that reads as "collapsed"


def _mono_type(docs: list[Document],
               shares: dict[Axis, list[float]]) -> list[Observation]:
    """Typography used many times with one size, one weight, one leading."""
    from .util import dominant_share

    out: list[Observation] = []
    for prop, min_uses, max_distinct, title, detail, fix in _TYPE_MONO:
        values, evidence = _uses(docs, Axis.TYPE, prop)
        if len(values) < min_uses:
            continue
        value, share = dominant_share(values)
        shares.setdefault(Axis.TYPE, []).append(share)
        distinct = len(set(values))
        if share < _MONO_AT or distinct > max_distinct:
            continue
        n = sum(1 for v in values if v == value)
        out.append(Observation(
            axis=Axis.TYPE, id=f"type.mono_{prop.replace('-', '_')}",
            title=title,
            detail=detail.format(n=len(values), k=n, v=value or "varsayılan",
                                 d=distinct),
            severity=round(min(1.0, share), 3),
            # The measured number, not the threshold: a reader can check this
            # against the page, and cannot check "above what is expected".
            stat=f"%{share * 100:.0f} aynı ({value or 'varsayılan'})",
            evidence=cap_evidence([e for e in evidence if e.value.endswith(value)]
                                  or evidence),
            prescription=fix,
        ))
    return out


def _no_type_choice(docs: list[Document],
                    shares: dict[Axis, list[float]]) -> list[Observation]:
    """No font family declared anywhere — the framework picked the typeface.

    Deliberately an *absence* test rather than a monoculture one. A page that
    pairs a declared serif display with the default sans body has two families
    and only one declaration, so counting declarations would accuse exactly the
    pages that made the choice.
    """
    families, _ = _uses(docs, Axis.TYPE, "font-family")
    text_elements = sum(
        1 for doc in docs for el in doc.elements
        if any(d.axis is Axis.TYPE for d in el.decls)
    )
    # A `fontFamily` in tailwind.config is a declaration; it just is not a
    # declaration on an element. Reading only elements told a project that wrote
    # its own type stack that it had never chosen a typeface — the same mistake
    # `parse/theme.py` exists to stop the vocabulary metric making.
    if _theme_declares(docs, "font-family") or families or text_elements < 6:
        return []
    shares.setdefault(Axis.TYPE, []).append(1.0)
    return [Observation(
        axis=Axis.TYPE,
        id="type.no_type_choice",
        title="Yazı tipi hiç seçilmemiş",
        detail=(
            f"{text_elements} tipografik elemanın hiçbirinde bir yazı ailesi "
            f"belirtilmemiş; sayfa framework'ün varsayılan sistem yığınıyla "
            f"çalışıyor. Tipografi bir arayüzün sesidir ve bu sayfada o ses "
            f"hiç seçilmemiş — bugün üretilen her sayfayla aynı."
        ),
        severity=0.8,
        stat="0 aile bildirimi",
        evidence=[],
        prescription=(
            "En az bir aile seç ve bildir: başlık için karakterli bir kesit, "
            "gövde için okunaklı bir kesit. Sistem yığınında kalacaksan bile "
            "bunu açıkça yaz ve ağırlıklarını ayarla."
        ),
    )]


def _theme_declares(docs: list[Document], group: str) -> bool:
    """True when the project's own theme config supplies this scale."""
    for doc in docs:
        theme = doc.theme
        if theme is not None and group in getattr(theme, "groups", ()):
            return True
    return False


_DISPLAY_SIZES = frozenset({"3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl"})


def _untuned_display(docs: list[Document],
                     shares: dict[Axis, list[float]]) -> list[Observation]:
    """Big type with no tracking and no leading — the untouched default ramp."""
    display: list[tuple[Document, Element]] = []
    tuned = 0
    for doc in docs:
        theme = doc.theme
        for el in doc.elements:
            sizes = [d for d in el.decls
                     if d.axis is Axis.TYPE and d.prop == "font-size"]
            if not any(d.value in _DISPLAY_SIZES for d in sizes):
                continue
            display.append((doc, el))
            # A size whose own scale entry states a leading or a tracking is
            # tuned; there is simply no trace on the element, because the
            # decision was made once, in the config, which is the better place
            # to make it. Read from the config rather than assumed: a project
            # that redefined `fontSize` with bare values still gets the tell.
            if (any(d.axis is Axis.TYPE
                    and d.prop in ("letter-spacing", "line-height")
                    for d in el.decls)
                    or (theme is not None
                        and any(theme.tunes(d.value) for d in sizes))):
                tuned += 1
    # Below the gate the share is *not* recorded either. Two large headings with
    # no tracking are not evidence of an untuned ramp — the observation itself
    # says so by refusing to fire — and appending a full repetition share for
    # them made a hand-written page read as typographically uniform.
    if len(display) < _DISPLAY_MIN:
        return []
    if tuned:
        shares.setdefault(Axis.TYPE, []).append(
            max(0.0, 1.0 - tuned / len(display)))
        return []
    shares.setdefault(Axis.TYPE, []).append(1.0)
    return [Observation(
        axis=Axis.TYPE,
        id="type.untuned_display",
        title="Büyük başlıklar hiç ayarlanmamış",
        detail=(
            f"{len(display)} büyük başlığın hiçbirinde harf aralığı ya da "
            f"satır yüksekliği ayarı yok. Tailwind'in text-4xl/5xl "
            f"varsayılanları gövde metni için ayarlanmış satır yüksekliğiyle "
            f"gelir; display boyutlarda bu satırları birbirinden ayırır ve "
            f"harfleri gevşek bırakır. Bir tipografi kararı verilmiş olsaydı "
            f"burada bir iz olurdu."
        ),
        severity=0.7,
        stat=f"{len(display)} başlık · 0 ayar",
        evidence=cap_evidence([evidence_for(d, e, e.own_text[:50])
                               for d, e in display]),
        prescription=(
            "Display boyutlara sıkı satır yüksekliği (1.0–1.1) ve negatif "
            "harf aralığı (-0.02em civarı) ver; gövde metnini ayrı ayarla."
        ),
    )]


def _transition_all(docs: list[Document],
                    shares: dict[Axis, list[float]]) -> list[Observation]:
    """``transition-all`` repeated — motion applied without deciding to what."""
    hits: list[Evidence] = []
    for doc in docs:
        for el in doc.elements:
            if any(d.axis is Axis.MOTION and d.value == "transition-all"
                   for d in el.decls):
                hits.append(evidence_for(doc, el, "transition-all"))
    if len(hits) < _TRANSITION_ALL_MIN:
        return []
    shares.setdefault(Axis.MOTION, []).append(1.0)
    return [Observation(
        axis=Axis.MOTION,
        id="motion.transition_all",
        title="Her yerde transition-all",
        detail=(
            f"{len(hits)} elemanda transition-all var. Bu, “neyin animasyon "
            f"olacağına karar vermedim” demenin kısa yolu: düzen özellikleri "
            f"de animasyona girer, hover'da yeniden yerleşim tetiklenir ve "
            f"hareket bilgi taşımaz."
        ),
        severity=0.6,
        stat=f"{len(hits)} kullanım",
        evidence=cap_evidence(hits),
        prescription=(
            "transition-all yerine neyin değiştiğini yaz: transition-colors, "
            "transition-transform. Süreyi ve easing'i role göre ayır."
        ),
    )]


def _uniform_card(docs: list[Document],
                  shares: dict[Axis, list[float]]) -> list[Observation]:
    """One surface recipe — same radius + border + shadow — on every panel."""
    recipes: list[tuple[Document, Element, str]] = []
    for doc in docs:
        for el in doc.elements:
            radius = [d.value for d in el.decls if d.axis is Axis.SHAPE and d.prop == "radius"]
            border = [d.value for d in el.decls if d.axis is Axis.SHAPE and d.prop == "border"]
            shadow = [d.value for d in el.decls if d.axis is Axis.MATERIAL and d.prop == "shadow"]
            if not radius or not (border or shadow):
                continue
            recipes.append((doc, el, f"r={radius[0]}|b={border[0] if border else '-'}"
                                     f"|s={shadow[0] if shadow else '-'}"))
    if len(recipes) < 4:
        return []
    counts = Counter(r for _, _, r in recipes)
    recipe, n = counts.most_common(1)[0]
    share = n / len(recipes)
    shares.setdefault(Axis.MATERIAL, []).append(share)
    if share < 0.8:
        return []
    return [Observation(
        axis=Axis.MATERIAL,
        id="material.uniform_card",
        title="Tek yüzey reçetesi",
        detail=(
            f"{len(recipes)} panelin {n}'i aynı yüzey tarifini kullanıyor "
            f"({recipe}). Yarıçap + kenarlık + gölge üçlüsü her yerde aynı "
            f"olduğunda içerik hiyerarşisi kaybolur: bir fiyat kartı ile bir "
            f"dipnot kutusu aynı ağırlıkta görünür."
        ),
        severity=round(min(1.0, share), 3),
        stat=f"%{share * 100:.0f} aynı tarif",
        evidence=cap_evidence([evidence_for(d, e, r) for d, e, r in recipes
                               if r == recipe]),
        prescription=(
            "En az iki yüzey tanımla: taşıyıcı (kenarlıksız, gölgesiz, "
            "yalnızca zemin farkı) ve vurgulu (kenarlık ya da gölge). Her "
            "kutuyu kart yapma."
        ),
    )]


def stack_of(docs: list[Document]) -> set[str]:
    """Which styling systems the project actually uses — shown in the report."""
    stack: set[str] = set()
    for doc in docs:
        if doc.kind == "style":
            stack.add("css")
        if any(d.origin is Origin.TOKEN for el in doc.elements for d in el.decls):
            stack.add("tokens")
        if any(el.classes for el in doc.elements):
            stack.add("tailwind")
        if any(el.inline_style for el in doc.elements):
            stack.add("inline")
        if doc.styled:
            stack.add("css-in-js")
        if any(el.module_classes for el in doc.elements):
            stack.add("modules")
        if any(_GLASS.match(d.prop) for el in doc.elements for d in el.decls):
            stack.add("glass")
    return stack
