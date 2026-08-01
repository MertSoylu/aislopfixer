"""Run every metric over a parsed project and assemble the report.

The two headline numbers are combined here, and how they combine is the single
most consequential choice in the tool.

Repetition alone cannot be the score: a real design system repeats on purpose,
and punishing that would tell every well-built site it is slop. Decision
density alone cannot be it either: a small, plain, honest page has few
decisions and is not a template. What identifies the template is the *pair* —
almost no decisions, endlessly repeated — so decision density sets the size of
the problem and repetition scales it.

``template_score`` is therefore ``(100 − decisions) × (0.55 + 0.45 × repetition)``:
a project with real decisions caps out low no matter how consistent it is, and
a project with none is only called a template once the sameness is measured
rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..design.metrics import (content, contrast, layout, palette, repetition,
                              rhythm, states, tells, vocabulary)
from .models import Axis, Coverage, DesignReport, Document, Observation
from .render import render_documents

# How much each axis contributes to the headline decision density. Type, colour,
# space and layout are what a viewer registers first; shape, material and motion
# are refinements that only read once the first four are decided.
AXIS_WEIGHT: dict[Axis, float] = {
    Axis.TYPE: 0.20,
    Axis.COLOR: 0.18,
    Axis.SPACE: 0.20,
    Axis.LAYOUT: 0.20,
    Axis.SHAPE: 0.08,
    Axis.MATERIAL: 0.07,
    Axis.MOTION: 0.07,
}

# Observations that, taken together, are the template's own signature. Each one
# adds a small amount to the score so a page that trips all of them cannot land
# in the middle just because its axis averages did.
TEMPLATE_TELLS = frozenset({
    "repeat.canonical_order", "repeat.page_skeleton", "repeat.block_shape",
    "copy.stock_headings", "color.stock_palette", "space.uniform_rhythm",
    "layout.symmetric_grids", "layout.center_monoculture", "layout.no_break",
    # "the accent is the blue→violet the model reaches for" is the most
    # recognizable tell there is — more so than a stock palette, which only says
    # the *neutrals* came out of the box. It separates the field's templates
    # from the hand-written page that also uses stock utilities: that page
    # picked a hue, it just picked it out of the shipped ramp.
    "color.default_accent",
})
_TELL_STEP = 2.0
_TELL_CAP = 12.0
_TELL_AT = 0.6      # severity a tell must reach to count


def analyze(root: str, docs: list[Document],
            skipped: dict[str, int] | None = None) -> DesignReport:
    """Measure a parsed project and return its :class:`DesignReport`."""
    markup = [d for d in docs if d.kind == "markup"]
    elements = sum(len(d.elements) for d in markup)
    report = DesignReport(root=root, files_scanned=len(docs), elements=elements)

    # Structure is measured on the tree the page *renders*; vocabulary, palette
    # and copy stay on the tree the author *wrote*. Writing `py-20` once inside
    # a wrapper is one decision however many bands it produces — but it really
    # does produce those bands, and rhythm has to see them.
    rendered = render_documents(markup)
    # The size the decision target is scaled against is the rendered size too:
    # a page that puts eighty elements on screen is a page of that size whether
    # it wrote them once or eight times, and scaling against the source let a
    # componentised template be graded as if it were a small project.
    rendered_elements = sum(len(d.elements) for d in rendered)

    decls = vocabulary.collect_decls(docs)
    report.axes = vocabulary.score_axes(rendered, decls, rendered_elements)
    report.stack = tells.stack_of(docs)

    observations: list[Observation] = list(vocabulary.observe(docs, report.axes))

    space_obs, space_rep = rhythm.analyze(rendered)
    # Read on the *authored* tree: the usages are what carry the roles, and the
    # rendered tree has already replaced them with what they render. This is the
    # one rhythm statement that is about the source's shape, not the page's.
    space_obs += rhythm.shared_band_wrappers(markup)
    layout_obs, layout_rep = layout.analyze(rendered)
    rep_obs, rep_score, clusters, pairs = repetition.analyze(rendered)
    color_obs, color_rep, palette_map = palette.analyze(docs)
    copy_obs, copy_rep = content.analyze(markup)
    tell_obs, tell_rep = tells.analyze(docs)
    # State coverage reads the *authored* tree: a `dark:` written once on a
    # component covers every place it renders, and counting the renders would
    # report a covered project as half-covered.
    state_obs = states.analyze(markup, docs)
    # Contrast reads the rendered tree: the surface a card's text sits on is
    # the one its wrapper paints, and before expansion that wrapper is a
    # component usage with no background of its own.
    contrast_obs = contrast.analyze(rendered, docs)

    observations += (space_obs + layout_obs + rep_obs + color_obs + copy_obs
                     + tell_obs + state_obs + contrast_obs)
    report.clusters = clusters
    report.page_pairs = pairs
    report.palette = palette_map

    per_axis_rep: dict[Axis, float] = dict(tell_rep)
    per_axis_rep[Axis.SPACE] = max(per_axis_rep.get(Axis.SPACE, 0.0), space_rep)
    per_axis_rep[Axis.LAYOUT] = max(
        per_axis_rep.get(Axis.LAYOUT, 0.0), (layout_rep + rep_score) / 2
        if layout_rep and rep_score else max(layout_rep, rep_score))
    per_axis_rep[Axis.COLOR] = max(per_axis_rep.get(Axis.COLOR, 0.0), color_rep)
    per_axis_rep[Axis.COPY] = copy_rep
    for axis, value in per_axis_rep.items():
        if axis in report.axes:
            report.axes[axis].repetition = round(value, 1)

    report.observations = sorted(observations, key=lambda o: (-o.severity, o.id))
    report.rewritable = sum(1 for d in markup for el in d.elements
                            if el.class_span is not None)
    report.coverage = Coverage(
        files_read=len(docs), markup_files=len(markup),
        with_elements=sum(1 for d in markup if d.elements),
        routes=repetition.page_count(rendered),
        elements=elements, rendered=rendered_elements,
        unread=dict(skipped or {}),
    )
    report.notes = (_coverage_notes(docs, report.coverage)
                    + _limit_notes(rendered) + _naming_notes(rendered))
    # Only axes the project actually uses take part in either headline. See
    # AxisScore.measured — declining an axis is not the same as fumbling it.
    live = {a for a, s in report.axes.items() if s.measured}
    report.decision_density = _weighted(
        {a: s.decision_score for a, s in report.axes.items() if a in live})
    report.repetition = _weighted(
        {a: v for a, v in per_axis_rep.items() if a in AXIS_WEIGHT and a in live})
    report.template_score = _template_score(report)
    return report


# --------------------------------------------------------------- what to fix
# The score a decision axis reaches once it is genuinely designed — the same
# threshold ``AxisScore.verdict`` calls "tasarlanmış". Closing a "no decisions"
# observation means getting there, so that is what the projection assumes.
DESIGNED_AT = 60.0

# Observations the class-level transform closes on its own. Everything else
# needs a person or an agent, and the two must be visibly different in a list
# whose whole purpose is "what do I do first".
SELF_FIXABLE = frozenset({
    "color.stock_palette", "color.default_accent", "color.no_decisions",
    "space.uniform_rhythm", "space.single_container", "space.no_decisions",
    "layout.symmetric_grids", "layout.center_monoculture", "layout.no_break",
    "layout.no_decisions", "type.untuned_display", "type.no_decisions",
    "shape.mono_radius", "shape.no_decisions",
    "material.mono_shadow", "material.uniform_card", "material.no_decisions",
})


@dataclass(frozen=True)
class Priority:
    """One observation, what closing it is worth, and who has to close it."""

    observation: Observation
    drop: float          # template-score points this is projected to remove
    self_fixable: bool   # the tool's own transform closes it


def projected_all(report: DesignReport, closed) -> float:
    """The template score with *every* observation in ``closed`` closed at once.

    Not the sum of the individual projections: each of those assumes the others
    stay open, so adding them double-counts the axis gap they share. ``bench``
    compares this against what the transform actually achieves.
    """
    closed = list(closed)
    live = {a: s for a, s in report.axes.items() if s.measured}
    decisions = {a: s.decision_score for a, s in live.items()}
    repetition = {a: s.repetition for a, s in live.items()}
    for observation in closed:
        _close(report, observation, decisions, repetition)
    remaining = [o for o in report.observations if o not in closed]
    return _score_from(_weighted(decisions), _weighted(repetition), remaining)


def _close(report: DesignReport, closed: Observation,
           decisions: dict[Axis, float], repetition: dict[Axis, float]) -> None:
    """Move one observation's share out of the two axis dictionaries."""
    peers = _concrete(report, closed.axis)
    if closed.id.endswith(".no_decisions"):
        if closed.axis in decisions:
            decisions[closed.axis] = max(decisions[closed.axis], DESIGNED_AT)
        return
    weight = sum(o.severity for o in report.observations if o.axis is closed.axis)
    if closed.axis in repetition and weight > 0:
        repetition[closed.axis] *= max(0.0, 1.0 - closed.severity / weight)
    # Closing a concrete tell is also *how* its axis's missing decisions get
    # made — replacing the stock ramp is what raises the colour axis — and that
    # is true whether or not the axis also carries a "no decisions" line. It was
    # gated on that line for one release, and `bench.impact` measured the cost:
    # the forecast came in at half the drop the transform actually produced,
    # because the axes it lifts most are exactly the ones whose gap was already
    # named by a concrete tell instead of by an axis-level one.
    share = sum(o.severity for o in peers)
    if share > 0 and closed.axis in decisions:
        gap = max(0.0, DESIGNED_AT - decisions[closed.axis])
        decisions[closed.axis] += gap * (closed.severity / share)


