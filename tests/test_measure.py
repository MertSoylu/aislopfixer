"""Metrics and scoring: what the numbers mean, and what must not move them."""

from __future__ import annotations

import os

from aislopfixer.design.analyze import analyze
from aislopfixer.design.metrics import (content, contrast, layout, palette,
                                        repetition, rhythm, states, tells)
from aislopfixer.design.metrics.sections import canonical_run, classify, skeleton
from aislopfixer.design.metrics.util import coefficient_of_variation, dominant_share
from aislopfixer.design.models import Axis, Origin
from aislopfixer.design.parse import parse_document

from bench.cases import CASES, TWIN_MARGIN
from bench.harness import evaluate, twin_gaps


def doc(name: str, text: str):
    return parse_document(name, f"/abs/{name}", text)


def _band(role_class: str, n: int = 5) -> str:
    return "".join(
        f"<section class='{role_class}'><div class='max-w-7xl mx-auto'>"
        f"<h2 class='text-center'>S{i}</h2></div></section>"
        for i in range(n)
    )


# ------------------------------------------------------------------ helpers
def test_dominant_share_and_variation():
    assert dominant_share(["a", "a", "b"]) == ("a", 2 / 3)
    assert dominant_share([]) == ("", 0.0)
    assert coefficient_of_variation([10, 10, 10]) == 0.0
    assert coefficient_of_variation([2, 20]) > 0.5


# ------------------------------------------------------------------- rhythm
def test_one_band_value_across_sections_is_reported():
    obs, rep = rhythm.analyze([doc("a.html", _band("py-20"))])
    assert any(o.id == "space.uniform_rhythm" for o in obs)
    assert rep > 80


def test_varied_bands_stay_quiet():
    text = "".join(
        f"<section class='py-{v}'><div class='max-w-{m}'>x</div></section>"
        for v, m in (("28", "5xl"), ("12", "3xl"), ("16", "5xl"), ("8", "2xl"),
                     ("24", "6xl"))
    )
    obs, _ = rhythm.analyze([doc("a.html", text)])
    assert not [o for o in obs if o.id == "space.uniform_rhythm"]


def test_band_padding_is_found_on_the_inner_container():
    d = doc("a.html", "<section><div class='py-20 max-w-7xl mx-auto'>x</div></section>")
    values, _ = rhythm.section_rhythm([d])
    assert values == ["20"]


# ------------------------------------------------------------------- layout
def test_symmetric_grids_and_centred_headings_are_reported():
    text = (
        "<section class='py-20'><div class='max-w-7xl mx-auto text-center'>"
        "<h2>A</h2><div class='grid grid-cols-3'><div>1</div><div>2</div><div>3</div></div>"
        "</div></section>"
        "<section class='py-20'><div class='max-w-7xl mx-auto text-center'>"
        "<h2>B</h2><div class='grid grid-cols-3'><div>1</div><div>2</div><div>3</div></div>"
        "</div></section>"
        "<section class='py-20'><div class='max-w-7xl mx-auto text-center'>"
        "<h2>C</h2><div class='grid grid-cols-3'><div>1</div><div>2</div><div>3</div></div>"
        "</div></section>"
    )
    obs, rep = layout.analyze([doc("a.html", text)])
    ids = {o.id for o in obs}
    assert {"layout.symmetric_grids", "layout.center_monoculture"} <= ids
    assert rep > 80


def test_an_asymmetric_grid_is_not_reported():
    text = (
        "<div class='grid grid-cols-12'><div class='col-span-7'>1</div>"
        "<div class='col-span-5'>2</div></div>"
        "<div class='grid grid-cols-12'><div class='col-span-4'>1</div>"
        "<div class='col-span-8'>2</div></div>"
    )
    obs, _ = layout.analyze([doc("a.html", text)])
    assert not [o for o in obs if o.id == "layout.symmetric_grids"]


def test_a_full_bleed_element_counts_as_a_break():
    text = _band("py-20") + "<figure class='w-screen'><img/></figure>"
    obs, _ = layout.analyze([doc("a.html", text)])
    assert not [o for o in obs if o.id == "layout.no_break"]


# --------------------------------------------------------------- repetition
def test_page_skeleton_similarity_is_measured_between_pages():
    page = (
        "<header><h1>Hi</h1></header>"
        "<section><h2>Features</h2></section>"
        "<section><h2>Pricing</h2><p>$9 per month</p></section>"
        "<footer>x</footer>"
    )
    pairs = repetition.page_pairs([doc("a.html", page), doc("b.html", page)])
    assert pairs and pairs[0].similarity == 1.0


