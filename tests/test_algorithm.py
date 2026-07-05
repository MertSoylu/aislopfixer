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


# ----------------------------------------------------- #6 comments mined as prose
def test_ai_leak_in_code_comment_flagged():
    text = "// As an AI language model, I should note this.\nexport const x = 1;\n"
    assert any(r.startswith("ai_leak.strong") for r in ids(run_file_rules(sf(text))))


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
