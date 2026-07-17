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


def test_source_block_highlights_the_match_at_its_column():
    # Two identical tokens on the line: the highlight must sit at the
    # finding's column, not on the first occurrence found by substring search.
    from aislopfixer.engine.models import Category, Finding, Fixability, Severity
    from aislopfixer.screens.results import ResultsScreen

    f = Finding(
        rule_id="x", category=Category.PLACEHOLDER, severity=Severity.INFO,
        message="m", file="a.html", abs_path="/a.html",
        line=1, col=10, start=9, end=13,
        snippet="x href y href z", matched_text="href",
        fixability=Fixability.MANUAL,
    )
    t = ResultsScreen([])._source_block(f)
    gutter = len("    1 │ ")  # line number + separator prefix
    hits = [
        (s.start, s.end) for s in t.spans
        if "on" in str(s.style) and t.plain[s.start:s.end] == "href"
    ]
    assert hits == [(gutter + 9, gutter + 13)]


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


async def test_results_hint_leads_on_the_impact_split(tmp_path):
    # a manual-only finding: the hint leads on what is at stake, and `x` is
    # taught by the footer — the hint is no_wrap and a tail about the fix brief
    # was simply cut off at 80 columns.
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
        assert "1 application problem(s)" in hint
        assert len(hint) <= 78, f"must survive an 80-col terminal: {hint!r}"
        assert any(
            b.key == "x" and b.show for b in screen.BINDINGS
        ), "the footer is what teaches x now"