def test_sibling_repetition_alone_is_not_a_template():
    """Three cards in one row are a list; a cluster needs to cross a boundary."""
    text = (
        "<div class='grid'>"
        + "".join("<div class='rounded-2xl border p-6'><h3>T</h3><p>b</p></div>"
                  for _ in range(3))
        + "</div>"
    )
    assert repetition.clusters([doc("a.html", text)]) == []


def test_the_same_shape_in_two_sections_is_a_template():
    card = ("<div class='rounded-2xl border p-6'><span class='w-12'>i</span>"
            "<h3>T</h3><p>body text</p></div>")
    text = f"<section class='grid'>{card * 2}</section><section class='grid'>{card * 2}</section>"
    found = repetition.clusters([doc("a.html", text)])
    assert found and found[0].count >= 3


# ------------------------------------------------------------------ palette
def test_stock_palette_and_default_accent_are_reported():
    text = ("<div class='bg-white text-gray-900 border-gray-200 bg-gray-50 "
            "text-gray-600 bg-indigo-600 text-indigo-700'>x</div>")
    obs, _, table = palette.analyze([doc("a.html", text)])
    ids = {o.id for o in obs}
    assert "color.stock_palette" in ids
    assert "color.default_accent" in ids
    assert table["authored"] == []


def test_provenance_is_not_counted_as_repetition():
    """A plain stock ramp must not read as repetitive — that is a decision gap."""
    text = ("<div class='bg-stone-50 text-stone-900 border-stone-200 "
            "text-stone-600 bg-stone-100 text-stone-500'>x</div>")
    obs, rep, _ = palette.analyze([doc("a.html", text)])
    assert "color.stock_palette" in {o.id for o in obs}
    assert rep == 0.0


def test_authored_colours_are_kept_out_of_the_stock_count():
    text = "<div class='bg-paper text-ink border-rule bg-[#a8442a] text-clay'>x</div>"
    obs, _, table = palette.analyze([doc("a.html", text)])
    assert "color.stock_palette" not in {o.id for o in obs}
    assert table["authored"]


# --------------------------------------------------------------------- copy
def test_stock_headings_are_reported_as_a_table_of_contents():
    text = "".join(f"<h2>{h}</h2>" for h in
                   ("Features", "How It Works", "Testimonials", "Pricing"))
    obs, _ = content.analyze([doc("a.html", text)])
    assert "copy.stock_headings" in {o.id for o in obs}


def test_written_headings_stay_quiet():
    text = "".join(f"<h2>{h}</h2>" for h in (
        "We buy four hundred kilos a year",
        "Where the tea comes from",
        "A note about single origin",
        "Ordering",
    ))
    obs, _ = content.analyze([doc("a.html", text)])
    assert "copy.stock_headings" not in {o.id for o in obs}


# ----------------------------------------------------------------- sections
def test_a_section_with_an_h1_is_the_hero_even_when_it_sounds_like_features():
    d = doc("a.html", "<section><h1>Ship it</h1><p>Everything you need to build.</p></section>")
    assert classify(d, d.sections[0]) == "hero"


def test_canonical_run_breaks_on_reordering():
    assert canonical_run(["hero", "features", "pricing", "faq"]) == 4
    assert canonical_run(["pricing", "hero", "features"]) == 2


def test_a_turkish_landing_page_is_read_as_the_template_it_is():
    """The section reader has to speak the language its own interface does.

    None of the English vocabularies match a word of `slop_tr`, so before the
    Turkish patterns every band read as `content` and the structural half of
    the template score went silent on exactly the pages this tool's users
    write.
    """
    import os

    from aislopfixer.design.metrics.sections import CANONICAL, skeleton
    from aislopfixer.design.project import scan_project
    from aislopfixer.design.render import render_documents

    from bench.cases import ROOT

    _report, docs = scan_project(os.path.join(ROOT, "slop_tr"))
    rendered = render_documents([d for d in docs if d.kind == "markup"])
    roles = skeleton(rendered[0])
    assert roles == CANONICAL, roles


def test_a_band_no_vocabulary_can_place_is_named_by_its_shape():
    """`content` was the answer for two thirds of a studio site's bands.

    The names below are structural, not canonical: naming one neither extends
    the template run nor breaks it. What they buy is a rhythm token per shape,
    two pages that stop reading as one page, and a number for how far the
    classifier reached.
    """
    import os

    from aislopfixer.design.metrics.sections import CANONICAL, classify, naming
    from aislopfixer.design.project import scan_project
    from aislopfixer.design.render import render_documents

    from bench.cases import ROOT

    _report, docs = scan_project(os.path.join(ROOT, "clean_studio_large"))
    rendered = render_documents([d for d in docs if d.kind == "markup"])
    named, total = naming(rendered)
    assert total >= 10 and named / total >= 0.7, f"{named}/{total}"
    roles = {classify(d, i) for d in rendered for i in d.sections}
    assert roles - set(CANONICAL), "a studio site is not a landing sequence"