def projected_score(report: DesignReport, closed: Observation) -> float:
    """The template score this project would carry with ``closed`` closed.

    Recomputed, not guessed at — the same two-axis formula the live score uses,
    run again over the report with one observation removed. Two modelling
    choices are stated rather than hidden, because they are the only part of
    this that is not a measurement:

    * closing a *"no decisions"* observation means that axis reaching
      :data:`DESIGNED_AT`; there is no other reading of "fixed" for it;
    * closing anything else removes its share of its axis's repetition, taken
      as its severity relative to the severities on that axis. Severity is
      derived from that share in every metric that reports one, so this is the
      share put back rather than a new number invented here.

    It is a projection of the tool's own scoring, never a promise about the
    redesign. What it is *for* is ordering: which of two fixes moves the number
    further.
    """
    # A concrete tell is also *how* its axis's missing decisions get made:
    # replacing the stock ramp is what raises the colour axis. Its share of that
    # lift is its severity among the axis's concrete observations, so three tells
    # on one axis split the axis's gap instead of each claiming all of it. That
    # arithmetic lives in :func:`_close`, shared with :func:`projected_all`.
    live = {a: s for a, s in report.axes.items() if s.measured}
    decisions = {a: s.decision_score for a, s in live.items()}
    repetition = {a: s.repetition for a, s in live.items()}
    _close(report, closed, decisions, repetition)
    remaining = [o for o in report.observations if o is not closed]
    return _score_from(_weighted(decisions), _weighted(repetition), remaining)


