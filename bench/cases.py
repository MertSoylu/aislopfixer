"""The labeled corpus: real-shaped projects with the band each must land in.

A detector is only worth trusting if it separates cases it has never been tuned
against, so every entry here is a whole small project rather than a snippet,
and each carries the *band* it must fall in rather than an exact number. Bands
leave room for calibration to move without silently changing what the tool
claims; a case that drifts out of its band is a regression, not a rounding
difference.

The pairs matter more than the individuals. ``slop_saas`` and
``mid_human_tailwind`` are built from the same framework, the same palette and
the same era — the only difference is whether anyone made decisions. A tool
that cannot separate those two is measuring Tailwind, not design.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ROOT = os.path.join(os.path.dirname(__file__), "cases")


@dataclass(frozen=True)
class Case:
    name: str
    note: str
    template: tuple[float, float]      # allowed template-score band
    decisions: tuple[float, float]     # allowed decision-density band
    must_observe: tuple[str, ...] = ()   # observation ids that must fire
    must_not_observe: tuple[str, ...] = ()
    # Another case that is *the same design in another stack*. The two must land
    # within TWIN_MARGIN of each other; a gap wider than that is the tool
    # measuring the framework instead of the design.
    twin_of: str = ""
    # "slop" / "middle" / "clean" take part in the separation margin — the one
    # number that says whether the tool can tell designed from generated.
    # "probe" cases exist to pin one observation and are deliberately left out
    # of it: they are fragments, and averaging them in would flatter the margin
    # or wreck it for reasons that have nothing to do with separation.
    family: str = "probe"

    @property
    def path(self) -> str:
        return os.path.join(ROOT, self.name)


TWIN_MARGIN = 5.0


CASES: tuple[Case, ...] = (
    Case(
        name="slop_saas",
        family="slop",
        note="Generated Tailwind landing page — accessible, clean, entirely templated",
        template=(70.0, 100.0),
        decisions=(0.0, 35.0),
        must_observe=(
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.center_monoculture", "color.stock_palette",
            "repeat.canonical_order", "copy.stock_headings",
            "color.low_contrast",
        ),
        # The HTML twin writes its bands out one by one, so there is no shared
        # wrapper to report — the observation must be about this project's
        # shape, not about the tool's usual complaint.
        must_not_observe=("space.shared_band_wrapper",),
    ),
    Case(
        name="slop_tr",
        family="slop",
        note="The same template in Turkish — the section reader has to speak it too",
        template=(70.0, 100.0),
        decisions=(0.0, 35.0),
        # The canonical run is the point: none of the English vocabularies match
        # a word on this page, so before the Turkish patterns every band read as
        # `content` and the structural half of the score went silent on exactly
        # the pages this tool's own users write.
        must_observe=(
            "repeat.canonical_order", "space.uniform_rhythm",
            "layout.symmetric_grids", "color.stock_palette",
        ),
        must_not_observe=("space.shared_band_wrapper",),
    ),
    Case(
        name="slop_react",
        family="slop",
        note="The same template as a componentised Next.js page",
        template=(70.0, 100.0),
        decisions=(0.0, 35.0),
        # Deliberately the same band and the same required observations as
        # slop_saas: it is the same design, and a componentised template that
        # scores better than its copy-pasted twin is a hole in the measurement,
        # not a better page. ``twin_of`` holds that pair to five points.
        must_observe=(
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.center_monoculture", "color.stock_palette",
            "repeat.canonical_order", "repeat.block_shape",
            "copy.stock_headings", "space.shared_band_wrapper",
        ),
        twin_of="slop_saas",
    ),
    Case(
        name="slop_vue",
        family="slop",
        note="The same template again as a Vue single-file component tree",
        template=(70.0, 100.0),
        decisions=(0.0, 35.0),
        must_observe=(
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.center_monoculture", "color.stock_palette",
            "repeat.canonical_order", "repeat.block_shape",
            "copy.stock_headings", "space.shared_band_wrapper",
        ),
        twin_of="slop_saas",
    ),
    Case(
        name="slop_styled",
        family="slop",
        note="The same template once more in styled-components — no class attribute anywhere",
        template=(70.0, 100.0),
        decisions=(0.0, 35.0),
        # The dialect twin. Every value here is spelled in raw CSS (`padding:
        # 80px 0`, `#4f46e5`) rather than as a utility, and the score has to be
        # the same: a project that converts its Tailwind to CSS has not designed
        # anything, and a tool that rewards it is measuring syntax.
        must_observe=(
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.center_monoculture", "color.stock_palette",
            "repeat.canonical_order", "repeat.block_shape",
            "copy.stock_headings", "space.shared_band_wrapper",
        ),
        twin_of="slop_saas",
    ),
    Case(
        name="slop_kit",
        family="slop",
        note="A multi-page Next.js landing kit — 300+ rendered elements, its own config",
        template=(70.0, 100.0),
        decisions=(0.0, 40.0),
        # The size case. Every other slop case is one page of 26–116 elements,
        # and the decision target used to stop growing at 120 — so nothing in
        # the corpus ever crossed the saturation point, and eight real landing
        # templates were graded "designed" for two releases running. This one
        # renders 300+ elements out of two pages and three shared components,
        # ships the `tailwind.config.js` every kit ships, and must still land in
        # the slop band. Its clean twin is `clean_studio_large`.
        must_observe=(
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.center_monoculture", "repeat.canonical_order",
            "repeat.block_shape", "copy.stock_headings",
            "space.shared_band_wrapper",
        ),
    ),
    Case(
        name="clean_studio_large",
        family="clean",
        note="A multi-page studio site of the same shape and size, with real decisions",
        template=(0.0, 20.0),
        decisions=(70.0, 100.0),
        # Deliberately *not* a `twin_of` of `slop_kit`: a twin is the same design
        # in another stack and must score the same. This is the opposite design
        # in the same stack, at the same size and file count, and the pair's job
        # is the separation margin — the number that says whether volume or
        # design is being measured.
        must_not_observe=(
            "color.stock_palette", "space.uniform_rhythm",
            "layout.symmetric_grids", "layout.center_monoculture",
            "repeat.canonical_order", "repeat.page_skeleton",
            "copy.stock_headings", "layout.no_break", "type.untuned_display",
        ),
    ),
    Case(
        name="crafted_kit",
        family="middle",
        note="A commercial landing template: designers made it, and everyone will use it",
        # The case that separates two claims `bench/field.md` kept confusing.
        # "Sold as a starting point" and "nobody decided anything" are different
        # sentences, and only the second is what the two axes measure. This page
        # has a tuned type ramp, authored easing curves and durations, a
        # full-bleed band and an asymmetric hero — and a stock indigo palette on
        # a stock spacing scale. It must land in the *middle*: above the
        # generated kit, below a site somebody designed for themselves.
        #
        # `bench/field.py` reads this band directly for its `crafted` side, so
        # the two cannot drift apart.
        template=(25.0, 60.0),
        decisions=(45.0, 80.0),
        must_observe=("color.stock_palette", "color.default_accent"),
        must_not_observe=(
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.center_monoculture", "layout.no_break",
            "type.untuned_display", "copy.stock_headings",
            "repeat.canonical_order",
        ),
    ),
    Case(
        name="clean_svelte",
        family="clean",
        note="Authored SFC project: own tokens, four rhythms, asymmetric grid",
        template=(0.0, 18.0),
        decisions=(80.0, 100.0),
        must_not_observe=(
            "color.stock_palette", "space.uniform_rhythm",
            "layout.symmetric_grids", "layout.center_monoculture",
            "repeat.block_shape", "repeat.canonical_order",
            "copy.stock_headings", "layout.no_break",
            "color.low_contrast", "color.partial_dark",
            "space.shared_band_wrapper",
        ),
    ),
    Case(
        name="mid_human_tailwind",
        family="middle",
        note="Hand-written, stock utilities only, but varied structure and real copy",
        template=(18.0, 50.0),
        decisions=(35.0, 75.0),
        must_not_observe=(
            "space.uniform_rhythm", "layout.center_monoculture",
            "repeat.canonical_order", "repeat.block_shape",
            "copy.stock_headings", "layout.no_break",
            "color.low_contrast",
        ),
    ),
    Case(
        name="clean_studio",
        family="clean",
        note="Authored token system, varied rhythm, asymmetric grid",
        template=(0.0, 18.0),
        decisions=(80.0, 100.0),
        must_not_observe=(
            "color.stock_palette", "space.uniform_rhythm",
            "layout.symmetric_grids", "type.untuned_display",
            "material.uniform_card", "copy.stock_headings",
            "color.low_contrast", "color.partial_focus",
        ),
    ),
    Case(
        name="clean_config",
        family="clean",
        note="Stock utilities everywhere — the one system is a type ramp in tailwind.config.js",
        template=(0.0, 18.0),
        # Widened from (80, 100) when the decision target moved off element
        # count and onto vocabulary size. The case's *typography* is a system
        # and still scores like one; its spacing and layout are seventeen and
        # thirteen stock Tailwind values, and the old target — which stopped
        # growing at 120 elements — was simply too small for a page that uses
        # that many. The template band, which is what the tool tells the user,
        # is unchanged and the case now lands well inside it.
        decisions=(65.0, 100.0),
        # The case exists to prove the config is read: every typographic class
        # on the page (`text-lg`, `text-display`) is a name Tailwind also ships,
        # and reads as a default until the config file is opened. Without that
        # step the typography axis scores 47.8 instead of 100 and the most
        # careful project in the corpus is graded as the least.
        must_not_observe=(
            "type.no_decisions", "type.no_type_choice", "type.untuned_display",
            "color.stock_palette", "space.uniform_rhythm",
            "layout.symmetric_grids", "copy.stock_headings",
        ),
    ),
    Case(
        name="clean_utility",
        family="clean",
        note="A page written entirely in arbitrary values, with a config behind it",
        template=(0.0, 35.0),
        decisions=(55.0, 100.0),
        must_not_observe=("type.no_decisions", "color.no_decisions",
                          "color.stock_palette", "space.uniform_rhythm"),
    ),
    Case(
        name="clean_css",
        family="clean",
        # The twin rule was tested four times on the slop side and never once on
        # the clean side, and the gap it exists to catch was real: `py-[2.5rem]`
        # was a decision and `padding: 2.5rem` was a default, so the same design
        # scored 8 points apart depending on the dialect. Two things came out of
        # it — arbitrary values now go through the same shipped-value table as
        # raw CSS, and an external stylesheet is finally attached to the
        # elements it styles, which no structural metric had ever seen.
        note="The same design as clean_utility, written as raw CSS",
        template=(0.0, 35.0),
        decisions=(50.0, 100.0),
        twin_of="clean_utility",
        must_not_observe=("type.no_decisions", "color.no_decisions",
                          "space.no_decisions", "layout.no_decisions"),
    ),
    Case(
        name="clean_modules",
        family="clean",
        note="Authored CSS Modules — no utility class anywhere, every style behind styles.x",
        template=(0.0, 18.0),
        decisions=(80.0, 100.0),
        # The clean twin for the module resolver. Before it existed every
        # element here carried nothing and the project measured as empty, which
        # reads as clean for exactly the wrong reason — so the requirement is
        # not just the band but that the styles were found at all.
        must_not_observe=(
            "type.no_decisions", "color.no_decisions", "space.no_decisions",
            "layout.no_decisions", "color.stock_palette",
            "space.uniform_rhythm", "layout.symmetric_grids",
            "layout.no_break", "copy.stock_headings",
        ),
    ),
    Case(
        name="half_dark_kit",
        note="A dashboard that claims a dark mode and finishes half of it",
        template=(50.0, 85.0),
        decisions=(0.0, 50.0),
        must_observe=("color.partial_dark", "color.partial_focus"),
        twin_of="clean_dark_kit",
    ),
    Case(
        name="clean_dark_kit",
        note="The same dashboard with the claim finished — no state gaps",
        template=(50.0, 85.0),
        decisions=(0.0, 50.0),
        must_not_observe=("color.partial_dark", "color.partial_focus"),
    ),
)