def test_pages_made_of_shapes_are_not_the_same_page():
    """Three pages of a studio site share a house style, not a template.

    Skeleton similarity is a claim about the canonical sequence, so a band
    named by its shape takes no part in it — the same transparency
    `canonical_run` already gives it.
    """
    import os

    from aislopfixer.design.project import scan_project

    from bench.cases import ROOT

    import difflib

    from aislopfixer.design.metrics.sections import routes
    from aislopfixer.design.render import render_documents

    report, docs = scan_project(os.path.join(ROOT, "clean_studio_large"))
    assert not [o for o in report.observations if o.id == "repeat.page_skeleton"]
    # …and the filter is the reason, not luck: read whole, these three pages
    # are well over the similarity threshold that would report them as one.
    rendered = render_documents([d for d in docs if d.kind == "markup"])
    owns = [own for _label, _roles, own in routes(rendered)]
    assert len(owns) == 3
    assert difflib.SequenceMatcher(None, owns[0], owns[1]).ratio() >= 0.7


def test_skeleton_collapses_repeats():
    d = doc("a.html", "<header><h1>x</h1></header><footer>a</footer><footer>b</footer>")
    assert skeleton(d) == ["hero", "footer"]


# ------------------------------------------------------------------ scoring
def test_an_unused_axis_is_excluded_not_scored_zero():
    """Restraint is not slop: a page with no shadows has declined that axis."""
    report = analyze("x", [doc("a.html", "<p class='text-lg text-gray-700'>hi</p>")])
    assert not report.axes[Axis.MOTION].measured
    assert report.axes[Axis.MOTION].decision_score == 0.0
    assert report.decision_density > 0


def test_structural_choices_count_even_when_every_value_is_a_default():
    from aislopfixer.design.metrics.vocabulary import structural_decisions

    flat = doc("a.html", _band("py-20"))
    varied = doc("b.html",
                 "<section class='py-28'><div class='max-w-5xl mx-auto'>a</div></section>"
                 "<section class='py-12'><div class='max-w-3xl mx-auto'>b</div></section>"
                 "<section class='py-16'><div class='max-w-6xl mx-auto'>c</div></section>")
    assert structural_decisions([varied])[Axis.SPACE] > \
        structural_decisions([flat])[Axis.SPACE]


def test_origin_weights_rank_token_above_default():
    assert (Origin.TOKEN.decision_weight > Origin.ARBITRARY.decision_weight
            > Origin.DEFAULT.decision_weight)


# -------------------------------------------------------------------- bench
def test_every_corpus_case_lands_in_its_band():
    for case in CASES:
        outcome = evaluate(case)
        lo, hi = case.template
        assert lo <= outcome.template <= hi, (
            f"{case.name}: şablon {outcome.template} ∉ [{lo}, {hi}]")
        dlo, dhi = case.decisions
        assert dlo <= outcome.decisions <= dhi, (
            f"{case.name}: karar {outcome.decisions} ∉ [{dlo}, {dhi}]")
        assert not outcome.missing, f"{case.name}: eksik {outcome.missing}"
        assert not outcome.spurious, f"{case.name}: yanlış pozitif {outcome.spurious}"


def test_generated_and_hand_written_cases_do_not_overlap():
    scores = {c.name: (c.family, evaluate(c).template) for c in CASES}
    slop = [v for f, v in scores.values() if f == "slop"]
    rest = [v for f, v in scores.values() if f in ("middle", "clean")]
    assert min(slop) - max(rest) >= 15, scores


def test_a_projects_own_theme_config_is_read():
    """`text-lg` in a project that redefined `fontSize.lg` is a decision.

    Acceptance for the config reader: the typography axis has to clear 60 on a
    page whose every type class is a name Tailwind also ships, and the project
    that never wrote a config must not move a point.
    """
    import aislopfixer.design.project as project_module
    from aislopfixer.design.parse.theme import EMPTY
    from aislopfixer.design.project import scan_project

    from bench.cases import ROOT

    with_config, _ = scan_project(os.path.join(ROOT, "clean_config"))
    assert with_config.axes[Axis.TYPE].decision_score > 60

    load = project_module.load_theme
    project_module.load_theme = lambda sources: EMPTY
    try:
        blind, _ = scan_project(os.path.join(ROOT, "clean_config"))
        stock, _ = scan_project(os.path.join(ROOT, "slop_saas"))
        stock_blind = evaluate(next(c for c in CASES if c.name == "slop_saas"))
    finally:
        project_module.load_theme = load

    # The gap the reader closes, and the page it must leave alone.
    assert blind.axes[Axis.TYPE].decision_score < 60
    assert stock.template_score == stock_blind.template


