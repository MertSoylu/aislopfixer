"""Tests for the algorithmic engine upgrades.

Covers: code-aware masking, comment-as-prose mining, entropy secrets,
co-occurrence confidence boosting, containment dedupe, near-duplicate
clustering, and adaptive per-project suppression.
"""

from aislopfixer.engine.context import code_masks, point_in
from aislopfixer.engine.models import (
    Category,
    Finding,
    Fixability,
    Severity,
    SourceFile,
    Status,
)
from aislopfixer.engine.runner import run_cross_rules, run_file_rules
from aislopfixer.store import Store


def sf(text: str, name: str = "app.js") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings) -> set[str]:
    return {f.rule_id for f in findings}


# --------------------------------------------------------- #1 code-aware masking
def test_code_masks_marks_strings_and_comments():
    text = 'const a = "hello"; // bye\n'
    strings, comments = code_masks(text, ".js")
    assert point_in(strings, text.index("hello"))
    assert point_in(comments, text.index("bye"))
    assert not point_in(strings, text.index("const"))


def test_eval_in_comment_not_flagged():
    assert "security.eval" not in ids(run_file_rules(sf("// never use eval() here\n")))


def test_eval_in_string_not_flagged():
    assert "security.eval" not in ids(run_file_rules(sf('const s = "eval() is bad";\n')))


def test_real_eval_flagged():
    assert "security.eval" in ids(run_file_rules(sf("eval(userInput);\n")))


def test_elision_inside_template_literal_not_flagged():
    # "// ... rest ..." printed inside a template literal is data, not slop.
    text = "const help = `to skip code write // ... rest of the code ...`;\n"
    assert "codegen.elision" not in ids(run_file_rules(sf(text)))


def test_eval_inside_template_interpolation_flagged():
    """${…} holes are code — exclude_strings must not swallow sinks there."""
    text = "const x = `ok ${eval(userInput)}`;\n"
    assert "security.eval" in ids(run_file_rules(sf(text)))
    # Hole itself is not a string span.
    strings, _ = code_masks(text, ".js")
    assert not point_in(strings, text.index("eval"))


def test_eval_in_template_static_chunk_not_flagged():
    text = "const s = `never call eval() on input`;\n"
    assert "security.eval" not in ids(run_file_rules(sf(text)))


def test_nested_template_interpolation_lexed():
    text = "const x = `a ${`b ${eval(y)} c`} d`;\n"
    assert "security.eval" in ids(run_file_rules(sf(text)))
    strings, _ = code_masks(text, ".js")
    assert not point_in(strings, text.index("eval"))


def test_brace_in_string_inside_interpolation_does_not_break_lex():
    text = 'const x = `hi ${foo("}") + eval(z)}`;\n'
    assert "security.eval" in ids(run_file_rules(sf(text)))


# ----------------------------------------------------- #6 comments mined as prose
def test_ai_leak_in_code_comment_flagged():
    text = "// As an AI language model, I should note this.\nexport const x = 1;\n"
    assert any(r.startswith("ai_leak.strong") for r in ids(run_file_rules(sf(text))))


def test_ai_leak_in_vue_script_comment_flagged():
    text = (
        "<template><p>hi</p></template>\n"
        "<script setup>\n"
        "// As an AI language model, I should note this.\n"
        "export const x = 1;\n"
        "</script>\n"
    )
    assert any(
        r.startswith("ai_leak.strong")
        for r in ids(run_file_rules(sf(text, "Widget.vue")))
    )


def test_buzzword_in_svelte_script_comment_flagged():
    text = (
        "<script>\n"
        "// we leverage synergy to deliver value\n"
        "let x = 1;\n"
        "</script>\n"
        "<p>ok</p>\n"
    )
    assert any(
        r.startswith("buzzword")
        for r in ids(run_file_rules(sf(text, "Card.svelte")))
    )


def test_buzzword_in_html_script_comment_flagged():
    text = (
        "<html><body>\n"
        "<script>\n// leverage cutting-edge synergy here\n</script>\n"
        "</body></html>\n"
    )
    assert any(
        r.startswith("buzzword")
        for r in ids(run_file_rules(sf(text, "page.html")))
    )


def test_buzzword_in_code_comment_flagged():
    text = "// we leverage synergy to deliver value\nconst x = 1;\n"
    assert any(r.startswith("buzzword") for r in ids(run_file_rules(sf(text))))


def test_buzzword_as_identifier_not_flagged():
    text = "const leverage = synergy();\n"
    assert not any(r.startswith("buzzword") for r in ids(run_file_rules(sf(text))))


# ------------------------------------------------------------ #5 entropy secrets
def test_high_entropy_secret_flagged():
    text = 'const token = "aZ3kL9qXr2mP7wVt1nB4cE6dF8gH0jK";\n'
    assert "security.high_entropy_secret" in ids(run_file_rules(sf(text)))


def test_env_value_not_entropy_secret():
    text = "const token = process.env.SECRET_TOKEN;\n"
    assert "security.high_entropy_secret" not in ids(run_file_rules(sf(text)))


def test_placeholder_not_entropy_secret():
    text = 'const apiKey = "your-api-key-here-xxxxxxxx";\n'
    assert "security.high_entropy_secret" not in ids(run_file_rules(sf(text)))


# --------------------------------------------------- #2 co-occurrence corroboration
def test_corroboration_boosts_cooccurring_tells():
    multi = sf("// ... rest of the code ...\ndebugger;\neval(userInput);\n")
    solo = sf("debugger;\n")
    boosted = next(f.confidence for f in run_file_rules(multi)
                   if f.rule_id == "codegen.debugger")
    base = next(f.confidence for f in run_file_rules(solo)
                if f.rule_id == "codegen.debugger")
    assert boosted > base


