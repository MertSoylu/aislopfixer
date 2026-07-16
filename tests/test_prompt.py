"""AI fix-brief generation: prompter.py, --prompt flag, TUI export."""

from aislopfixer.cli import main
from aislopfixer.engine.models import (
    Category,
    Finding,
    Fixability,
    Severity,
    Status,
)
from aislopfixer.prompter import render_fix_prompt


def _finding(**kw) -> Finding:
    base = dict(
        rule_id="security.sql_interpolation",
        category=Category.SECURITY,
        severity=Severity.ERROR,
        message="SQL built by string interpolation",
        file="src/db.js",
        abs_path="/x/src/db.js",
        line=12,
        col=5,
        start=100,
        end=140,
        snippet="const q = `SELECT * FROM users WHERE id = ${id}`;",
        matched_text="`SELECT * FROM users WHERE id = ${id}`",
        fixability=Fixability.MANUAL,
        suggested_fix="Use parameterized queries / prepared statements",
        confidence=0.9,
    )
    base.update(kw)
    return Finding(**base)


# ------------------------------------------------------------------- unit
def test_prompt_contains_location_source_and_guidance():
    out = render_fix_prompt([_finding()], target="./site")
    assert "# Fix brief" in out
    assert "## Ground rules" in out
    assert "`src/db.js:12:5` — security.sql_interpolation" in out
    assert "   12 | const q = `SELECT * FROM users WHERE id = ${id}`;" in out
    assert "Use parameterized queries" in out
    assert "aislopfixer \"./site\" --check" in out


def test_prompt_skips_non_open_findings():
    fixed = _finding(status=Status.FIXED)
    out = render_fix_prompt([fixed])
    assert out == "No open findings — nothing to fix.\n"


def test_prompt_groups_by_category_with_strategy():
    f1 = _finding()
    f2 = _finding(
        rule_id="ai_leak.strong",
        category=Category.AI_LEAK,
        message="AI chat residue",
        file="index.html",
        line=3,
        snippet="As an AI language model, hello.",
        matched_text="As an AI language model",
        fixability=Fixability.AUTO,
    )
    out = render_fix_prompt([f1, f2])
    assert "### Security (1)" in out
    assert "### AI Leak (1)" in out
    assert "> Strategy:" in out
    assert "2 issue(s) in 2 file(s)" in out


def test_prompt_shows_replace_template_for_prompt_fixes():
    f = _finding(
        rule_id="placeholder.dead_link",
        category=Category.PLACEHOLDER,
        fixability=Fixability.PROMPT,
        replace_template='href="{value}"',
        prompt_label="Real URL",
    )
    out = render_fix_prompt([f])
    assert 'href="{value}"' in out
    assert "Real URL" in out


def test_prompt_clips_long_snippets():
    f = _finding(snippet="\n".join(f"line{i}" for i in range(20)))
    out = render_fix_prompt([f])
    assert "line7" in out
    assert "line8" not in out
    assert "| …" in out


def test_prompt_fence_survives_backticks_in_snippet():
    # A markdown_fence finding carries ``` in its snippet — a fixed three-
    # backtick fence would end early and break the brief's rendering.
    f = _finding(
        rule_id="codegen.markdown_fence",
        file="README.mdx",
        snippet="```python\nprint('hi')\n```",
        matched_text="```python",
    )
    out = render_fix_prompt([f])
    lines = out.splitlines()
    fences = [ln for ln in lines if ln and set(ln) == {"`"}]
    assert fences and all(len(ln) >= 4 for ln in fences)


# --------------------------------------------------------------- headless
def _slop_project(tmp_path):
    (tmp_path / "index.html").write_text(
        "<p>As an AI language model, I cannot browse the internet.</p>\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "try { run(); } catch (e) {}\n", encoding="utf-8"
    )
    return tmp_path


def test_prompt_flag_emits_brief_and_exit_code(tmp_path, capsys):
    code = main([str(_slop_project(tmp_path)), "--prompt"])
    out = capsys.readouterr().out
    assert code == 1
    assert "# Fix brief" in out
    assert "ai_leak.strong" in out
    assert "app.js" in out


def test_prompt_flag_clean_project(tmp_path, capsys):
    (tmp_path / "page.html").write_text(
        "<p>We open at 8am on weekdays.</p>\n", encoding="utf-8"
    )
    code = main([str(tmp_path), "--prompt"])
    assert code == 0
    assert "No open findings" in capsys.readouterr().out


def test_fix_plus_prompt_briefs_only_the_rest(tmp_path, capsys):
    p = _slop_project(tmp_path)
    main([str(p), "--fix", "--prompt"])
    out = capsys.readouterr().out
    # the AI leak was auto-fixed; the swallowed catch needs the agent
    assert "ai_leak.strong" not in out
    assert "catch" in out


# --------------------------------------------------------------------- TUI
async def _to_results(app, pilot):
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause(0.1)
    await pilot.press("enter")
    await pilot.pause(2.0)
    assert app.screen.__class__.__name__ == "ResultsScreen"


async def test_results_screen_exports_fix_brief(tmp_path):
    from aislopfixer.app import AISlopFixerApp

    _slop_project(tmp_path)
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _to_results(app, pilot)
        await pilot.press("x")          # opens the export picker
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "ExportModal"
        await pilot.press("b")          # fix brief
        await pilot.pause(0.2)
    brief = tmp_path / ".aislopfixer" / "fix-prompt.md"
    assert brief.exists()
    text = brief.read_text(encoding="utf-8")
    assert "# Fix brief" in text
    assert "ai_leak.strong" in text


async def test_results_screen_exports_all_formats(tmp_path):
    import json as jsonlib

    from aislopfixer.app import AISlopFixerApp

    _slop_project(tmp_path)
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _to_results(app, pilot)
        await pilot.press("x")
        await pilot.pause(0.2)
        await pilot.press("a")          # all three formats
        await pilot.pause(0.2)
    out = tmp_path / ".aislopfixer"
    assert (out / "fix-prompt.md").exists()
    data = jsonlib.loads((out / "findings.json").read_text(encoding="utf-8"))
    assert data["tool"] == "aislopfixer" and data["total"] > 0
    sarif = jsonlib.loads((out / "findings.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"]


async def test_export_modal_escape_writes_nothing(tmp_path):
    from aislopfixer.app import AISlopFixerApp

    _slop_project(tmp_path)
    app = AISlopFixerApp(initial_path=str(tmp_path))
    async with app.run_test() as pilot:
        await _to_results(app, pilot)
        await pilot.press("x")
        await pilot.pause(0.2)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert app.screen.__class__.__name__ == "ResultsScreen"
    assert not (tmp_path / ".aislopfixer" / "fix-prompt.md").exists()


def test_prompt_doc_level_finding_shows_scope_not_line_one():
    # buzzword.density anchors at offset 0 with no span — quoting line 1
    # (`<!DOCTYPE html>`) would point the agent at innocent code.
    f = _finding(
        rule_id="buzzword.density",
        category=Category.BUZZWORD,
        message="High buzzword density",
        line=1, col=1, start=0, end=0,
        snippet="<!DOCTYPE html>", matched_text="",
        suggested_fix="Rewrite the copy",
    )
    out = render_fix_prompt([f])
    assert "scope: the whole file" in out
    assert "<!DOCTYPE html>" not in out
