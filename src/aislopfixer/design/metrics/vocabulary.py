"""Decision density: how many independent design decisions a project contains.

This is headline axis 1, and the reason the tool can flag a page that contains
no forbidden token. A generated landing page uses a *large number of classes*
drawn from a *tiny number of decisions* — ``py-20 px-4 mb-4 gap-8 text-4xl
rounded-2xl shadow-sm`` is seven classes and, on the measure below, about one
and a half decisions, because every value is one the framework already chose.

The count is deliberately weighted by :class:`~aislopfixer.design.models.Origin`
rather than by raw distinctness. Distinctness alone rewards volume: a page that
sprinkles ``mt-1 mt-2 mt-3 mt-5 mt-7`` would out-score a page with a real
three-step spacing system. What matters is whether anyone *chose*, and the
origin of a value is the only offline evidence of that.

Normalization is against the *vocabulary the project actually uses*, not against
its element count. An earlier version scaled the target by page size and
saturated it at 120 elements — but the thing being counted, the number of
distinct values, keeps growing past that, so every project bigger than a demo
page saturated its own score. ``bench/field.md`` showed it plainly: eight
landing-page templates, all eight graded "designed", every one of them simply
larger than the corpus. The question is not *how many* decisions a project
carries, it is *what share of its vocabulary was chosen* — and that question has
the same answer at forty elements and at ten thousand.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from ..models import Axis, AxisScore, Decl, Document, Evidence, Observation, Origin
from ..parse.theme import group_for as theme_group_for
from .util import cap_evidence, evidence_for

# Weight expected *per distinct vocabulary entry*. A project whose every value
# is one the framework chose carries 0.25 per entry however many entries it has,
# so it lands at 0.25/VOCAB_TARGET of the axis — the same score at any size.
# Calibrated jointly on the eleven corpus cases and the fourteen field
# repositories; tuning against either side alone is how the saturation bug got
# in.
VOCAB_TARGET = 1.25
# The floor under a tiny vocabulary. Three authored values are not a type system,
# and without this a page that declares one arbitrary colour would score 100 on
# colour. Expressed in the same weighted units as the goal.
AXIS_FLOOR: dict[Axis, float] = {
    Axis.TYPE: 7.0,
    Axis.COLOR: 6.0,
    Axis.SPACE: 7.0,
    Axis.SHAPE: 3.0,
    Axis.LAYOUT: 7.0,
    Axis.MATERIAL: 3.0,
    Axis.MOTION: 3.0,
}

# A variant (`md:`, `hover:`) is real design work, but it is derived from a base
# decision rather than independent of it — counting it at full weight let a page
# with one colour and six breakpoints outscore a page with six colours. It is
# discounted on *both* sides of the ratio, so a responsive project is neither
# rewarded nor punished for being responsive.
VARIANT_WEIGHT = 0.5


# ------------------------------------------------------- one scale, one decision
# Writing a ten-step colour ramp is one decision, not ten. Counting each step as
# its own ``TOKEN`` handed any project that ships a config a full axis for free —
# and every landing-page template ships a config. The steps are therefore folded
# into a single entry worth ``TOKEN + log(n)``: more than one decision, because a
# considered ramp *is* more work than a single value, and far less than ten.
#
# Only genuinely-stepped names fold. ``--color-surface`` and ``--radius-panel``
# are roles, not scales, and stay one decision each.
_SIZE_STEPS = frozenset({
    "3xs", "2xs", "xs", "sm", "md", "base", "lg", "xl",
    "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl",
})
_NUMERIC = re.compile(r"^\d+(?:\.\d+)?$")
_VAR_IN_VALUE = re.compile(r"var\(\s*(--[\w-]+)")
GROUP_BASE = Origin.TOKEN.decision_weight


def _strip_step(name: str) -> str:
    """``--color-brand-500`` → ``--color-brand``; an unstepped name is itself."""
    head, sep, tail = name.rpartition("-")
    if not sep or not head:
        return name
    if _NUMERIC.match(tail) or tail in _SIZE_STEPS:
        return head
    return name


def decision_group(axis: Axis, prop: str, value: str, origin: Origin,
                   theme) -> str | None:
    """The scale this value is a step of, or ``None`` when it stands alone.

    Everything that is not a project token stands alone: a literal someone typed
    and an arbitrary value someone measured off the screen are each their own
    decision no matter how many of them there are.
    """
    if origin is not Origin.TOKEN:
        return None
    if prop.startswith("--"):
        stem = _strip_step(prop)
        return f"ramp:{stem}" if stem != prop else None
    ref = _VAR_IN_VALUE.search(value)
    if ref is not None:
        stem = _strip_step(ref.group(1))
        return f"ramp:{stem}" if stem != ref.group(1) else None
    base = value.split("/", 1)[0]
    if theme is not None and theme.redefines(axis, prop, value):
        group = theme_group_for(axis, prop)
        if group is None:
            return None
        # A redefined colour *family* is one ramp; a redefined `fontSize` scale
        # is one scale whatever its steps are called.
        return (f"scale:color:{_strip_step(base)}" if group == "color"
                else f"scale:{group}")
    if axis is Axis.COLOR:
        stem = _strip_step(base)
        return f"ramp:color:{stem}" if stem != base else None
    return None


# Structural decisions carry no unusual *value* — they are made entirely out of
# framework defaults — yet they are the decisions a viewer actually notices.
# Sizing a hero band differently from a dense one, letting a card span two
# columns, breaking the container once: none of that changes provenance, so
# without these bonuses a careful page built from stock utilities scored the
# same as a generated one. They are also exactly what the repetition metrics
# punish the absence of, which keeps the two axes symmetric.
#
# Each is a **share of the axis goal**, not an absolute count, for the same
# reason the goal itself is a ratio: "four distinct band rhythms" is variety on a
# five-band page and monotony on a forty-band site. A count-based bonus put every
# large repository at the cap — designed and generated alike — which is a bonus
# that has stopped measuring anything.
STRUCTURE_BONUS = {
    "band_variety": 0.40,       # × whether the bands form a rhythm system
    "container_variety": 0.25,  # × the same, over content widths
    "split_gap": 0.13,          # row and column gaps sized separately
    "grid_variety": 0.31,       # × whether the column counts form a system
    "asymmetry": 0.31,          # × share of grids whose children span unevenly
    "container_break": 0.25,    # × breaks, one per four sections counting full
    "alignment_variety": 0.20,  # headings not all aligned the same way
    "alignment_consistent": 0.13,  # deliberately all left — still a choice
}
_STRUCTURE_CAP = 0.45          # per axis, so structure cannot fake a system
_BREAK_PER_SECTIONS = 4        # one container break per this many bands is "full"


ENOUGH = 3              # a system is three values; the prescriptions say so


def _variety(values: list[str], enough: int = ENOUGH) -> float:
    """How close a set of values comes to being a *system* of ``enough`` of them.

    Two readings, multiplied, because either one alone measures the wrong thing:

    * **breadth** — are there ``enough`` distinct values at all? Counted against
      three rather than against "all different", because three band rhythms is
      what the prescription asks for, and a five-band page that uses three is
      finished, not 60% finished.
    * **spread** — are they actually in use, or is one of them the value and the
      others footnotes? Breadth alone let a repository with three hundred
      identical grids and six stragglers score a full bonus, which is the
      saturation this whole measure exists to avoid.
    """
    if len(values) < 2:
        return 0.0
    breadth = min(1.0, (len(set(values)) - 1) / (enough - 1))
    dominant = max(Counter(values).values()) / len(values)
    spread = min(1.0, (1.0 - dominant) / (1.0 - 1.0 / enough))
    return breadth * spread


def structural_decisions(docs: list[Document]) -> dict[Axis, float]:
    """Structure's share of each axis goal, ``0..`` :data:`_STRUCTURE_CAP`."""
    from . import layout as layout_metrics
    from . import rhythm as rhythm_metrics

    out: dict[Axis, float] = {Axis.SPACE: 0.0, Axis.LAYOUT: 0.0}

    bands, _ = rhythm_metrics.section_rhythm(docs)
    out[Axis.SPACE] += _variety(bands) * STRUCTURE_BONUS["band_variety"]
    widths = [
        d.value for doc in docs for el in doc.elements for d in el.decls
        if d.axis is Axis.LAYOUT and d.prop == "max-width"
    ]
    out[Axis.SPACE] += _variety(widths) * STRUCTURE_BONUS["container_variety"]
    if any(d.prop in ("gap-x", "gap-y") for doc in docs for el in doc.elements
           for d in el.decls):
        out[Axis.SPACE] += STRUCTURE_BONUS["split_gap"]

    grids = layout_metrics._grid_containers(docs)
    out[Axis.LAYOUT] += _variety([c for _, _, c in grids]) * \
        STRUCTURE_BONUS["grid_variety"]
    if grids:
        uneven = sum(1 for d, e, _ in grids if layout_metrics._has_span_variety(d, e))
        out[Axis.LAYOUT] += (uneven / len(grids)) * STRUCTURE_BONUS["asymmetry"]
    sections = sum(len(doc.sections) for doc in docs)
    if sections:
        reached = min(1.0, layout_metrics.band_breaks(docs)
                      * _BREAK_PER_SECTIONS / sections)
        out[Axis.LAYOUT] += reached * STRUCTURE_BONUS["container_break"]

    centered, headings = layout_metrics._heading_alignment(docs)
    if headings:
        share = len(centered) / len(headings)
        if 0.1 <= share <= 0.9:
            out[Axis.LAYOUT] += STRUCTURE_BONUS["alignment_variety"]
        elif share < 0.1:
            out[Axis.LAYOUT] += STRUCTURE_BONUS["alignment_consistent"]

    return {a: min(_STRUCTURE_CAP, v) for a, v in out.items()}