def test_a_project_with_nothing_to_measure_gets_no_score():
    """Zero decisions and zero repetition is what *empty* looks like.

    The two-axis formula reads that as 55/100 — "şablona yakın" about a
    repository whose markup the tool never found. Found in the field table on a
    Jekyll site whose pages live in `_layouts`.
    """
    empty = analyze("/nowhere", [])
    assert not empty.measured
    assert empty.template_score == 0.0
    assert "Ölçülemedi" in empty.verdict


def test_the_impact_list_is_ordered_by_a_recomputed_score():
    """"What do I fix first" has to be answered by the score, not by weight.

    The drop beside each job is this tool's own formula re-run with that
    observation closed, so the ordering is monotone by construction and the
    first job really is the one that moves the number furthest.
    """
    from aislopfixer.design.analyze import (SELF_FIXABLE, priorities,
                                            projected_score)

    for name in ("slop_saas", "slop_react", "slop_styled", "half_dark_kit"):
        report = evaluate(next(c for c in CASES if c.name == name))
        _ = report                      # band checked elsewhere; scores below
        from aislopfixer.design.project import scan_project

        from bench.cases import ROOT
        full, _docs = scan_project(os.path.join(ROOT, name))
        jobs = priorities(full)
        assert jobs, name
        drops = [j.drop for j in jobs]
        assert drops == sorted(drops, reverse=True), (name, drops)
        assert drops[0] > 0, name
        for job in jobs:
            # The number is the recomputation, not a second opinion about it.
            assert job.drop == round(
                max(0.0, full.template_score
                    - projected_score(full, job.observation)), 1)
            # ⚡ is a promise, so it needs both a fix the tool knows and a place
            # to write it. `slop_styled` has no class attribute anywhere.
            assert job.self_fixable == (
                job.observation.id in SELF_FIXABLE and full.rewritable > 0)
        # An axis-level "no decisions" never stands beside a concrete tell on
        # the same axis — they are the same job at two altitudes.
        axes = {j.observation.axis for j in jobs
                if not j.observation.id.endswith(".no_decisions")}
        assert not any(j.observation.id.endswith(".no_decisions")
                       and j.observation.axis in axes for j in jobs), name


def test_decision_density_does_not_grow_with_size():
    """The measurement this whole axis exists to make scale-free.

    ``slop_kit`` renders about three times as many elements as ``slop_saas`` out
    of the same vocabulary of framework defaults. Under a target that scaled
    with element count and stopped growing at 120, the larger one scored *up* —
    which is how eight real landing templates were graded "designed" in
    ``bench/field.md`` for two releases. The gap between them is now about the
    design, so it has to stay small.
    """
    import os

    from aislopfixer.design.project import scan_project

    from bench.cases import ROOT

    small, _ = scan_project(os.path.join(ROOT, "slop_saas"))
    large, _ = scan_project(os.path.join(ROOT, "slop_kit"))
    assert large.coverage.rendered > 2 * small.coverage.rendered
    assert abs(large.decision_density - small.decision_density) < 15, (
        small.decision_density, large.decision_density)


def test_a_redefined_ramp_is_one_decision_not_ten():
    """Ten shades of one colour ramp are one decision, and one vocabulary entry.

    Every landing kit ships a config. Counting each key it touches as its own
    ``TOKEN`` handed those projects a full axis before a page was written.
    """
    from aislopfixer.design.metrics.vocabulary import weigh_axis
    from aislopfixer.design.models import Axis, Origin

    ramp = {(f"background-color", f"brand-{n}", ""): Origin.TOKEN
            for n in (50, 100, 200, 300, 400, 500, 600, 700, 800, 900)}
    weight, size = weigh_axis(Axis.COLOR, ramp, None)
    assert size == 1.0
    assert 1.5 < weight < 5.0            # more than one value, far less than ten

    roles = {("background-color", name, ""): Origin.TOKEN
             for name in ("surface", "ink", "accent", "rule")}
    weight, size = weigh_axis(Axis.COLOR, roles, None)
    assert size == 4.0                   # four roles are four decisions


def test_a_compiled_stylesheet_is_not_the_projects_vocabulary():
    from aislopfixer.scanner import _looks_generated

    compiled = "/*! tailwindcss v3.4.1 | MIT License */\n.mx-auto{margin:auto}"
    assert _looks_generated("output.css", compiled)
    runtime = "*,::before{--tw-border-spacing-x:0;--tw-ring-offset-shadow:0 0}"
    assert _looks_generated("app.css", runtime)
    assert not _looks_generated("app.css", ":root { --color-ink: #111; }")
    assert not _looks_generated("notes.txt", compiled)


