"""Tests for the v2 smarter detectors: codegen, prose tells, markdown tells."""

from aislopfixer.engine.models import Fixability, SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "a.js") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(text: str, name: str = "a.js") -> set[str]:
    return {f.rule_id for f in run_file_rules(sf(text, name))}


# ------------------------------------------------------------------- codegen
def test_elision_marker_flagged_manual():
    f = [x for x in run_file_rules(sf("// ... existing code ...\n"))
         if x.rule_id == "codegen.elision"]
    assert f and f[0].fixability is Fixability.MANUAL


def test_elision_variants():
    assert "codegen.elision" in ids("    // rest of the component remains unchanged\n")
    assert "codegen.elision" in ids("/* truncated for brevity */\n")
    assert "codegen.elision" in ids("// keep existing code\n")
    assert "codegen.elision" in ids("// same as above\n")


def test_elision_does_not_flag_real_existing_reference():
    # the D-branch tighten: a real cross-reference comment must not fire
    assert "codegen.elision" not in ids("// existing code is in utils.js\n")


def test_elision_does_not_flag_spread_or_rest():
    assert "codegen.elision" not in ids("const arr = [...rest];\n")
    assert "codegen.elision" not in ids("const merged = {...existing, ...other};\n")
    assert "codegen.elision" not in ids("function f(...args) {}\n")


def test_elision_skipped_inside_template_literal():
    assert "codegen.elision" not in ids("const s = `// ... existing code ...`;\n")


def test_stub_body_detected_but_real_error_is_not():
    assert "codegen.stub_body" in ids("throw new Error('Not implemented');\n")
    assert "codegen.stub_body" in ids("raise NotImplementedError\n")
    assert "codegen.stub_body" not in ids("throw new Error('User not found');\n")


def test_stub_comment_detected():
    assert "codegen.stub_comment" in ids("// your code here\n")
    assert "codegen.stub_comment" in ids("// implement me\n")
    assert "codegen.stub_comment" not in ids("// your account balance is shown here\n")


def test_debugger_is_auto_and_identifier_is_safe():
    f = [x for x in run_file_rules(sf("    debugger;\n")) if x.rule_id == "codegen.debugger"]
    assert f and f[0].fixability is Fixability.AUTO
    assert "codegen.debugger" not in ids("const debugger_enabled = true;\n")


def test_debug_log_whitelist():
    assert "codegen.debug_log" in ids("console.log('here');\n")
    assert "codegen.debug_log" not in ids("console.log('User logged in:', user.id)\n")


def test_restate_comment_defeated_by_explanation():
    assert "codegen.restate_comment" in ids("// Initialize the variable\n")
    assert "codegen.restate_comment" not in ids(
        "// Initialize the variable to the cached value to skip the round-trip\n"
    )


# --------------------------------------------------------------- prose tells
def test_prose_tells_in_html_prose():
    assert "prose.not_only_but_also" in ids("<p>It is not only fast but also reliable.</p>", "i.html")
    assert "prose.in_this_article" in ids("<p>In this article, we explore hooks.</p>", "i.html")
    assert "prose.when_it_comes_to" in ids("<p>When it comes to speed, Rust wins.</p>", "i.html")


def test_prose_tells_skip_code_files():
    # prose_regions == [] for code → identifiers never flagged
    assert "prose.when_it_comes_to" not in ids("const whenItComesTo = 1;\n")


def test_dive_in_requires_cta():
    assert "prose.dive_in" in ids("<p>Let's dive in!</p>", "i.html")
    assert "prose.dive_in" not in ids("<p>You can dive into the source.</p>", "i.html")


def test_emdash_density_threshold():
    assert "prose.emdash_density" in ids(
        "<p>We build apps — fast — clean — and ship — weekly.</p>", "i.html"
    )
    assert "prose.emdash_density" not in ids("<p>We build apps — fast and clean.</p>", "i.html")
    assert "prose.emdash_density" not in ids(
        "<p>A self-service, low-code, state-of-the-art tool.</p>", "i.html"
    )


# ------------------------------------------------------------ markdown tells
def test_markdown_tells_md_only():
    md = "## 🚀 Features\n"
    assert "md.emoji_header" in ids(md, "doc.md")
    assert "md.emoji_header" not in ids(md, "a.js")  # never on code


def test_emoji_header_skipped_in_fence():
    assert "md.emoji_header" not in ids("```\n## 🚀 Features\n```\n", "doc.md")


def test_boilerplate_section_end_anchored():
    assert "md.boilerplate_section" in ids("## Conclusion\n", "doc.md")
    assert "md.boilerplate_section" not in ids("## Conclusion of the war\n", "doc.md")


def test_checkmark_bullets_count_gate_and_tasklist_safe():
    assert "md.checkmark_bullets" in ids("- ✅ Fast\n- ✔️ Secure\n- ✨ Easy\n", "doc.md")
    assert "md.checkmark_bullets" not in ids("- [ ] todo\n- [x] done\n- [ ] more\n", "doc.md")


def test_bold_lead_list_run_gate():
    good = (
        "- **Lightning Fast**: built on Rust\n"
        "- **Secure by Default:** TLS 1.3\n"
        "- **Easy to Use**: intuitive API\n"
        "- **Scalable**: millions\n"
        "- **Open Source**: MIT\n"
    )
    assert "md.bold_lead_list" in ids(good, "doc.md")
    lone = (
        "- The build uses esbuild\n- Run make test\n"
        "- **Important**: back up DB\n- See the docs\n"
    )
    assert "md.bold_lead_list" not in ids(lone, "doc.md")


def test_scaffolding_leadin():
    assert "md.scaffolding_leadin" in ids("Here is a breakdown of the steps:\n", "doc.md")
    assert "md.scaffolding_leadin" not in ids("Here is the config file.\n", "doc.md")
