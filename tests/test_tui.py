from aislopfixer.app import AISlopFixerApp


async def test_app_boots_scans_and_collects(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, hello.\n"
        '<a href="#">x</a>\n',
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")     # splash -> scan
        await pilot.pause(2.0)         # scan worker + transition timer -> results
        assert app.findings, "expected findings after scan"
        # results screen is active
        assert app.screen.__class__.__name__ == "ResultsScreen"


async def test_clean_project_summary(tmp_path):
    (tmp_path / "page.html").write_text(
        "<p>Our bakery opens at 8am on Main Street downtown.</p>\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(2.0)
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
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(2.0)
        assert not app.findings, "expected a clean project"
        for key in ("f", "i", "a", "s", "e", "p"):
            await pilot.press(key)
            await pilot.pause(0.05)
        assert app.screen.__class__.__name__ == "ResultsScreen"


async def test_scan_writes_report_folder(tmp_path):
    (tmp_path / "index.html").write_text(
        "<p>We delve into a tapestry of solutions.</p>\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(2.0)
    assert (tmp_path / ".aislopfixer" / "report.md").exists()


async def _drive_to_summary(pilot, app):
    await pilot.pause()
    await pilot.press("enter")     # splash -> scan
    await pilot.pause(2.0)         # scan -> results
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
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(2.0)
        assert app.screen.__class__.__name__ == "ResultsScreen"
        assert "on" in app.screen.query_one("#guard").classes
