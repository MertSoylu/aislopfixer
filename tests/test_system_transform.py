"""System derivation, the transform, and the safety properties of writing."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aislopfixer.design import transform
from aislopfixer.design.brief import render as render_brief
from aislopfixer.design.models import DesignReport
from aislopfixer.design.parse import parse_document
from aislopfixer.design.project import scan_project
from aislopfixer.design.system import ARCHETYPES, derive, token_css, write_system
from aislopfixer.design.system.color import contrast_ratio, hsl_of, neutral_ramp, ramp
from aislopfixer.design.system.derive import pick_archetype, project_seed
from aislopfixer.design.system.preview import render as system_preview
from aislopfixer.design.transform.apply import apply_edits, read_text
from aislopfixer.store import Store
from aislopfixer.theme import sparkline

from bench.cases import ROOT as CASE_ROOT


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dst = tmp_path / "slop_saas"
    shutil.copytree(Path(CASE_ROOT) / "slop_saas", dst)
    return dst


# ------------------------------------------------------------------- colour
def test_ramp_keeps_its_hue_at_both_ends():
    """Regression: a saturation-specified ramp lost its tint at L≈0.96."""
    steps = neutral_ramp(32, 0.09)
    light = hsl_of(steps[50])
    assert light is not None and light[1] > 0.2, steps[50]
    assert abs(light[0] - 32) < 12


def test_zero_tint_is_a_true_grey():
    value = neutral_ramp(0, 0.0)[500].lstrip("#")
    assert value[0:2] == value[2:4] == value[4:6]


def test_accent_ramp_is_ordered_light_to_dark():
    steps = ramp(220)
    lights = [hsl_of(steps[s])[2] for s in (950, 700, 500, 200, 50)]
    assert lights == sorted(lights)


# ------------------------------------------------------------------- derive
def test_derivation_is_deterministic(project: Path):
    report, _ = scan_project(str(project))
    a = derive(str(project), report)
    b = derive(str(project), report)
    assert a.colors == b.colors and a.archetype.key == b.archetype.key


def test_archetypes_spread_across_projects():
    picked = {pick_archetype(project_seed(f"/tmp/proj-{i}")).key for i in range(40)}
    assert len(picked) >= 4, picked


def test_every_archetype_produces_readable_pairs():
    report = DesignReport(root="x")
    for arch in ARCHETYPES:
        s = derive("/tmp/x", report, archetype_key=arch.key)
        c = s.colors
        assert contrast_ratio(c["ink"], c["paper"]) >= 7, arch.key
        assert contrast_ratio(c["ink-muted"], c["paper"]) >= 4.5, arch.key
        assert contrast_ratio(c["on-accent"], c["accent"]) >= 4.5, arch.key


def test_a_projects_own_hue_is_kept_over_the_seed():
    report = DesignReport(root="x", palette={"authored": ["#a8442a"]})
    s = derive("/tmp/x", report)
    assert s.inherited_hue
    assert abs(s.accent_hue - (hsl_of("#a8442a")[0])) < 1


def test_emitted_css_carries_both_dialects(project: Path):
    report, _ = scan_project(str(project))
    css = token_css(derive(str(project), report))
    assert "@theme {" in css and ":root {" in css
    assert "--color-accent:" in css and "--spacing-band-open:" in css
    assert css.count("--color-paper:") == 2


def test_write_system_creates_the_token_file(project: Path):
    report, _ = scan_project(str(project))
    written = write_system(str(project), derive(str(project), report))
    assert written and Path(written[0]).exists()


# ---------------------------------------------------------------- transform
def test_transform_lowers_the_score_and_is_idempotent(project: Path):
    report, docs = scan_project(str(project))
    system = derive(str(project), report)
    result = transform.run(str(project), docs, report, system)
    assert result.applied.edits > 0 and not result.applied.failed

    after, docs2 = scan_project(str(project))
    assert after.template_score < report.template_score - 30
    assert after.decision_density > report.decision_density + 20

    again = transform.plan_all(str(project), docs2, after, derive(str(project), after))
    assert again.edits == [], "a second pass must have nothing left to change"


def test_undo_restores_the_original_bytes(project: Path):
    before = (project / "index.html").read_bytes()
    report, docs = scan_project(str(project))
    result = transform.run(str(project), docs, report, derive(str(project), report))
    assert (project / "index.html").read_bytes() != before
    transform.undo(result.applied)
    assert (project / "index.html").read_bytes() == before


def test_a_backup_is_written_once(project: Path):
    report, docs = scan_project(str(project))
    transform.run(str(project), docs, report, derive(str(project), report))
    assert (project / "index.html.aislopfixer.bak").exists()


def test_crlf_and_bom_survive_a_rewrite(tmp_path: Path):
    src = "<!doctype html>\r\n<html><body class=\"bg-white text-gray-900\">x</body></html>\r\n"
    path = tmp_path / "a.html"
    path.write_bytes(b"\xef\xbb\xbf" + src.encode("utf-8"))
    report, docs = scan_project(str(tmp_path))
    transform.run(str(tmp_path), docs, report, derive(str(tmp_path), report),
                  write_tokens=False)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw and b"bg-paper" in raw


def _write(tmp_path: Path, body: str) -> tuple[Path, object]:
    path = tmp_path / "a.jsx"
    path.write_text(body, encoding="utf-8")
    report, docs = scan_project(str(tmp_path))
    plan = transform.plan_all(str(tmp_path), docs, report, derive(str(tmp_path), report))
    return path, plan


def test_class_literals_inside_an_expression_are_rewritten_in_place(tmp_path: Path):
    path, plan = _write(tmp_path,
        "export const A = () => (\n"
        "  <section className={cn('py-20', on && 'bg-white')}>\n"
        "    <p className='text-gray-600'>x</p>\n"
        "  </section>\n"
        ")\n")
    assert plan.skipped_expressions == 0
    text, _, _ = read_text(path)
    after = apply_edits(text, [e for e in plan.edits if e.abs_path == str(path)])
    assert "cn('py-band-narrative', on && 'bg-paper')" in after, after
    assert after.count("cn(") == 1, "the expression's own structure is untouched"


def test_a_class_glued_to_an_interpolation_is_left_alone(tmp_path: Path):
    path, plan = _write(tmp_path,
        "export const A = () => (\n"
        "  <section className={`py-${n} bg-white`}>x</section>\n"
        ")\n")
    text, _, _ = read_text(path)
    after = apply_edits(text, plan.edits)
    assert "py-${n}" in after, "a half-written class must never be rewritten"
    assert "bg-paper" in after, "the whole tokens beside it still are"


def test_a_new_class_never_lands_in_a_conditional_branch(tmp_path: Path):
    """A grid gains columns; if every literal is a branch, it is skipped."""
    path, plan = _write(tmp_path,
        "export const A = () => (\n"
        "  <section className='py-20'><div className={wide ? 'grid grid-cols-3' : 'grid grid-cols-2'}>\n"
        "    <article className='p-6'>a</article><article className='p-6'>b</article>\n"
        "  </div></section>\n"
        ")\n")
    assert plan.skipped_expressions >= 1
    text, _, _ = read_text(path)
    after = apply_edits(text, plan.edits)
    assert "md:grid-cols-12" not in after


def test_an_expression_rewrite_is_idempotent(tmp_path: Path):
    path, plan = _write(tmp_path,
        "export const A = () => (\n"
        "  <section className={`py-20 ${dark ? 'bg-gray-900' : 'bg-white'}`}>\n"
        "    <h2 className='text-4xl'>Hi</h2>\n"
        "  </section>\n"
        ")\n")
    text, _, _ = read_text(path)
    path.write_text(apply_edits(text, plan.edits), encoding="utf-8")
    report2, docs2 = scan_project(str(tmp_path))
    again = transform.plan_all(str(tmp_path), docs2, report2,
                               derive(str(tmp_path), report2))
    assert again.edits == []


def test_apply_edits_refuses_a_moved_span():
    from aislopfixer.design.transform.plan import Edit

    edit = Edit(file="a", abs_path="/a", start=0, end=3, old="abc", new="xyz",
                line=1, kind="token")
    assert apply_edits("abc", [edit]) == "xyz"
    assert apply_edits("zzz", [edit]) == "zzz"


def test_wiring_links_the_token_file_once(project: Path):
    report, docs = scan_project(str(project))
    transform.run(str(project), docs, report, derive(str(project), report))
    text = (project / "index.html").read_text(encoding="utf-8")
    assert text.count("system.css") == 1
    report2, docs2 = scan_project(str(project))
    plan = transform.plan_all(str(project), docs2, report2, derive(str(project), report2))
    assert not any("system.css" in e.new for e in plan.edits)


def test_reading_a_file_reports_its_newline_and_bom(tmp_path: Path):
    path = tmp_path / "x.css"
    path.write_bytes("a{}\r\nb{}".encode("utf-8"))
    text, newline, bom = read_text(path)
    assert newline == "\r\n" and bom is False and "\r" not in text


# -------------------------------------------------------------- store/brief
def test_store_remembers_choices_and_writes_a_report(project: Path):
    store = Store(str(project))
    report, _ = scan_project(str(project))
    store.set_archetype("swiss")
    assert store.toggle_accepted("layout:layout.no_break") is True
    assert store.toggle_accepted("layout:layout.no_break") is False
    store.record_run(report, applied=3)
    path = store.write_report(report)
    assert path and Path(path).exists()
    assert Store(str(project)).archetype == "swiss"
    assert Store(str(project)).history[-1]["edits"] == 3


def test_brief_names_the_system_and_the_acceptance_criteria(project: Path):
    report, _ = scan_project(str(project))
    text = render_brief(report, derive(str(project), report), applied=42)
    assert "Şablon skoru" in text
    assert "42 düzenleme" in text
    assert "Kabul kriteri" in text
    assert "bg-accent" in text


def test_accepted_observations_leave_the_brief(project: Path):
    report, _ = scan_project(str(project))
    target = report.observations[0]
    full = render_brief(report, None)
    trimmed = render_brief(report, None, accepted={target.key})
    assert target.title in full and target.title not in trimmed


def test_a_glued_class_is_counted_not_hidden(tmp_path: Path):
    _, plan = _write(tmp_path,
        "export const A = () => (\n"
        "  <section className={`py-${n} bg-white`}>x</section>\n"
        ")\n")
    assert plan.glued_tokens == 1


# ----------------------------------------------------------------- preview
def test_the_preview_tells_the_archetypes_apart():
    """`s` cycles six systems; a drawing that looks the same is not a choice."""
    report = DesignReport(root="x")
    drawings = {
        arch.key: system_preview(derive("/tmp/x", report, archetype_key=arch.key)).plain
        for arch in ARCHETYPES
    }
    assert len(set(drawings.values())) == len(ARCHETYPES), "two archetypes drew alike"


def test_the_preview_is_drawn_to_a_fixed_scale():
    """Bars normalised per archetype would make every hero band the same length."""
    report = DesignReport(root="x")
    def hero(key: str) -> int:
        for line in system_preview(derive("/tmp/x", report, archetype_key=key)).plain.splitlines():
            if line.strip().startswith("hero"):
                return line.count("█")
        raise AssertionError("no hero band row in the drawing")
    lengths = {a.key: hero(a.key) for a in ARCHETYPES}
    assert len(set(lengths.values())) > 1, lengths


# ------------------------------------------------------------------ history
def test_a_sparkline_reads_on_an_absolute_scale():
    """Auto-scaling would draw 84→81 as a cliff and 5→95 as the same picture."""
    assert sparkline([0, 100]) == "▁█"
    flat = sparkline([84, 82, 81])
    assert len(set(flat)) == 1, flat
    assert sparkline([5, 50, 95]) != flat


def test_a_class_directive_is_never_copied_into_the_static_list(tmp_path: Path):
    """Regression: merging `class:active` into `classes` made it unconditional."""
    path = tmp_path / "a.svelte"
    path.write_text(
        "<section class='py-20'><div class='text-gray-600' class:active={on}>x</div>"
        "</section>\n", encoding="utf-8")
    report, docs = scan_project(str(tmp_path))
    plan = transform.plan_all(str(tmp_path), docs, report, derive(str(tmp_path), report))
    text, _, _ = read_text(path)
    after = apply_edits(text, plan.edits)
    assert "class:active={on}" in after
    assert " active" not in after.split("class:active")[0], after


# --------------------------------------------------------------- plan.diff
def _plan_for(root: Path):
    report, docs = scan_project(str(root))
    system = derive(str(root), report)
    return transform.plan_all(str(root), docs, report, system)


def test_the_exported_patch_is_the_patch_that_would_be_applied():
    """`plan.diff` and the write come out of the same plan and the same edits.

    A tool whose exported diff differs from what it applies cannot be run
    unattended, so the file is compared against the text the applier produces
    rather than against a second rendering of it.
    """
    import difflib

    root = Path(CASE_ROOT) / "slop_saas"
    plan = _plan_for(root)
    patch = transform.plan_diff(plan)
    assert patch.startswith("diff --git a/")
    for abs_path, edits in plan.by_file().items():
        text, _, _ = read_text(Path(abs_path))
        applied = apply_edits(text, edits)
        rel = edits[0].file.replace("\\", "/")
        rebuilt = "".join(difflib.unified_diff(
            text.splitlines(keepends=True), applied.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3))
        assert rebuilt in patch


@pytest.mark.parametrize("case", ["slop_saas", "slop_react", "slop_vue"])
def test_the_exported_patch_passes_git_apply(tmp_path: Path, case: str):
    """The acceptance for the export: git has to accept it, not just look right."""
    import subprocess

    if shutil.which("git") is None:                     # pragma: no cover
        pytest.skip("git yok")
    work = tmp_path / case
    shutil.copytree(Path(CASE_ROOT) / case, work)
    shutil.rmtree(work / ".aislopfixer", ignore_errors=True)
    env = {"GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
           "GIT_CONFIG_SYSTEM": str(tmp_path / "gitconfig-sys"),
           "PATH": __import__("os").environ.get("PATH", "")}
    run = lambda *a: subprocess.run(  # noqa: E731 — local shorthand
        ["git", *a], cwd=work, env=env, capture_output=True, text=True)
    run("init", "-q")
    run("config", "core.autocrlf", "false")
    run("add", "-A")
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    patch = transform.plan_diff(_plan_for(work))
    assert patch, case
    (work / "plan.diff").write_text(patch, encoding="utf-8", newline="\n")
    checked = run("apply", "--check", "plan.diff")
    assert checked.returncode == 0, checked.stderr


# ------------------------------------------------------------- axis filter
def test_applying_one_axis_writes_only_that_axis_and_stays_idempotent(
        project: Path):
    """"Take the colours, leave the layout alone" is the usual first step.

    Two things have to hold for it to be safe: the edits produced are only the
    ones that axis owns, and running the same selection again finds nothing —
    otherwise a partial apply would drift on every pass.
    """
    from aislopfixer.design.models import Axis

    root = str(project)
    report, docs = scan_project(root)
    system = derive(root, report)

    only_colour = transform.plan_all(root, docs, report, system, axes={Axis.COLOR})
    assert only_colour.edits
    assert {e.kind for e in only_colour.edits} == {"token"}

    everything = transform.plan_all(root, docs, report, system)
    assert len(everything.edits) > len(only_colour.edits)

    transform.run(root, docs, report, system, axes={Axis.COLOR})
    again_report, again_docs = scan_project(root)
    again = transform.plan_all(root, again_docs, again_report,
                               derive(root, again_report), axes={Axis.COLOR})
    assert not again.edits


def test_applied_axes_are_remembered_and_cleared_by_undo(tmp_path: Path):
    store = Store(str(tmp_path))
    assert store.applied_axes == set()
    store.add_applied_axes(["color"])
    store.add_applied_axes(["space"])
    assert Store(str(tmp_path)).applied_axes == {"color", "space"}
    store.clear_applied_axes()
    assert Store(str(tmp_path)).applied_axes == set()


# ------------------------------------------------------------------- verify
def test_only_class_lists_change_across_the_whole_corpus():
    """The class-only constraint, checked at byte level on every case.

    It is written into `classmap`'s docstring and was never verified on
    anything bigger than a fixture. `daisyui` takes 1784 edits in one run; one
    mis-anchored span there corrupts hundreds of elements and no other test
    looks. The check masks class values and compares the rest of the file:
    element tree, text, whitespace, line endings.
    """
    from aislopfixer.design.transform.plan import build
    from aislopfixer.design.transform.verify import class_only

    from bench.cases import CASES

    checked = 0
    for case in CASES:
        root = str(Path(CASE_ROOT) / case.name)
        report, docs = scan_project(root)
        plan = build(docs, report, derive(root, report))
        if not plan.edits:
            continue
        checked += 1
        found = class_only(docs, plan)
        assert found.clean, f"{case.name}: {found.violations[:2]}"
    assert checked >= 8, "the corpus must exercise the transform on real cases"


def test_the_rewrite_does_not_leave_a_class_fighting_the_one_it_installed():
    """`tracking-tight` + the `tracking-display` the transform adds is a fight.

    Both reach the browser and the stylesheet's order decides silently. The
    value the transform replaced is exactly what it came to replace, so the
    installed token keeps the property.
    """
    from aislopfixer.design.system.derive import derive as derive_system
    from aislopfixer.design.transform.classmap import Context, rewrite

    system = derive_system("/x", DesignReport(root="/x"))
    out = rewrite(["text-5xl", "tracking-tight", "leading-none"],
                  Context(tag="h1"), system)
    assert "tracking-tight" not in out and "tracking-display" in out
    assert "leading-none" not in out and "leading-display" in out


def test_a_variant_that_repeats_its_own_base_is_dropped():
    """`text-blue-600 dark:text-blue-400` both become the accent role."""
    from aislopfixer.design.system.derive import derive as derive_system
    from aislopfixer.design.transform.classmap import Context, rewrite

    system = derive_system("/x", DesignReport(root="/x"))
    out = rewrite(["text-blue-600", "dark:text-blue-400", "py-16", "lg:py-20"],
                  Context(tag="section", is_band=True, section_role="features"),
                  system)
    assert out.count("text-accent") == 1 and "dark:text-accent" not in out
    assert "lg:py-band-narrative" not in out


def test_two_branches_of_one_ternary_are_not_resolved_against_each_other(
        tmp_path: Path):
    """`cn(reverse ? "lg:order-2" : "lg:order-1")` is one decision, written twice.

    Resolving them against each other emptied a branch — and an empty branch is
    a layout that collapses in exactly the state nobody previewed.
    """
    (tmp_path / "a.jsx").write_text(
        'export default () => (<div className="py-20 bg-white">'
        '<div className={cn(reverse ? "lg:order-2" : "lg:order-1")}>x</div>'
        "</div>);\n", encoding="utf-8")
    report, docs = scan_project(str(tmp_path))
    plan = transform.plan_all(str(tmp_path), docs, report,
                              derive(str(tmp_path), report))
    for edit in plan.edits:
        assert edit.new.strip(), f"a branch was emptied: {edit}"


def test_the_transform_bleeds_one_band_however_many_times_it_is_run(
        project: Path):
    """The break is found by a `w-full` the rewrite then drops as a conflict.

    So a second pass walked to the next full-width element and broke that one
    too — a page that gets worse every time the tool is run on it.
    """
    from aislopfixer.design.transform.plan import _already_bleeding

    def bleeding(root: str) -> int:
        _report, docs = scan_project(root)
        return sum(1 for d in docs for el in d.elements
                   if _already_bleeding(el))

    for _ in range(3):
        report, docs = scan_project(str(project))
        transform.run(str(project), docs, report, derive(str(project), report),
                      write_tokens=False)
    assert bleeding(str(project)) <= 1


def test_the_tool_does_not_recommend_its_transform_on_a_designed_project():
    """`a` is offered disarmed where the tool's own preview says it is not worth it.

    On a project that already has a system, the tool's is narrower: `clean_config`
    goes 15.1 → 17.0 and `clean_studio_large` 11.7 → 14.9. On the rest of the
    clean side the whole plan moves a fraction of a point. A warning printed
    beside a one-key write is not an offer anybody can decline, so the same
    number that prints the warning now decides whether the key is armed.
    """
    from aislopfixer.screens.system import _WORTH_AT

    from bench.cases import CASES

    seen = 0
    for case in CASES:
        root = str(Path(CASE_ROOT) / case.name)
        report, docs = scan_project(root)
        system = derive(root, report)
        after = transform.preview(root, docs, report, system)
        delta = after.template_score - report.template_score
        worth = -delta >= _WORTH_AT
        if case.family == "clean":
            seen += 1
            assert not worth, f"{case.name}: {delta:+.1f} puan önerildi"
        elif case.family == "slop" and case.name != "slop_styled":
            # `slop_styled` has no class attribute the transform can reach; it
            # is the case that proves the mark is withheld, not earned.
            assert worth, f"{case.name}: {delta:+.1f} puan önerilmedi"
    assert seen >= 4