def collect_decls(docs: list[Document]) -> list[Decl]:
    """Every declaration in the project, elements and stylesheets alike."""
    out: list[Decl] = []
    for doc in docs:
        for el in doc.elements:
            out.extend(el.decls)
        # A styled-component's declarations are written once, in the definition,
        # and reach the page only through usages — which carry them as
        # ``inherited`` and are therefore invisible here. Counted from the
        # definition so a CSS-in-JS project has an authored vocabulary at all.
        for sd in doc.styled:
            out.extend(sd.decls)
        if doc.kind == "style":
            from ..parse.css import rule_decls
            for rule in doc.css_rules:
                out.extend(rule_decls(rule.decls))
    return out


def weigh_axis(axis: Axis, distinct: dict[tuple[str, str, str], Origin],
               theme) -> tuple[float, float]:
    """``(weighted decisions, effective vocabulary size)`` for one axis.

    A scale folds on *both* sides of the ratio: ten shades of one ramp are one
    decision and also one vocabulary entry, so a project that builds a ramp is
    neither credited ten times nor asked to clear a target ten times larger.
    """
    groups: Counter = Counter()
    weight = 0.0
    size = 0.0
    for (prop, value, variant), origin in distinct.items():
        key = decision_group(axis, prop, value, origin, theme)
        if key is not None:
            groups[key] += 1
            continue
        step = VARIANT_WEIGHT if variant else 1.0
        weight += origin.decision_weight * step
        size += step
    for members in groups.values():
        weight += GROUP_BASE + math.log(members)
        size += 1.0
    return weight, size


