"""Core data models for the design-fingerprint engine.

The old engine asked "does this file contain a forbidden token?". This one
asks "how many independent design decisions does this project contain, and how
much of it is a copy of itself?" — so the models are about *distributions*, not
about matches.

Three layers:

* :class:`Element` / :class:`Document` — what the parsers produce: a tolerant
  element tree with every style declaration reachable from it (class list,
  inline style, matched CSS rules).
* :class:`Decl` — one resolved design declaration on one axis. This is the
  atom every metric counts: ``(axis, prop, value, origin)``. ``origin`` is what
  separates a *decision* from a *default*.
* :class:`Observation` / :class:`DesignReport` — what the UI renders: per-axis
  verdicts with evidence, and the two headline numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Axis(Enum):
    """The eight axes a design is measured on.

    Ordered as the report displays them: the ones a human notices first come
    first. ``value`` is the stable id used in keys and config; ``label`` is the
    Turkish UI string, ``blurb`` the one-line explanation under it.
    """

    TYPE = "type"
    COLOR = "color"
    SPACE = "space"
    SHAPE = "shape"
    LAYOUT = "layout"
    MATERIAL = "material"
    MOTION = "motion"
    COPY = "copy"

    @property
    def label(self) -> str:
        return _AXIS_LABEL[self]

    @property
    def blurb(self) -> str:
        return _AXIS_BLURB[self]

    @property
    def order(self) -> int:
        return list(Axis).index(self)


_AXIS_LABEL: dict[Axis, str] = {
    Axis.TYPE: "Tipografi",
    Axis.COLOR: "Renk",
    Axis.SPACE: "Boşluk / Ritim",
    Axis.SHAPE: "Biçim",
    Axis.LAYOUT: "Yerleşim",
    Axis.MATERIAL: "Malzeme / Derinlik",
    Axis.MOTION: "Hareket",
    Axis.COPY: "Kopya",
}

_AXIS_BLURB: dict[Axis, str] = {
    Axis.TYPE: "Yazı ölçeği, ağırlık, satır aralığı, harf aralığı",
    Axis.COLOR: "Palet, aksan rolleri, nötr rampanın tonu",
    Axis.SPACE: "Dikey ritim, container genişliği, boşluk ölçeği",
    Axis.SHAPE: "Köşe yarıçapı, kenarlık dili, ayraçlar",
    Axis.LAYOUT: "Grid yapısı, simetri, hizalama, kırılmalar",
    Axis.MATERIAL: "Yüzey muamelesi, gölge katmanları, saydamlık",
    Axis.MOTION: "Geçişler, süreler, yumuşatma eğrileri",
    Axis.COPY: "Metin şekli, başlık uzunluğu, şablon cümleler",
}


class Origin(Enum):
    """Where a declared value came from — the heart of the decision count.

    ``DEFAULT`` is a value the framework already chose (``py-20``, ``text-xl``,
    ``rounded-2xl``, ``bg-gray-100``): using it is not a design decision, it is
    the absence of one. ``ARBITRARY`` is an escape-hatch value the author typed
    (``text-[2.75rem]``, ``py-[68px]``) — someone looked at the screen. ``TOKEN``
    is a project-defined name (``bg-surface``, ``text-ink-muted``, a CSS custom
    property): someone built a system. ``LITERAL`` is a raw CSS value in a
    stylesheet, which is also an authored choice.
    """

    DEFAULT = "default"
    ARBITRARY = "arbitrary"
    TOKEN = "token"
    LITERAL = "literal"

    @property
    def decision_weight(self) -> float:
        """How much one distinct value on this origin counts as a decision."""
        return _ORIGIN_WEIGHT[self]


_ORIGIN_WEIGHT: dict[Origin, float] = {
    Origin.DEFAULT: 0.25,   # a default still shows *selection* among defaults
    Origin.LITERAL: 1.0,
    Origin.ARBITRARY: 1.0,
    Origin.TOKEN: 1.5,      # a named token is a system, the strongest evidence
}


@dataclass(frozen=True)
class Decl:
    """One resolved design declaration on one element.

    ``prop`` is normalized across sources: a Tailwind ``py-20``, an inline
    ``padding-block: 5rem`` and a CSS rule ``padding: 5rem 0`` all land on
    ``space/padding-y`` so they are counted in the same vocabulary.

    ``variant`` carries the Tailwind state/breakpoint prefix (``md``, ``hover``)
    — responsive and state variants are real design work and are counted, but
    they must not be confused with the base value when measuring rhythm.
    """

    axis: Axis
    prop: str
    value: str
    origin: Origin
    variant: str = ""
    raw: str = ""

    @property
    def keyed(self) -> str:
        """``prop=value`` identity used when counting a vocabulary."""
        return f"{self.prop}={self.value}"


@dataclass
class Element:
    """One markup element, with everything needed to style and place it."""

    tag: str
    attrs: dict[str, str]
    classes: list[str]
    inline_style: dict[str, str]
    start: int                 # offset of '<'
    end: int                   # offset just past '>'
    line: int
    depth: int
    parent: int = -1
    children: list[int] = field(default_factory=list)
    inner_start: int = 0       # offset just past the open tag
    inner_end: int = 0         # offset of the close tag (== inner_start if empty)
    own_text: str = ""         # visible text inside, tags/interpolations stripped
    class_attr: str = ""       # the attribute name actually used (class/className)
    class_span: tuple[int, int] | None = None  # offsets of the class value text
    # Only the tokens written in the attribute at ``class_span``. ``classes``
    # also holds what other class-bearing attributes contribute — Vue's
    # ``:class`` object, Svelte's ``class:active`` directives — which is right
    # for measuring and wrong for rewriting: writing a directive's name into
    # the static list would make a conditional class unconditional.
    attr_classes: list[str] = field(default_factory=list)
    decls: list[Decl] = field(default_factory=list)
    # What a JSX component usage renders — filled by parse.components.resolve.
    # Kept apart from ``decls`` so counts of *authored* declarations stay exact;
    # only the metrics that measure the rendered page read it.
    inherited: list[Decl] = field(default_factory=list)
    section_like: bool = False   # a component whose root element is a section
    # The host tag a component usage actually renders, when it is known without
    # expanding anything — `const Title = styled.h2` renders an `h2`. The
    # rendered tree uses it, because a heading that the page really draws is a
    # heading whatever the source called it.
    renders_tag: str = ""
    # CSS-Module class names reached through `className={styles.card}`. Kept
    # apart from ``classes`` because they are not tokens in any class attribute:
    # the attribute holds an expression, and writing a resolved name into it
    # would produce source that no bundler would agree with.
    module_classes: list[str] = field(default_factory=list)

    @property
    def is_component(self) -> bool:
        """True for JSX components (``<FeatureCard>``) vs host tags (``<div>``)."""
        return bool(self.tag) and self.tag[0].isupper()

    @property
    def rendered(self) -> list[Decl]:
        """Declarations that describe how this element actually looks."""
        return self.decls + self.inherited


@dataclass
class CssRule:
    """One CSS rule set, flattened out of any at-rule nesting."""

    selector: str
    decls: dict[str, str]
    at: str = ""          # enclosing at-rule prelude, e.g. "@media (min-width:768px)"
    start: int = 0
    line: int = 1


@dataclass
class Document:
    """A parsed source file: its element tree plus its stylesheet content."""

    rel_path: str
    abs_path: str
    text: str
    kind: str                  # "markup" | "style" | "other"
    elements: list[Element] = field(default_factory=list)
    css_rules: list[CssRule] = field(default_factory=list)
    custom_props: dict[str, str] = field(default_factory=dict)
    # The project's own theme config, shared by every document in the project.
    # Carried here rather than passed around because the class decoder needs it
    # again whenever a tree is re-decoded (component expansion, re-measure).
    theme: object | None = None
    # CSS-in-JS components defined in this file (see parse.styles.StyledDef),
    # plus what could not be read. Both counts reach the report: a scan that
    # silently skips half a project is worse than one that says how much.
    styled: list = field(default_factory=list)
    unreadable_styles: int = 0     # declarations whose value was an interpolation
    unresolved_modules: int = 0    # `*.module.css` imports pointing outside the scan
    # Memo for `render._array_length`: a module-level array's entry count, by
    # name. A component used eight times asks the same question eight times and
    # each answer is a regex over the whole file.
    arrays: dict[str, int] = field(default_factory=dict)
    # Filled by the ``sections`` property on first read; see its docstring.
    _sections: list[int] | None = None
    # Set on a *rendered* document whose component expansion hit a cap. The cap
    # under-reports by construction, so the reader has to be told which pages
    # were measured short rather than measured whole.
    render_capped: bool = False

    @property
    def is_page(self) -> bool:
        """True when this document reads as a rendered page, not a leaf part.

        Page-level repetition (two pages with the same skeleton) is a much
        stronger tell than component reuse (which is correct engineering), so
        the two are measured separately and this is the split.
        """
        return self.kind == "markup" and len(self.sections) >= 2

    @property
    def sections(self) -> list[int]:
        """Indices of the elements that read as top-level page sections.

        Cached on first read. It is a pure function of the element tree, and
        every structural metric asks for it — 4 784 full re-scans of one project
        in a single measurement, each walking every element twice. Filled
        lazily rather than at parse time because ``parse.components.resolve``
        sets ``section_like`` afterwards, and a band list built before that ran
        would miss every component that renders a section.

        Includes JSX components that render a section element — a page built
        from ``<Section>`` wrappers has bands even though its source has no
        ``<section>`` tags at all.

        A band is the *outermost* stripe: once one is found, nothing inside it
        is another one. Without that rule an ``<article>`` card in a grid read
        as a peer of the band containing it, which put four catalogue entries
        into the rhythm distribution and made a list look like a page.
        """
        if self._sections is not None:
            return self._sections
        out: list[int] = []
        inside = [False] * len(self.elements)
        for i, el in enumerate(self.elements):
            parent = el.parent
            inside[i] = parent >= 0 and (
                inside[parent] or self.elements[parent].tag in _SECTION_TAGS
                or self.elements[parent].section_like)
            if inside[i] or el.depth > _SECTION_MAX_DEPTH:
                continue
            if el.tag in _SECTION_TAGS or el.section_like:
                out.append(i)
        self._sections = self._drop_lists(out)
        return self._sections

    def _drop_lists(self, found: list[int]) -> list[int]:
        """Remove runs of card-like bands: three ``<article>``s in a row are a list.

        ``<article>`` is a band tag and also the tag every card grid reaches
        for. The outermost-band rule catches the case where a real ``<section>``
        encloses them; it cannot catch a grid whose wrapper is a plain ``div``,
        and then nine testimonial cards arrived as nine top-level bands and the
        page's skeleton read ``features → content`` instead of naming a single
        testimonial band. Three in a row is a list — the same threshold
        ``repetition`` uses before it calls a shape a cluster.
        """
        out: list[int] = []
        run: list[int] = []
        for i in found + [-1]:
            tag = self.elements[i].tag if i >= 0 else ""
            if run and self.elements[run[0]].tag == tag:
                run.append(i)
                continue
            if run:
                out.extend([] if (len(run) >= _LIST_AT
                                  and self.elements[run[0]].tag in _LIST_LIKE_TAGS)
                           else run)
            run = [i] if i >= 0 else []
        return out


# A "section" is the unit vertical rhythm is measured on. Depth is capped as a
# backstop for trees the scanner could not close cleanly.
_SECTION_TAGS = frozenset({"section", "header", "footer", "article", "nav", "aside"})
# Band tags that a card grid also uses. Repeated, they are a list.
_LIST_LIKE_TAGS = frozenset({"article", "aside"})
_LIST_AT = 3
# Page wrappers: never a band themselves, and transparent — the bands inside
# `<main>` are still top-level bands.
_SECTION_MAX_DEPTH = 8


@dataclass(frozen=True)
class Evidence:
    """One concrete place in the project that supports an observation."""

    file: str
    line: int
    start: int
    end: int
    snippet: str
    value: str = ""


@dataclass
class Observation:
    """One measured statement about the design, with the numbers behind it.

    Deliberately *not* a "finding": it is not a match at a location, it is a
    verdict about a distribution, and its evidence is a sample of the places
    the distribution shows up. ``severity`` is 0..1 — how far this is from a
    designed baseline — and drives ordering, never a pass/fail gate.
    """

    axis: Axis
    id: str                    # stable, e.g. "space.uniform_rhythm"
    title: str
    detail: str
    severity: float
    evidence: list[Evidence] = field(default_factory=list)
    prescription: str = ""
    stat: str = ""             # short measured value shown next to the title

    @property
    def key(self) -> str:
        return f"{self.axis.value}:{self.id}"


@dataclass
class AxisScore:
    """Per-axis result: how many decisions, how repeated, and the vocabulary."""

    axis: Axis
    decisions: float           # weighted distinct-decision count
    decision_score: float      # 0..100, normalized against the size-aware target
    repetition: float          # 0..100
    vocabulary: dict[str, int] = field(default_factory=dict)  # "prop=value" -> uses
    default_share: float = 0.0  # fraction of declared values taken from defaults
    uses: int = 0              # total declarations seen; 0 means "axis unused"
    # What the axis was scored against, and the vocabulary size it was derived
    # from. Carried so the observation can state the comparison it made instead
    # of asserting "below what is expected" and leaving the number offstage.
    goal: float = 0.0
    entries: float = 0.0       # distinct vocabulary entries, scales folded

    @property
    def measured(self) -> bool:
        """False when the project never touches this axis at all.

        An unused axis must not be averaged in as a zero: a page with no
        shadows and no animation has not failed the material and motion axes,
        it has declined them, and restraint is not slop.
        """
        return self.uses > 0

    @property
    def verdict(self) -> str:
        if self.decision_score >= 60:
            return "tasarlanmış"
        if self.decision_score >= 35:
            return "kısmen tasarlanmış"
        if self.decision_score >= 15:
            return "varsayılana yakın"
        return "karar yok"


@dataclass
class RepetitionCluster:
    """A group of structurally identical subtrees — one component, N copies."""

    signature: str
    label: str
    count: int
    files: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    text_variance: float = 0.0  # 0..1, how much the copy inside them differs
    words: int = 0              # total words measured; 0 means "no copy to read"


@dataclass
class PagePair:
    """Skeleton similarity between two pages, 0..1."""

    a: str
    b: str
    similarity: float


@dataclass
class Coverage:
    """How much of the project the numbers above actually describe.

    A scan that reads five files of a fifty-page site produces a perfectly
    normal-looking score, and nothing in it says the other forty-five pages were
    never opened. ``leerob-site`` was that: a docs site whose pages are ``.mdx``,
    measured on a handful of components and graded as if the whole site had been
    read. ``.mdx`` is read now; what remains unread is named below, split by
    *why*, because the two kinds are not the same gap.

    Nothing here moves a score. It says how far the score reaches.
    """

    files_read: int = 0
    markup_files: int = 0
    with_elements: int = 0       # markup files that yielded any element
    routes: int = 0              # pages the scan could read end to end
    elements: int = 0            # authored elements
    rendered: int = 0            # elements after component expansion
    # reason → count for everything walked and not read. ``template:.erb`` is a
    # page in a markup language this tool does not parse; ``prose:.md`` is a
    # page whose design belongs to the theme rendering it; ``generated`` is a
    # framework build artifact; ``minified`` is a bundle.
    unread: dict[str, int] = field(default_factory=dict)

    def _by(self, prefix: str) -> int:
        return sum(n for reason, n in self.unread.items()
                   if reason.startswith(prefix))

    @property
    def unread_pages(self) -> int:
        """Pages written in a markup language this tool cannot read at all."""
        return self._by("template:")

    @property
    def prose_pages(self) -> int:
        """Markdown pages counted and deliberately not scanned.

        Kept apart from :attr:`unread_pages` because it is not a hole in the
        measurement. An unread ``.erb`` page has design in it that the tool
        cannot see; an unread ``.md`` page has none — the theme that renders it
        does, and that theme is source this tool reads.
        """
        return self._by("prose:")

    @property
    def confidence(self) -> str:
        """``"tam"`` · ``"kısmi"`` · ``"yok"`` — how far the numbers reach."""
        if self.elements <= 0 or not self.with_elements:
            return "yok"
        if self.elements < _THIN_AT:
            return "kısmi"
        # No page could be read end to end *and* there are pages this tool does
        # not speak: the scan saw components, and the site is somewhere else.
        # A component library with no page entries and no foreign templates is
        # fully read — it simply has no pages, which is not the same gap.
        if self.routes == 0 and self.unread_pages:
            return "kısmi"
        return "tam"

    def _kinds(self, prefix: str) -> str:
        return ", ".join(sorted(reason.split(":", 1)[1] for reason in self.unread
                                if reason.startswith(prefix)))

    @property
    def summary(self) -> str:
        """One line, in the measurement's own words."""
        parts = [f"{self.with_elements}/{self.markup_files} işaretleme dosyası "
                 f"okundu", f"{self.routes} sayfa", f"{self.elements} eleman"]
        if self.rendered and self.rendered != self.elements:
            parts.append(f"{self.rendered} render")
        if self.unread_pages:
            parts.append(f"{self.unread_pages} dosya okunamayan bir şablon "
                         f"dilinde ({self._kinds('template:')})")
        if self.prose_pages:
            parts.append(f"{self.prose_pages} düz metin sayfa sayıldı, "
                         f"taranmadı ({self._kinds('prose:')})")
        return " · ".join(parts)