async def test_results_hint_separates_problems_from_warnings(tmp_path):
    """The headline is application problems — buzzwords must not pad the count."""
    (tmp_path / "index.html").write_text(
        "<p>Our cutting-edge, seamless, world-class platform.</p>\n"
        '<a href="#">Get started</a>\n',
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        screen = app.screen
        findings = screen._findings
        hint = screen._brief_hint().plain
    # placeholder.dead_href is the only application problem here; the three
    # buzzwords are warnings and must be counted separately.
    problems = [f for f in findings if f.impact.is_application]
    assert {f.rule_id for f in problems} == {"placeholder.dead_href"}
    assert "1 application problem(s)" in hint
    assert "simple warning(s)" in hint


async def test_results_tree_tags_problems_and_sorts_them_first(tmp_path):
    """A BROKEN finding outranks a higher-confidence buzzword in the same file."""
    (tmp_path / "index.html").write_text(
        "<p>Our cutting-edge, seamless, world-class, best-in-class platform "
        "will revolutionize and supercharge your synergy.</p>\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        screen = app.screen
        buzz = next(f for f in screen._findings if f.rule_id.startswith("buzzword."))
        # POLISH findings carry no tag — an untagged row *is* the "just taste"
        # signal, so a tag on every row would mark nothing.
        assert "BROKEN" not in screen._leaf_label(buzz).plain
        assert "RISKY" not in screen._leaf_label(buzz).plain
        detail = screen._detail(buzz).plain
        assert "POLISH" in detail
        assert "not a defect" in detail


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


async def test_empty_folder_says_nothing_to_scan(tmp_path):
    # A folder with no scannable files is not a "clean project" — the banner
    # must say there was nothing to check, not that no slop was found.
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        assert app.screen.__class__.__name__ == "ResultsScreen"
        assert app.files_scanned == 0
        banner = app.screen._clean_banner().plain
        assert "NOTHING TO SCAN" in banner
        assert "NO SLOP DETECTED" not in banner


async def test_scanned_clean_project_reports_file_count(tmp_path):
    (tmp_path / "page.html").write_text(
        "<p>Our bakery opens at 8am downtown.</p>\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        assert app.files_scanned == 1
        banner = app.screen._clean_banner().plain
        assert "NO SLOP DETECTED" in banner
        assert "1 file(s) scanned" in banner


async def test_failed_scan_stays_and_offers_a_way_out(tmp_path, monkeypatch):
    # A crashed scan must never be dressed up as a clean result screen.
    (tmp_path / "index.html").write_text("<p>hi</p>\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr("aislopfixer.screens.scan.scan_project", boom)
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        assert app.screen.__class__.__name__ == "ScanScreen"
        assert app.screen._failed
        await pilot.press("n")             # new folder is offered as a way out
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "PathScreen"


async def test_bulk_fix_confirm_accepts_enter(tmp_path):
    p = tmp_path / "index.html"
    p.write_text(
        "As an AI language model, I cannot browse.\n<p>keep</p>\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("p")             # bulk auto-fix -> confirm modal
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "ConfirmModal"
        await pilot.press("enter")         # Enter must confirm, same as y
        await pilot.pause(0.3)
    assert "As an AI" not in p.read_text(encoding="utf-8")


async def _to_category_row(pilot):
    """Move the cursor from the auto-selected first finding up to its category."""
    await pilot.press("up")        # leaf -> file
    await pilot.press("up")        # file -> category
    await pilot.pause(0.1)


async def test_diff_modal_previews_the_fix(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, I cannot browse.\n<p>keep</p>\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("d")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "DiffModal"
        assert "As an AI language model" in app.screen._diff
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "ResultsScreen"


async def test_undo_restores_file_and_status(tmp_path):
    p = tmp_path / "index.html"
    original = "As an AI language model, I cannot browse.\n<p>keep</p>\n"
    p.write_text(original, encoding="utf-8")
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("f")             # auto-fix deletes the leak line
        await pilot.pause(0.3)
        assert "As an AI" not in p.read_text(encoding="utf-8")
        await pilot.press("u")             # undo restores the file
        await pilot.pause(0.3)
        assert p.read_text(encoding="utf-8") == original
        from aislopfixer.engine.models import Status
        leak = next(
            f for f in app.screen._findings if f.rule_id.startswith("ai_leak")
        )
        assert leak.status is Status.OPEN


async def test_branch_skip_bulk_skips_whole_category(tmp_path):
    (tmp_path / "index.html").write_text(
        "As an AI language model, one.\n"
        "As an AI language model, two.\n",
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await _to_category_row(pilot)
        # on the category row, s must offer a branch-wide skip
        await pilot.press("s")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "ConfirmModal"
        await pilot.press("y")
        await pilot.pause(0.3)
        from aislopfixer.engine.models import Status
        leaks = [
            f for f in app.screen._findings if f.rule_id.startswith("ai_leak")
        ]
        assert leaks and all(f.status is Status.SKIPPED for f in leaks)


async def test_prompt_modal_warns_on_implausible_url(tmp_path):
    p = tmp_path / "index.html"
    p.write_text('<a href="#">contact</a>\n', encoding="utf-8")
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("f")             # PROMPT fix -> value modal
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "PromptModal"
        for ch in "asdf":
            await pilot.press(ch)
        await pilot.press("enter")         # implausible URL -> warned, stays open
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "PromptModal"
        await pilot.press("enter")         # explicit override applies it
        await pilot.pause(0.3)
    assert 'href="asdf"' in p.read_text(encoding="utf-8")


async def test_scan_esc_cancels_back_to_path(tmp_path, monkeypatch):
    import time as _time

    (tmp_path / "index.html").write_text("<p>hi</p>\n", encoding="utf-8")

    def slow_scan(path, store=None, on_file=None, on_cross_start=None, config=None):
        from aislopfixer.engine.models import SourceFile
        for i in range(300):
            _time.sleep(0.01)
            if on_file is not None:
                on_file(SourceFile("x", f"f{i}.html", ""), [])
        return []

    monkeypatch.setattr("aislopfixer.screens.scan.scan_project", slow_scan)
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.3)             # scan is underway
        assert app.screen.__class__.__name__ == "ScanScreen"
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert app.screen.__class__.__name__ == "PathScreen"


async def test_bulk_fix_fixpoint_reports_unmasked_finding(tmp_path):
    # `# 🎯 Conclusion`: bulk-fixing the emoji unmasks a boilerplate heading —
    # the fixpoint pass must surface it in the same action.
    (tmp_path / "notes.md").write_text(
        "# 🎯 Conclusion\n\nSome text.\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("p")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "ConfirmModal"
        await pilot.press("y")
        await pilot.pause(0.5)
        rules = {f.rule_id for f in app.screen._findings}
        assert "md.boilerplate_section" in rules
    text = (tmp_path / "notes.md").read_text(encoding="utf-8")
    assert text.startswith("# Conclusion")


async def test_summary_counters_are_actually_visible(tmp_path):
    """`height: 3` could not fit 4 rows of chrome, so the content box was 0.

    The four headline counters rendered as a blank gap between two rules — on
    the last screen of the flow, and in the committed README screenshot.
    """
    (tmp_path / "index.html").write_text(
        "<p>Our seamless, cutting-edge platform.</p>\n", encoding="utf-8"
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        await pilot.press("q")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "SummaryScreen"
        strip = app.screen.query_one("#summary-counters")
        assert strip.size.height > 0, "the counters strip collapsed to zero rows"
        for wid in ("#s-found", "#s-fixed", "#s-skip", "#s-left"):
            assert app.screen.query_one(wid).size.height > 0, wid


async def test_summary_and_results_agree_on_the_axis(tmp_path):
    """Both screens must lead on the impact split, not two different counts."""
    (tmp_path / "index.html").write_text(
        "<p>Our seamless, cutting-edge, world-class platform.</p>\n"
        '<a href="#">Get started</a>\n',
        encoding="utf-8",
    )
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _begin_scan(pilot)
        hint = app.screen._brief_hint().plain
        await pilot.press("q")
        await pilot.pause(0.2)
        summary = app.screen._impact_line().plain
        problems = sum(1 for f in app.screen._findings if f.impact.is_application)
        assert f"{problems} application problem(s)" in hint
        assert f"{problems} application problem(s)" in summary