def test_scan_all_corroborates_cross_with_file_tells():
    """Import (cross) + debugger (file) in same path → import confidence lifts."""
    from aislopfixer.engine.runner import scan_all

    # undeclared import is a cross-rule; debugger is a file-rule.
    a = SourceFile(
        "page.ts", "page.ts",
        "import { missingThing } from './ghost';\ndebugger;\n",
    )
    b = SourceFile("ghost.ts", "ghost.ts", "export const other = 1;\n")
    found = scan_all([a, b])
    imp = next(
        (f for f in found if f.rule_id.startswith("import.") and f.file == "page.ts"),
        None,
    )
    assert imp is not None
    # Base import.missing_export/undeclared is 0.82/0.85; with codegen co-tell
    # (debugger family) corroboration must raise it.
    from aislopfixer.engine.scoring import score_finding
    assert imp.confidence > score_finding(imp)


# ------------------------------------------------------------- #8 containment dedupe
def test_nested_same_category_match_dropped():
    found = ids(run_file_rules(sf("<p>let us delve into things now</p>\n", "x.html")))
    assert "buzzword.delve_into" in found
    assert "buzzword.delve" not in found  # contained in "delve into"


# ----------------------------------------------------------- #4 near-duplicate prose
def test_near_duplicate_prose_clustered():
    para = ("Welcome to Acme Corporation, your trusted partner in scalable cloud "
            "services and reliable infrastructure for ambitious modern teams")
    a = SourceFile("a.md", "a.md", para + " worldwide.\n")
    b = SourceFile("b.md", "b.md", para + " everywhere.\n")
    dup = [f for f in run_cross_rules([a, b]) if f.rule_id == "duplicate.block"]
    assert dup
    assert any("Near-duplicate" in f.message for f in dup)


# --------------------------------------------------------- #7 adaptive suppression
def _ignored(value: str) -> Finding:
    return Finding(
        rule_id="buzzword.leverage",
        category=Category.BUZZWORD,
        severity=Severity.INFO,
        message="m",
        file=f"{value}.html",
        abs_path="x",
        line=1,
        col=1,
        start=0,
        end=1,
        snippet="",
        matched_text=value,
        fixability=Fixability.MANUAL,
        status=Status.IGNORED,
    )


def test_store_learns_noisy_rules(tmp_path):
    store = Store(str(tmp_path))
    for v in ("a", "b", "c"):
        store.record(_ignored(v))
    assert store.ignored_count("buzzword.leverage") == 3
    assert "buzzword.leverage" in store.noisy_rules()
    assert "buzzword.leverage" not in store.noisy_rules(threshold=4)


# ------------------------------------------------------------- regex literals
def test_regex_literal_slashes_do_not_open_comment():
    # `//` inside a regex literal is not a line comment — code after it is live.
    text = "const re = /https?:\\/\\//; eval(userInput);\n"
    _, comments = code_masks(text, ".js")
    assert not point_in(comments, text.index("eval"))


def test_regex_literal_quote_does_not_open_string():
    text = "const re = /'/; eval(userInput);\n"
    strings, _ = code_masks(text, ".js")
    assert not point_in(strings, text.index("eval"))


def test_regex_after_return_keyword_recognized():
    # After `return` a `/` starts a regex; its quote must not open a string
    # that swallows the rest of the line.
    text = "function f(s) {\n  return /'/ .test(s) && eval(payload);\n}\n"
    strings, _ = code_masks(text, ".js")
    assert not point_in(strings, text.index("eval"))


def test_division_is_not_a_regex():
    # `total / 2` must not start a regex and swallow the comment/string after it.
    text = "const half = total / 2; // note\nconst s = 'eval(x)';\n"
    strings, comments = code_masks(text, ".js")
    assert point_in(comments, text.index("// note"))
    assert point_in(strings, text.index("'eval"))


def test_regex_char_class_slash_does_not_close():
    # A `/` inside a regex char class does not terminate the literal.
    text = "const re = /[/]+/;\nconst s = 'eval(x)';\n"
    strings, _ = code_masks(text, ".js")
    assert point_in(strings, text.index("'eval"))


# ----------------------------------------------------- doc-level annotations
def test_doc_level_finding_survives_annotation_on_first_line():
    # File-level findings anchor at offset 0; an annotation on line 1 must not
    # silently kill them — they describe the file, not that line.
    text = (
        "<!-- aislopfixer: reviewed -->\n"
        "<p>cutting-edge seamless leverage synergy delve unparalleled</p>\n"
    )
    sf = SourceFile(abs_path="hero.html", rel_path="hero.html", text=text)
    assert "buzzword.density" in [f.rule_id for f in run_file_rules(sf)]


def test_todo_match_stops_before_comment_closers():
    # `{/* TODO: x */}` / `<!-- TODO: x -->`: the match must not swallow the
    # comment closer — a brief consumer deleting the match would break syntax.
    from aislopfixer.engine.models import SourceFile
    from aislopfixer.engine.runner import run_file_rules

    sf = SourceFile(
        abs_path="App.jsx", rel_path="App.jsx",
        text="{/* TODO: wire up real CTA */}\n<!-- FIXME: replace hero -->\n",
    )
    todos = [f for f in run_file_rules(sf) if f.rule_id == "placeholder.todo"]
    assert [f.matched_text for f in todos] == [
        "TODO: wire up real CTA",
        "FIXME: replace hero",
    ]