def score_axes(docs: list[Document], decls: list[Decl],
               elements: int) -> dict[Axis, AxisScore]:
    """Per-axis decision counts, scores and vocabularies.

    ``elements`` is no longer part of the normalization — it is kept in the
    signature because the caller measures it anyway and because the day this
    stops being true it should be a visible change, not a silent one.
    """
    markup = [d for d in docs if d.kind == "markup"]
    structure = structural_decisions(markup)
    theme = next((d.theme for d in docs if d.theme is not None), None)
    by_axis: dict[Axis, list[Decl]] = {axis: [] for axis in AXIS_FLOOR}
    for d in decls:
        if d.axis in by_axis:
            by_axis[d.axis].append(d)

    out: dict[Axis, AxisScore] = {}
    for axis, floor in AXIS_FLOOR.items():
        group = by_axis[axis]
        distinct: dict[tuple[str, str, str], Origin] = {}
        for d in group:
            key = (d.prop, d.value, d.variant)
            prev = distinct.get(key)
            if prev is None or d.origin.decision_weight > prev.decision_weight:
                distinct[key] = d.origin
        weight, size = weigh_axis(axis, distinct, theme)
        goal = max(floor, VOCAB_TARGET * size)
        decisions = weight + structure.get(axis, 0.0) * goal
        vocab = Counter(f"{d.prop}={d.value}" for d in group if not d.variant)
        defaults = sum(1 for d in group if d.origin is Origin.DEFAULT)
        out[axis] = AxisScore(
            axis=axis,
            decisions=round(decisions, 2),
            decision_score=round(100.0 * min(1.0, decisions / goal), 1),
            repetition=0.0,
            vocabulary=dict(vocab.most_common(24)),
            default_share=round(defaults / len(group), 3) if group else 0.0,
            uses=len(group),
            goal=round(goal, 2),
            entries=round(size, 1),
        )
    return out