# Below this many elements a score is an extrapolation from a fragment, and the
# report has to say so. The same floor `bench/field.py` uses to withhold a side.
_THIN_AT = 40


@dataclass
class DesignReport:
    """Everything the UI shows, and everything the transformer reads."""

    root: str
    files_scanned: int = 0
    elements: int = 0
    decision_density: float = 0.0   # 0..100, headline axis 1
    repetition: float = 0.0         # 0..100, headline axis 2
    template_score: float = 0.0     # 0..100, the "is this the AI template" number
    axes: dict[Axis, AxisScore] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    clusters: list[RepetitionCluster] = field(default_factory=list)
    page_pairs: list[PagePair] = field(default_factory=list)
    palette: dict[str, list[str]] = field(default_factory=dict)
    stack: set[str] = field(default_factory=set)   # "tailwind", "css", "next", ...
    # What the measurement could not read, in the measurement's own words. A cap
    # that is hit, an import that resolved to nothing, a value behind an
    # interpolation: none of them are design verdicts, and all of them change
    # how much of the project the numbers above actually cover.
    notes: list[str] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    # Elements whose class attribute is plain text the transform may rewrite.
    # Zero means the tool can measure this project and change nothing in it.
    rewritable: int = 0

    @property
    def measured(self) -> bool:
        """True when the scan actually saw a page to judge.

        A repository whose markup lives in a theme package, a build output or a
        template language this tool does not read produces no elements — and
        the two-axis formula still returns 55/100 for it, because "no decisions"
        and "no repetition" are what an *empty* measurement looks like. That
        number is a statement about a project nobody measured.
        """
        return self.elements > 0 and any(s.measured for s in self.axes.values())

    @property
    def verdict(self) -> str:
        """One line the whole report collapses to.

        Reads both axes, not just the combined score: "few decisions" and
        "endlessly repeated" are different problems and deserve different
        sentences. A restrained page with little visual system but varied
        structure must not be told it is a template, because it is not one.
        """
        if not self.measured:
            return "Ölçülemedi: bu klasörde okunabilir tasarım kodu yok"
        if self.coverage.confidence == "kısmi":
            # A number derived from a fragment is still a number, and printing
            # it beside the same sentence a full scan gets is the lie. Say what
            # was seen; the score stays available underneath.
            return (f"Kısmi tarama — hüküm dar: {self.coverage.summary}. "
                    f"Skor bu parça için geçerli, proje için değil.")
        if self.template_score >= 70:
            return "Şablon: bu proje üretilmiş landing kalıbının kendisi"
        if self.template_score >= 50:
            return "Şablona yakın: kararların çoğu varsayılan, yapı tekrar ediyor"
        if self.template_score >= 30:
            if self.repetition >= 55:
                return "Karışık: yapı tekrar ediyor, görsel sistem eksik"
            return "Sade: yapı kendine ait, görsel sistem kurulmamış"
        return "Tasarlanmış: kalıptan uzak"

    def axis_observations(self, axis: Axis) -> list[Observation]:
        return sorted(
            (o for o in self.observations if o.axis is axis),
            key=lambda o: -o.severity,
        )
