from aislopfixer.app import AISlopFixerApp


async def _begin_scan(pilot):
    """Splash -> path (pre-filled, confirm) -> scan."""
    await pilot.pause()
    await pilot.press("enter")     # splash -> path screen
    await pilot.pause(0.1)
    await pilot.press("enter")     # path pre-filled & valid -> begin scan
    await pilot.pause(2.0)         # scan worker + transition timer -> results


async def test_app_boots_scans_and_collects(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n"
        '<a href="#">x</a>\n',
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        assert app.findings, "expected findings after scan"
        # results screen is active
        assert app.screen.__class__.__name__ == "ResultsScreen"


async def test_first_launch_asks_for_path(tmp_path):
    # Even with a valid PATH arg, the app should stop on the path screen
    # first (pre-filled) rather than jumping straight into a scan.
    (tmp_path / "index.html").write_text("<p>hi</p>\n", encoding="utf-8")
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")     # splash -> path screen
        await pilot.pause(0.1)
        assert app.screen.__class__.__name__ == "PathScreen"
        assert app.screen.query_one("#path-input").value == str(tmp_path)


async def test_clean_project_summary(tmp_path):
    (tmp_path / "page.html").write_text(
        "<p>Our bakery opens at 8am on Main Street downtown.</p>\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        # no AI leaks in clean content
        assert all(f.category.name != "AI_LEAK" for f in app.findings)


async def test_clean_project_actions_do_not_crash(tmp_path):
    # Regression: pressing a command on a clean (no-findings) results screen
    # used to crash because there was no tree to query.
    (tmp_path / "page.html").write_text(
        "<p>Our bakery opens at 8am downtown.</p>\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        assert not app.findings, "expected a clean project"
        for key in ("f", "i", "a", "s", "e", "p", "x", "c"):
            await pilot.press(key)
            await pilot.pause(0.05)
        assert app.screen.__class__.__name__ == "ResultsScreen"


def test_help_body_groups_keys_under_section_headers():
    from aislopfixer.screens.modal import HelpModal

    m = HelpModal([("SECTION A", ""), ("f", "fix"), ("1 2 3", "filter"), ("SECTION B", ""), ("q", "quit")])
    text = m._body().plain
    assert "SECTION A" in text and "SECTION B" in text
    # chip width sized to widest key ("1 2 3"), not the section headers
    assert " 1 2 3 " in text
    assert "  f    " in text


async def test_help_modal_opens_and_closes(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("question_mark")
        await pilot.pause(0.1)
        assert app.screen.__class__.__name__ == "HelpModal"
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.screen.__class__.__name__ == "ResultsScreen"


async def test_results_hint_teaches_the_fix_brief(tmp_path):
    # a manual-only finding: the hint must point at `x` / the AI fix brief
    (tmp_path / "app.js").write_text(
        "const q = `SELECT * FROM users WHERE id = ${userId}`;\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        screen = app.screen
        assert screen.query_one("#results-hint") is not None
        hint = screen._brief_hint().plain
        assert "AI fix brief" in hint
        assert "need judgement" in hint


async def test_confidence_floor_cycles_and_filters(tmp_path):
    (tmp_path / "index.html").write_text(
        "<p>As an AI language model, hello.</p>\n"
        '<a href="#">x</a>\n',
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        screen = app.screen
        assert screen._conf == 0.0
        await pilot.press("c")
        await pilot.pause(0.1)
        assert screen._conf == 0.45
        assert all(f.confidence >= 0.45 for f in screen._visible())
        # full cycle returns to "show all"
        for _ in range(3):
            await pilot.press("c")
            await pilot.pause(0.05)
        assert screen._conf == 0.0


async def test_scan_writes_report_folder(tmp_path):
    (tmp_path / "index.html").write_text(
        "<p>We delve into a tapestry of solutions.</p>\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
    assert (tmp_path / ".aislopfixer" / "report.md").exists()


async def _drive_to_summary(pilot, app):
    await _begin_scan(pilot)
    assert app.screen.__class__.__name__ == "ResultsScreen"
    await pilot.press("q")         # results -> summary
    await pilot.pause(0.3)
    assert app.screen.__class__.__name__ == "SummaryScreen"


async def test_summary_scan_again_returns_to_scan(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _drive_to_summary(pilot, app)
        await pilot.press("r")     # scan again -> re-enters the scan pipeline
        await pilot.pause()
        # left the summary and re-entered scanning (a tiny project may already
        # have advanced to results by the time we look)
        assert app.screen.__class__.__name__ in ("ScanScreen", "ResultsScreen")


async def test_summary_new_folder_returns_to_path(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _drive_to_summary(pilot, app)
        await pilot.press("n")     # new folder
        await pilot.pause(0.3)
        assert app.screen.__class__.__name__ == "PathScreen"
        # path picker is prefilled with the previous target
        assert app.screen.query_one("#path-input").value == str(tmp_path)


async def test_too_small_guard_shows_and_hides(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n", encoding="utf-8"
    )
    # cramped terminal -> guard visible on the splash
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test(size=(40, 12)) as pilot:
        await pilot.pause()
        assert "on" in app.screen.query_one("#guard").classes

    # roomy terminal -> guard hidden
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert "on" not in app.screen.query_one("#guard").classes


async def test_results_guard_visible_when_narrow(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test(size=(70, 19)) as pilot:
        await _begin_scan(pilot)
        assert app.screen.__class__.__name__ == "ResultsScreen"
        assert "on" in app.screen.query_one("#guard").classes