def observe(docs: list[Document], axes: dict[Axis, AxisScore]) -> list[Observation]:
    """Per-axis observations about missing decisions."""
    out: list[Observation] = []
    for axis, score in axes.items():
        if score.decision_score >= 40 or not score.measured:
            continue
        if not score.vocabulary:
            continue
        top = sorted(score.vocabulary.items(), key=lambda kv: -kv[1])[:5]
        listing = ", ".join(f"{k} ×{v}" for k, v in top)
        out.append(Observation(
            axis=axis,
            id=f"{axis.value}.no_decisions",
            title=f"{axis.label}: karar yok denecek kadar az",
            detail=(
                f"Bu eksende {score.entries:.0f} farklı değer kullanılıyor ama "
                f"ağırlıklı karar toplamı {score.decisions:.1f} — bu sözlük "
                f"büyüklüğünde beklenen {score.goal:.1f}. Değerlerin "
                f"%{score.default_share * 100:.0f}'i framework'ün hazır "
                f"ölçeğinden geliyor: seçilmemiş, varsayılan bırakılmış. Sayı "
                f"değil oran ölçülüyor — daha çok varsayılan kullanmak bu skoru "
                f"yükseltmez. En sık kullanılanlar: {listing}."
            ),
            severity=round(1.0 - score.decision_score / 100.0, 3),
            stat=f"{score.decision_score:.0f}/100 karar",
            evidence=cap_evidence(_axis_evidence(docs, axis)),
            prescription=_PRESCRIPTION[axis],
        ))
    return out


def _axis_evidence(docs: list[Document], axis: Axis) -> list[Evidence]:
    """A few elements whose declarations are all framework defaults."""
    out: list[Evidence] = []
    for doc in docs:
        for el in doc.elements:
            hits = [d for d in el.decls if d.axis is axis and not d.variant]
            if len(hits) < 2 or any(d.origin is not Origin.DEFAULT for d in hits):
                continue
            out.append(evidence_for(doc, el, ", ".join(d.raw for d in hits[:4])))
            if len(out) >= 24:
                return out
    return out


_PRESCRIPTION: dict[Axis, str] = {
    Axis.TYPE: (
        "Kendi tip ölçeğini tanımla: bir oran seç (1.2 minör üçlü, 1.333 dörtlü), "
        "display/başlık/gövde/meta rollerini o orandan türet, display için "
        "negatif tracking ve sıkı leading ver. Tailwind'in text-4xl/text-xl "
        "rampasına dokunma — o rampa herkesin."
    ),
    Axis.COLOR: (
        "Nötr rampanı tonla (saf gray yerine markanın hue'suna kaydırılmış bir "
        "rampa), tek aksan yerine aksan + destek rengi tanımla, ve rolleri "
        "isimlendir (surface / ink / ink-muted / accent / rule) — shade "
        "numarasıyla değil rolle çağır."
    ),
    Axis.SPACE: (
        "Tek bir bölüm boşluğu yerine role göre ritim kur: hero geniş, yoğun "
        "bölümler dar, ardışık aynı renkli bölümler birleşik. En az üç "
        "farklı bölüm ritmi ve iki farklı container genişliği hedefle."
    ),
    Axis.SHAPE: (
        "Tek yarıçap yerine bir biçim dili seç: konteyner yarıçapı, kontrol "
        "yarıçapı ve keskin kenar üçlüsü. Kenarlığı da karar haline getir — "
        "her yerde 1px gri yerine yalnızca ayrım gereken yerde."
    ),
    Axis.LAYOUT: (
        "Her bölümü aynı ortalanmış container'a koyma. En az bir asimetrik "
        "bölüm (2/3 + 1/3), bir tam genişlik kırılması ve sola hizalı bir "
        "bölüm başlığı ekle."
    ),
    Axis.MATERIAL: (
        "Tek gölge yerine yükseklik katmanları tanımla (yüzey / kalkık / "
        "yüzen) ve her kartı kalkık yapma. Derinliği ayırt etmek için kullan, "
        "dekorasyon için değil."
    ),
    Axis.MOTION: (
        "transition-all duration-300 yerine role göre hareket: renk geçişleri "
        "hızlı, düzen geçişleri yavaş ve kendi easing eğrini tanımla. "
        "prefers-reduced-motion karşılığını da yaz."
    ),
}