def _concrete(report: DesignReport, axis: Axis) -> list[Observation]:
    """An axis's observations that name a specific thing to change."""
    return [o for o in report.observations
            if o.axis is axis and not o.id.endswith(".no_decisions")
            and o.prescription]


def priorities(report: DesignReport, limit: int = 5) -> list[Priority]:
    """The work in the order that moves the number most, biggest first.

    An axis-level "no decisions" entry is dropped when that axis already has a
    concrete observation: the two are the same job at two altitudes, and a list
    that answers "what do I fix first" has to name a thing, not an axis.
    """
    ranked = [
        o for o in report.observations
        if not (o.id.endswith(".no_decisions") and _concrete(report, o.axis))
    ]
    # ⚡ is a promise, and on a project whose styles are all in CSS-in-JS there
    # is no class attribute anywhere for the transform to rewrite — it produces
    # zero edits and the score does not move. `bench.impact` caught the tool
    # promising a 165-point drop on exactly that project. A promise it cannot
    # keep is worse than no mark at all.
    reachable = report.rewritable > 0
    out = [
        Priority(
            observation=o,
            drop=round(max(0.0, report.template_score - projected_score(report, o)), 1),
            self_fixable=reachable and o.id in SELF_FIXABLE,
        )
        for o in ranked
    ]
    out.sort(key=lambda p: (-p.drop, -p.observation.severity, p.observation.id))
    return out[:limit] if limit else out