def test_a_next_route_is_its_layout_plus_its_page():
    """The canonical sequence lives in two files and neither imports the other."""
    import os

    from aislopfixer.design.metrics.sections import canonical_run, routes
    from aislopfixer.design.project import load_documents
    from aislopfixer.design.render import render_documents

    from bench.cases import ROOT

    docs = load_documents(os.path.join(ROOT, "slop_kit"))
    rendered = render_documents([d for d in docs if d.kind == "markup"])
    found = {label: roles for label, roles, _own in routes(rendered)}
    home = next(roles for label, roles in found.items() if label.endswith("page.tsx"))
    assert home[0] == "hero" and home[-1] == "footer"
    assert canonical_run(home) >= 5
    # The page's *own* roles carry no chrome: every route in an App Router
    # project shares one layout, and comparing the composed lists reported two
    # unrelated pages as the same page.
    own = {label: own for label, _roles, own in routes(rendered)}
    assert all("footer" not in roles for roles in own.values())


def test_the_transform_forecast_is_the_transform():
    """The number shown before `a` has to be the number the next scan reports.

    Not a projection of it — `transform.preview` builds the same plan, applies
    the same edits in memory and re-measures with the same pipeline. Anything
    that reads from disk instead of from the plan shows up here as a gap.
    """
    import os
    import shutil
    import tempfile

    from aislopfixer.design.project import scan_project
    from aislopfixer.design.system.derive import derive
    from aislopfixer.design.transform import preview
    from aislopfixer.design.transform import run as transform_run

    from bench.cases import ROOT

    for name in ("slop_saas", "slop_kit", "slop_styled", "clean_config"):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, name)
            shutil.copytree(os.path.join(ROOT, name), root)
            before, docs = scan_project(root)
            system = derive(root, before)
            forecast = preview(root, docs, before, system)
            transform_run(root, docs, before, system)
            after, _ = scan_project(root)
            assert forecast.template_score == after.template_score, (
                name, forecast.template_score, after.template_score)


def test_a_crafted_template_lands_in_the_middle():
    """“Sold as a starting point” and “nobody decided anything” differ.

    `crafted_kit` has a tuned type ramp, authored easing and a broken layout on
    a stock palette. The field table reads this band directly for its `crafted`
    side, so a change that moves this case moves that judgement too — which is
    the point of pinning it here rather than restating a threshold there.
    """
    import os

    from aislopfixer.design.project import scan_project

    from bench.cases import CASES, ROOT

    case = next(c for c in CASES if c.name == "crafted_kit")
    report, _ = scan_project(os.path.join(ROOT, "crafted_kit"))
    lo, hi = case.template
    assert lo <= report.template_score <= hi
    # Above the generated kit it resembles, below a site somebody designed.
    generated, _ = scan_project(os.path.join(ROOT, "slop_kit"))
    designed, _ = scan_project(os.path.join(ROOT, "clean_studio_large"))
    assert designed.template_score < report.template_score < generated.template_score


def test_a_project_the_transform_cannot_reach_gets_no_lightning():
    """`slop_styled` has no class attribute anywhere: every style is CSS-in-JS.

    The transform produces zero edits there, so a ⚡ next to a job would be a
    promise the tool cannot keep — `bench.impact` measured it promising a
    165-point drop on a project whose score does not move at all.
    """
    import os

    from aislopfixer.design.analyze import priorities
    from aislopfixer.design.project import scan_project

    from bench.cases import ROOT

    styled, _ = scan_project(os.path.join(ROOT, "slop_styled"))
    assert styled.rewritable == 0
    assert not any(job.self_fixable for job in priorities(styled))

    utility, _ = scan_project(os.path.join(ROOT, "slop_saas"))
    assert utility.rewritable > 0
    assert any(job.self_fixable for job in priorities(utility))


def test_the_scan_says_how_much_of_the_project_it_read():
    """A five-file scan of a fifty-page site must not read as a full one."""
    import os

    from aislopfixer.design.project import scan_project

    from bench.cases import ROOT

    report, _ = scan_project(os.path.join(ROOT, "slop_kit"))
    assert report.coverage.confidence == "tam"
    assert report.coverage.routes >= 2
    assert report.coverage.rendered > report.coverage.elements
    assert any("Kapsam" in note for note in report.notes)


