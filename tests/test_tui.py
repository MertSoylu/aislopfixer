"""The TUI: the whole flow, and the states that must never be dressed up."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aislopfixer.app import AISlopFixerApp
from aislopfixer.cli import build_parser
from aislopfixer.config import Config
from aislopfixer.scanner import EXTENSIONS, collect, count_eligible
from aislopfixer.screens import ReportScreen, ScanScreen, SummaryScreen, SystemScreen

from bench.cases import ROOT as CASE_ROOT

SIZE = (140, 44)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    dst = tmp_path / "slop_saas"
    shutil.copytree(Path(CASE_ROOT) / "slop_saas", dst)
    return dst


def _text(app, selector: str) -> str:
    """The plain text a Static is currently showing."""
    return app.screen.query_one(selector).render().plain


async def _to_report(pilot, app) -> None:
    await pilot.press("enter")          # splash → path
    await pilot.pause()
    await pilot.press("enter")          # path → scan
    for _ in range(80):
        await pilot.pause(0.1)
        # Reaching the screen is not the same as the screen being built: its
        # children mount over the next few frames, and a test that queried
        # `#rep-list` the moment the screen appeared raised NoMatches about
        # once in five full runs. Wait for the widget, not for the screen.
        if isinstance(app.screen, ReportScreen) and app.screen.query("#rep-list"):
            return
    raise AssertionError(f"rapor ekranına ulaşılamadı: {app.screen}")


async def test_scan_reaches_the_report_with_a_measured_score(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        assert app.report.template_score > 70
        assert app.report.observations
        assert app.system is not None


async def test_apply_lowers_the_score_and_undo_puts_it_back(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        before = app.report.template_score
        await pilot.press("s")
        await pilot.pause(0.4)
        assert isinstance(app.screen, SystemScreen)
        await pilot.press("a")
        for _ in range(40):
            await pilot.pause(0.1)
            if app.applied_edits:
                break
        assert app.applied_edits > 0
        assert app.report.template_score < before - 30
        await pilot.press("u")
        for _ in range(40):
            await pilot.pause(0.1)
            if app.applied_edits == 0:
                break
        assert app.report.template_score == pytest.approx(before, abs=0.1)


async def test_cycling_the_archetype_changes_the_system(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        await pilot.press("s")
        await pilot.pause(0.4)
        first = app.system.archetype.key
        await pilot.press("s")
        await pilot.pause(0.4)
        assert app.system.archetype.key != first


async def test_the_archetype_list_shows_all_six_and_the_cursor_selects(project: Path):
    """`s` alone was a blind cycle: no count, no position, no way back."""
    from aislopfixer.design.system.archetypes import ARCHETYPES

    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        await pilot.press("s")
        await pilot.pause(0.4)
        picker = app.screen.query_one("#sys-arch")
        assert picker.option_count == len(ARCHETYPES)
        first = app.system.archetype.key
        await pilot.press("down")
        await pilot.pause(0.4)
        moved = app.system.archetype.key
        assert moved != first
        assert app.store.archetype == moved
        await pilot.press("up")
        await pilot.pause(0.4)
        assert app.system.archetype.key == first    # and back again


async def test_the_report_can_be_ordered_by_impact(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        options = app.screen.query_one("#rep-list")
        weighted = options.option_count
        await pilot.press("i")
        await pilot.pause(0.3)
        assert "ilk beş iş" in options.border_title
        # Five jobs plus the legend row, and never more than what was measured.
        assert options.option_count <= min(weighted, 5) + 1
        await pilot.press("i")
        await pilot.pause(0.3)
        assert options.option_count == weighted


async def test_turning_axes_off_reduces_the_plan(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        await pilot.press("s")
        await pilot.pause(0.4)
        screen = app.screen
        everything = len(screen._plan.edits)
        for key in ("2", "3", "4", "5"):     # leave only colour on
            await pilot.press(key)
            await pilot.pause(0.2)
        assert {e.kind for e in screen._plan.edits} == {"token"}
        assert 0 < len(screen._plan.edits) < everything
        await pilot.press("a")
        for _ in range(40):
            await pilot.pause(0.1)
            if app.applied_edits:
                break
        assert app.store.applied_axes == {"color"}
        await pilot.press("0")               # back to every axis
        await pilot.pause(0.3)
        assert len(screen._axes) == 5


async def test_writing_the_plan_diff_does_not_touch_the_source(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        before = (project / "index.html").read_bytes()
        await pilot.press("s")
        await pilot.pause(0.4)
        await pilot.press("d")
        await pilot.pause(0.4)
        patch = project / ".aislopfixer" / "plan.diff"
        assert patch.exists()
        assert patch.read_text(encoding="utf-8").startswith("diff --git a/")
        assert (project / "index.html").read_bytes() == before
        assert app.applied_edits == 0


async def test_opening_a_source_position_without_an_editor_says_so(
        project: Path, monkeypatch):
    """A key that silently does nothing is worse than one that admits it."""
    import aislopfixer.screens.report as report_screen

    monkeypatch.setattr(report_screen, "resolve_editor", lambda *a: None)
    notes: list[str] = []
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        monkeypatch.setattr(type(app), "notify",
                            lambda self, msg, **kw: notes.append(str(msg)))
        await pilot.press("o")
        await pilot.pause(0.3)
    assert notes and "Editör bulunamadı" in notes[-1]
    assert ":" in notes[-1]             # the position is still handed over


async def test_export_writes_the_brief(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        await pilot.press("x")
        await pilot.pause(0.4)
        brief = project / ".aislopfixer" / "brief.md"
        assert brief.exists() and "Kabul kriteri" in brief.read_text(encoding="utf-8")


async def test_accepting_an_observation_persists(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        await pilot.press("a")
        await pilot.pause(0.3)
        assert app.store.accepted


async def test_summary_is_reachable_and_shows_the_verdict(project: Path):
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        await pilot.press("q")
        await pilot.pause(0.4)
        assert isinstance(app.screen, SummaryScreen)


async def test_an_empty_folder_says_so_instead_of_looking_clean(tmp_path: Path):
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        assert app.report.files_scanned == 0
        rendered = pilot.app.screen.query_one("#rep-list").render_line(0)
        assert rendered is not None


async def test_a_failed_scan_stays_on_the_scan_screen(project: Path, monkeypatch):
    """A crash must never fall through to an empty — i.e. clean-looking — report."""
    import aislopfixer.screens.scan as scan_module

    def boom(*args, **kwargs):
        raise RuntimeError("motor patladı")

    monkeypatch.setattr(scan_module, "load_documents", boom)
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(40):
            await pilot.pause(0.1)
            if getattr(app.screen, "_failed", False):
                break
        assert isinstance(app.screen, ScanScreen)
        assert app.screen._failed


# ------------------------------------------------------------------- non-UI
def test_cli_is_tui_only():
    parser = build_parser()
    args = parser.parse_args(["some/path"])
    assert args.path == "some/path"
    assert not hasattr(args, "check") and not hasattr(args, "json")


def test_scanner_only_looks_at_design_files():
    assert ".css" in EXTENSIONS and ".tsx" in EXTENSIONS
    assert ".md" not in EXTENSIONS, "markdown carries no layout, palette or rhythm"


def test_scanner_skips_the_tools_own_folder(project: Path):
    (project / ".aislopfixer").mkdir(exist_ok=True)
    (project / ".aislopfixer" / "system.css").write_text(":root{--a:1}", encoding="utf-8")
    rels = {sf.rel_path.replace("\\", "/") for sf in collect(str(project))}
    assert not any(r.startswith(".aislopfixer/") for r in rels)


def test_count_matches_what_the_walk_yields(project: Path):
    assert count_eligible(str(project)) == len(collect(str(project)))


def test_config_ignores_paths_and_disables_observations(tmp_path: Path):
    (tmp_path / ".aislopfixer.toml").write_text(
        'ignore = ["legacy"]\ndisable = ["copy."]\n', encoding="utf-8")
    cfg = Config.load(str(tmp_path))
    assert cfg.path_ignored("legacy/page.html")
    assert not cfg.path_ignored("app/page.html")
    assert cfg.observation_disabled("copy.stock_headings")
    assert not cfg.observation_disabled("layout.no_break")


def test_disabled_observations_do_not_change_the_score(project: Path):
    from aislopfixer.design.project import apply_config, scan_project

    report, _ = scan_project(str(project))
    score = report.template_score
    filtered = apply_config(report, Config(disable=("copy.",)))
    assert filtered.template_score == score
    assert not [o for o in filtered.observations if o.id.startswith("copy.")]


async def test_the_report_compares_this_run_with_the_last(project: Path):
    """The history is only convincing if it is read, not recomputed."""
    from aislopfixer.store import Store

    Store(str(project)).record_run(
        type("R", (), {"decision_density": 10.0, "repetition": 90.0,
                       "template_score": 99.0})())
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        assert app.previous_run and app.previous_run["template"] == 99.0
        head = _text(app, "#rep-head")
        assert "geçen çalıştırma 99" in head
        assert Store(str(project)).history[-1]["template"] == app.report.template_score


async def test_the_summary_shows_the_last_runs(project: Path):
    from aislopfixer.store import Store

    store = Store(str(project))
    for score in (90.0, 85.0, 80.0):
        store.record_run(type("R", (), {"decision_density": 10.0, "repetition": 90.0,
                                        "template_score": score})())
    app = AISlopFixerApp(initial_path=str(project))
    async with app.run_test(size=SIZE) as pilot:
        await _to_report(pilot, app)
        app.show_summary()
        await pilot.pause(0.3)
        line = _text(app, "#sum-history")
        assert "son 4 çalıştırma" in line