def _coverage_notes(docs: list[Document], coverage: Coverage) -> list[str]:
    """What the measurement could not read — said out loud, not swallowed.

    None of these are design verdicts, so none of them move a score. They say
    how much of the project the scores above actually cover, which is the one
    thing a silent skip takes away from the reader.
    """
    notes: list[str] = [f"Kapsam ({coverage.confidence}): {coverage.summary}."]
    if coverage.unread_pages:
        notes.append(
            f"{coverage.unread_pages} sayfa bu aracın okuyamadığı bir şablon "
            f"dilinde (.erb, .njk, .liquid, Jekyll şablonları). İçerikleri "
            f"ölçüme girmedi: yukarıdaki skorlar taranabilen dosyalar hakkında."
        )
    if coverage.prose_pages:
        notes.append(
            f"{coverage.prose_pages} düz metin (.md) sayfa sayıldı ama "
            f"taranmadı: bir markdown sayfasının tasarımı onu render eden "
            f"temaya aittir, ve o tema bu taramanın okuduğu kaynaktır. "
            f"İçlerindeki işaretleme hemen her zaman bir kod örneğidir; "
            f"okunsaydı belgelenmiş bir snippet sitenin sözlüğü sayılırdı. "
            f"`.mdx` bunun dışında: gövdesi JSX'tir ve taranır."
        )
    generated = coverage.unread.get("generated", 0)
    if generated:
        notes.append(
            f"{generated} stylesheet derlenmiş framework çıktısı olduğu için "
            f"atlandı (Tailwind'in kendi `--tw-*` değişkenleri ya da başlığı). "
            f"Okunsaydı framework'ün bütün utility'leri projenin sözlüğü "
            f"sayılırdı."
        )
    minified = coverage.unread.get("minified", 0)
    if minified:
        notes.append(f"{minified} dosya paketlenmiş/minify edilmiş çıktı "
                     f"olduğu için atlandı.")
    unreadable = sum(d.unreadable_styles for d in docs)
    if unreadable:
        files = sum(1 for d in docs if d.unreadable_styles)
        notes.append(
            f"{unreadable} CSS-in-JS bildirimi okunamadı ({files} dosyada): "
            f"değeri bir interpolasyon (`${{…}}`). Bu değerler ölçüme "
            f"girmedi — tahmin edilmiş bir renk, ölçülmemiş bir renkten kötüdür."
        )
    unresolved = sum(d.unresolved_modules for d in docs)
    if unresolved:
        notes.append(
            f"{unresolved} `*.module.css` içe aktarımı taranan ağaçta "
            f"bulunamadı (takma ad ya da taramanın dışında bir yol). Bu "
            f"dosyaların kuralları hiçbir elemana bağlanmadı."
        )
    return notes