def test_a_theme_in_a_dot_directory_is_source_not_build_output(tmp_path):
    """A VitePress site keeps its whole design in `.vitepress/theme`.

    The blanket "skip anything starting with a dot" rule is right for `.next`
    and wrong here: it read `hono-website` as four markup files and then blamed
    the gap on its `.md` pages, which carry no design at all.
    """
    from aislopfixer.scanner import eligible_paths

    theme = tmp_path / ".vitepress" / "theme"
    theme.mkdir(parents=True)
    (theme / "Layout.vue").write_text(
        "<template><section class='py-20'><slot/></section></template>",
        encoding="utf-8")
    cache = tmp_path / ".vitepress" / "cache"
    cache.mkdir()
    (cache / "chunk.js").write_text("export const a = 1", encoding="utf-8")
    (tmp_path / ".next").mkdir()
    (tmp_path / ".next" / "page.js").write_text("x", encoding="utf-8")

    found = {os.path.basename(p) for p in eligible_paths(str(tmp_path))}
    assert found == {"Layout.vue"}


def test_markdown_pages_are_counted_apart_from_unreadable_ones(tmp_path):
    """Two unread pages, two different gaps — and only one of them is a hole.

    A `.erb` page has design in it this tool cannot see. A `.md` page has none:
    the theme that renders it does, and the theme is source the scan reads. An
    `.mdx` page is neither — its body is JSX and it is read like any markup.
    """
    from aislopfixer.design.project import scan_project

    (tmp_path / "index.html").write_text(
        "<main>" + "".join(f"<section class='py-20'><h2>H{i}</h2>"
                           f"<div class='grid grid-cols-3'><article class='p-6'>"
                           f"a</article></div></section>" for i in range(9))
        + "</main>", encoding="utf-8")
    (tmp_path / "guide.md").write_text(
        "# Guide\n\n```html\n<div class=\"px-4 bg-indigo-600\">x</div>\n```\n",
        encoding="utf-8")
    (tmp_path / "old.erb").write_text("<%= render 'x' %>", encoding="utf-8")
    (tmp_path / "note.mdx").write_text(
        "# Note\n\n<Callout class='p-8 rounded-2xl'>hi</Callout>\n",
        encoding="utf-8")

    report, docs = scan_project(str(tmp_path))
    cov = report.coverage
    assert cov.prose_pages == 1 and cov.unread_pages == 1
    assert any(d.rel_path == "note.mdx" and d.elements for d in docs)
    assert "px-4" not in {
        c for d in docs for el in d.elements for c in el.classes}
    assert any("düz metin" in note for note in report.notes)


def _monorepo(root) -> None:
    """A marketing route and a dashboard sharing one `components/` directory."""
    (root / "components").mkdir()
    (root / "components" / "Hero.tsx").write_text(
        "export const Hero = () => (<section className='py-20 bg-white'>"
        "<h1 className='text-5xl font-bold'>Ship faster</h1></section>);\n",
        encoding="utf-8")
    (root / "components" / "Table.tsx").write_text(
        "export const Table = () => (<section className='py-4 bg-slate-50'>"
        + "".join(f"<div className='p-2 text-xs'>row {i}</div>" for i in range(40))
        + "</section>);\n", encoding="utf-8")
    for route, tag in (("(marketing)", "Hero"), ("(dash)", "Table")):
        folder = root / "app" / route
        folder.mkdir(parents=True)
        (folder / "page.tsx").write_text(
            f"import {{ {tag} }} from '../../components/{tag}';\n"
            f"export default () => (<main><{tag} /></main>);\n", encoding="utf-8")


def test_a_page_scope_measures_one_site_without_losing_its_components(tmp_path):
    """`Project.subdir` could never do this: it left `components/` outside.

    The whole tree is read either way — the scope decides what the numbers are
    *about*, and a marketing page's `<Hero>` belongs to the marketing route
    wherever the repository keeps it.
    """
    from aislopfixer.config import Config
    from aislopfixer.design.project import scan_project

    _monorepo(tmp_path)
    scoped, docs = scan_project(
        str(tmp_path), Config().with_pages(["app/(marketing)"]))
    paths = {d.rel_path.replace("\\", "/") for d in docs if d.kind == "markup"}
    assert "components/Hero.tsx" in paths, "the page's own component was dropped"
    assert "components/Table.tsx" not in paths
    assert "app/(dash)/page.tsx" not in paths
    assert scoped.elements > 2, "component expansion still has to resolve"
    assert any("Kapsam sınırlandı" in note for note in scoped.notes)


def test_a_page_scope_is_a_scope_not_a_threshold(tmp_path):
    """With no scope given, nothing is filtered and the numbers do not move."""
    from aislopfixer.config import Config
    from aislopfixer.design.project import scan_project

    _monorepo(tmp_path)
    plain, plain_docs = scan_project(str(tmp_path))
    same, same_docs = scan_project(str(tmp_path), Config())
    assert plain.template_score == same.template_score
    assert len(plain_docs) == len(same_docs)

    scoped, _ = scan_project(str(tmp_path), Config().with_pages(["app/(dash)"]))
    assert scoped.elements < plain.elements


def test_a_shared_band_wrapper_is_named_in_the_brief():
    """The tool has to say where its own transform stops.

    On a componentised page the rhythm fix collapses onto one `<Section>`, so
    every band gets the same new value and the measurement does not move. The
    user could otherwise only discover that by reading the diff.
    """
    from aislopfixer.design.brief import render
    from aislopfixer.design.project import scan_project

    from bench.cases import ROOT

    report, _ = scan_project(os.path.join(ROOT, "slop_react"))
    obs = [o for o in report.observations if o.id == "space.shared_band_wrapper"]
    assert obs and "Section" in obs[0].title
    brief = render(report)
    head = brief.index("## Aracın yapamadığı: bileşen sınırı")
    section = brief[head:head + 2000]
    assert "Section" in section and "Hero" in section


def test_the_same_design_scores_the_same_in_every_stack():
    """A componentised template must not score better than its HTML twin."""
    outcomes = [evaluate(c) for c in CASES]
    gaps = twin_gaps(outcomes)
    assert gaps, "the corpus must keep at least one cross-stack pair"
    for a, b, gap in gaps:
        assert gap <= TWIN_MARGIN, f"{a} / {b}: {gap:.1f} puan"


# ------------------------------------------------------------------- states
def _painted(n: int, dark: int) -> str:
    return "".join(
        f"<div class='bg-white text-gray-900{' dark:bg-slate-900' if i < dark else ''}'>x</div>"
        for i in range(n)
    )


def test_no_dark_mode_at_all_is_not_a_failure():
    """Declining a mode is a decision; only a half-finished claim is reported."""
    obs = states.analyze([doc("a.html", _painted(14, 0))], [])
    assert not [o for o in obs if o.id == "color.partial_dark"]


def test_a_finished_dark_mode_is_silent():
    obs = states.analyze([doc("a.html", _painted(14, 14))], [])
    assert not [o for o in obs if o.id == "color.partial_dark"]


def test_a_half_finished_dark_mode_is_reported():
    obs = states.analyze([doc("a.html", _painted(14, 5))], [])
    hit = next(o for o in obs if o.id == "color.partial_dark")
    assert hit.axis is Axis.COLOR and hit.evidence


def test_a_stylesheet_dark_mode_is_not_second_guessed():
    page = doc("a.html", _painted(14, 5))
    sheet = doc("a.css", ".dark .card { background: #111 }")
    assert not [o for o in states.analyze([page], [page, sheet])
                if o.id == "color.partial_dark"]


def test_removing_the_browser_focus_ring_is_reported_at_once():
    page = doc("a.html", "<a href='#' class='outline-none text-blue-600'>go</a>")
    hit = next(o for o in states.analyze([page], [page])
               if o.id == "color.partial_focus")
    assert "outline-none" in hit.prescription


def test_controls_left_at_the_browser_default_are_silent():
    page = doc("a.html", "".join(f"<a href='#'>{i}</a>" for i in range(6)))
    assert not states.analyze([page], [page])


# ----------------------------------------------------------------- contrast
def _text_on(bg: str, ink: str, n: int = 5) -> str:
    return f"<div class='{bg}'>" + "".join(
        f"<p class='{ink}'>line {i}</p>" for i in range(n)) + "</div>"


def test_muted_grey_below_aa_is_reported():
    page = doc("a.html", _text_on("bg-gray-50", "text-gray-400"))
    hit = next(o for o in contrast.analyze([page], [page])
               if o.id == "color.low_contrast")
    assert hit.axis is Axis.COLOR and hit.evidence


def test_a_pair_that_clears_aa_is_silent():
    """`gray-500` on white is 4.8:1 — a threshold set by eye would flag it."""
    page = doc("a.html", _text_on("bg-white", "text-gray-500"))
    assert not contrast.analyze([page], [page])


def test_a_chromatic_pair_is_not_guessed_at():
    page = doc("a.html", _text_on("bg-amber-500", "text-indigo-400"))
    assert not contrast.analyze([page], [page])


def test_authored_colours_are_measured_exactly():
    sheet = doc("t.css", ":root { --ink: #9a9a9a; --paper: #ffffff }")
    page = doc("a.html", _text_on("bg-[var(--paper)]", "text-[var(--ink)]"))
    hit = next(o for o in contrast.analyze([page], [page, sheet])
               if o.id == "color.low_contrast")
    assert ":1" in hit.evidence[0].value


def test_text_with_nothing_declared_under_it_is_skipped():
    page = doc("a.html", "".join(f"<p class='text-gray-400'>x{i}</p>" for i in range(6)))
    assert not contrast.analyze([page], [page])