def _limit_notes(rendered: list[Document]) -> list[str]:
    """Every cut the measurement made, with the number it cut at.

    A truncation nobody is told about reads as "I looked at everything", which
    is the one claim this tool must never make by accident. Each note fires only
    when its cap was actually reached.
    """
    notes: list[str] = []
    pages = repetition.page_count(rendered)
    if pages > repetition._MAX_PAGES:
        notes.append(
            f"{pages} sayfanın ilk {repetition._MAX_PAGES}'ü karşılaştırıldı "
            f"(ikili karşılaştırma karesel). Hangi {repetition._MAX_PAGES} "
            f"olduğu yola göre sıralanarak seçildi, tarama sırasına göre "
            f"değil — aynı depo iki kez tarandığında aynı çiftler çıkar."
        )
    capped = [d.rel_path for d in rendered if d.render_capped]
    if capped:
        notes.append(
            f"{len(capped)} sayfada bileşen açılımı bir sınıra çarptı "
            f"(sayfa başına {render_limits()[0]} sanal eleman, bir döngü için "
            f"{render_limits()[1]} kopya). Sınıra çarpan sayfa olduğundan "
            f"*daha az* tekrarlı ölçülür: "
            + ", ".join(sorted(capped)[:3])
            + (f" (+{len(capped) - 3})" if len(capped) > 3 else "")
        )
    return notes


# Below this share of named bands, the canonical-order measure is looking at a
# page it mostly could not read, and saying so is the difference between a
# measure with a reach and a measure with an opinion.
_NAMING_NARROW = 0.7


def _naming_notes(rendered: list[Document]) -> list[str]:
    """How far the section classifier reached on this project.

    Only printed when it fell short: a page whose bands all have names needs no
    caveat, and a note that always prints is a note nobody reads.
    """
    from .metrics.sections import naming

    named, total = naming(rendered)
    if not total or named / total >= _NAMING_NARROW:
        return []
    return [
        f"{total} bandın {total - named} tanesi adlandırılamadı "
        f"(%{100 * (total - named) / total:.0f}). Kanonik sıra ölçüsü bu "
        f"projede dar: adlandırılamayan bir bant o ölçüde şeffaftır — ne diziyi "
        f"uzatır ne kırar. Adlandırılamamak bir kusur değil, çoğu zaman "
        f"sayfanın şablon olmadığının işaretidir; buradaki sayı hükmün değil, "
        f"merceğin genişliğidir."
    ]


def render_limits() -> tuple[int, int]:
    """The expansion caps, read from the module that enforces them."""
    from .render import _MAX_ELEMENTS, _MAX_REPEAT
    return _MAX_ELEMENTS, _MAX_REPEAT


def _weighted(values: dict[Axis, float]) -> float:
    """Weighted mean over the axes that actually produced a number."""
    total = sum(AXIS_WEIGHT[a] for a in values if a in AXIS_WEIGHT)
    if total <= 0:
        return 0.0
    weighted = sum(values[a] * AXIS_WEIGHT[a] for a in values if a in AXIS_WEIGHT)
    return round(weighted / total, 1)


def _template_score(report: DesignReport) -> float:
    if not report.measured:
        # Zero decisions and zero repetition is what an *empty* measurement
        # looks like, and the formula reads that as 55/100 — "şablona yakın"
        # about a project it never saw. Withholding the number is the only
        # honest output here; the verdict says so in words.
        return 0.0
    return _score_from(report.decision_density, report.repetition,
                       report.observations)


def _score_from(decisions: float, repetition: float,
                observations: list[Observation]) -> float:
    """The headline formula, over numbers rather than over a report.

    Taken apart from :func:`_template_score` so the same arithmetic can be run
    on a *hypothetical* report — see :func:`projected_score`. An impact estimate
    computed by a second, parallel formula would drift from the real one, and
    then the ordering it produces would stop being about this tool's score.
    """
    base = (100.0 - decisions) * (0.55 + 0.45 * repetition / 100.0)
    bonus = min(
        _TELL_CAP,
        _TELL_STEP * sum(
            1 for o in observations
            if o.id in TEMPLATE_TELLS and o.severity >= _TELL_AT
        ),
    )
    return round(max(0.0, min(100.0, base + bonus)), 1)