# ---------------------------------------------------------------- big repos
def _synthetic_repo(root, pages: int, components: int) -> int:
    """A componentised Next.js-shaped project, written to disk."""
    (root / "app").mkdir(parents=True, exist_ok=True)
    (root / "components").mkdir(parents=True, exist_ok=True)
    for i in range(components):
        (root / "components" / f"Card{i}.tsx").write_text(
            f'export function Card{i}({{title}}: any) {{\n'
            f'  return (\n'
            f'    <div className="rounded-2xl border border-gray-200 p-6 shadow-sm">\n'
            f'      <div className="w-12 h-12 rounded-lg bg-indigo-50 mb-4" />\n'
            f'      <h3 className="text-xl font-semibold text-gray-900">{{title}}</h3>\n'
            f'      <p className="text-gray-600">body</p>\n'
            f'    </div>\n  );\n}}\n', encoding="utf-8")
    roles = ("Features", "How It Works", "Pricing", "Testimonials",
             "Ready to get started?", "FAQ")
    for p in range(pages):
        body = "\n".join(
            f'      <section className="py-20 bg-white">\n'
            f'        <div className="max-w-7xl mx-auto px-4 text-center">\n'
            f'          <h2 className="text-4xl font-bold text-gray-900 mb-4">{roles[s]}</h2>\n'
            f'          <div className="grid md:grid-cols-3 gap-8">\n'
            + "".join(f'            <Card{(p * 5 + s * 3 + k) % components} title="T" />\n'
                      for k in range(3))
            + '          </div>\n        </div>\n      </section>'
            for s in range(len(roles)))
        (root / "app" / f"page{p}.tsx").write_text(
            f'export default function Page{p}() {{\n  return (\n'
            f'    <main className="bg-white text-gray-900">\n{body}\n'
            f'    </main>\n  );\n}}\n', encoding="utf-8")
    return pages + components


def test_a_mid_size_repo_scans_in_seconds(tmp_path):
    """Guards the quadratic steps: a regression here shows up as minutes."""
    import time

    from aislopfixer.design.project import scan_project

    n = _synthetic_repo(tmp_path, pages=220, components=400)
    started = time.perf_counter()
    report, _ = scan_project(str(tmp_path))
    elapsed = time.perf_counter() - started
    assert report.template_score > 0
    # Lowered from ten seconds once the expansion stopped building a virtual
    # tree for every component file and the loop scan moved from per-element to
    # per-document. The synthetic repo runs in about 1.3s; six is the headroom,
    # not the target.
    assert elapsed < 6.0, f"{n} dosya {elapsed:.1f}s sürdü"


def test_page_comparison_is_capped_and_says_so(tmp_path):
    page = ("<header><h1>Hi</h1></header>"
            "<section><h2>Features</h2></section>"
            "<section><h2>Pricing</h2><p>$9 per month</p></section>"
            "<footer>x</footer>")
    docs = [doc(f"p{i}.html", page) for i in range(210)]
    assert repetition.page_count(docs) == 210
    pairs = repetition.page_pairs(docs)
    assert len(pairs) == 200 * 199 // 2, "the cap bounds the quadratic step"
    obs, *_ = repetition.analyze(docs)
    hit = next(o for o in obs if o.id == "repeat.page_skeleton")
    assert "ilk 200 sayfa" in hit.detail, "a silent truncation reads as full coverage"


# ------------------------------------------------------- type monoculture
def _typed(sizes: list[str]) -> str:
    return "".join(f"<p class='{s}'>line {i}</p>" for i, s in enumerate(sizes))


def test_forty_headings_in_two_sizes_are_a_type_monoculture():
    """The type axis had no monoculture measure and discriminated backwards.

    `cruip-landing` — forty headings, two sizes — scored 0 type repetition
    while `solid-site` scored 77.8. Every other axis has had this measure since
    the first release; typography's repetition came from two absence tests, and
    both stand down as soon as the project's config tunes its ramp.
    """
    doc = parse_document("a.html", "/a.html",
                         _typed(["text-lg"] * 11 + ["text-sm"]))
    found, shares = tells.analyze([doc])
    mono = [o for o in found if o.id == "type.mono_font_size"]
    assert mono and "%92" in mono[0].stat
    assert shares[Axis.TYPE] > 50


def test_a_type_scale_with_real_steps_stays_quiet():
    """Three sizes in use is what the prescription asks for."""
    doc = parse_document("a.html", "/a.html",
                         _typed(["text-4xl", "text-xl", "text-base",
                                 "text-base", "text-sm", "text-base",
                                 "text-xl", "text-base", "text-4xl",
                                 "text-sm", "text-base", "text-xl"]))
    found, _ = tells.analyze([doc])
    assert not [o for o in found if o.id.startswith("type.mono")]
