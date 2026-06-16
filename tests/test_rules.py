from aislopfixer.engine.models import Category, Fixability, SourceFile
from aislopfixer.engine.runner import run_cross_rules, run_file_rules


def sf(text: str, name: str = "index.html") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def test_ai_leak_detected_and_auto():
    f = [x for x in run_file_rules(sf("As an AI language model, I cannot help.\n"))
         if x.category is Category.AI_LEAK]
    assert f
    assert f[0].fixability is Fixability.AUTO


def test_ai_leak_deduped_to_one_per_line():
    # the line matches several phrases; dedupe collapses identical spans
    f = [x for x in run_file_rules(sf("As an AI language model, I cannot help.\n"))
         if x.category is Category.AI_LEAK]
    assert len(f) == 1


def test_placeholder_email_is_prompt():
    f = run_file_rules(sf("Contact john@example.com today\n"))
    e = [x for x in f if x.rule_id == "placeholder.email"]
    assert e and e[0].fixability is Fixability.PROMPT


def test_lorem_ipsum_auto():
    f = run_file_rules(sf("<p>Lorem ipsum dolor sit amet.</p>\n"))
    e = [x for x in f if x.rule_id == "placeholder.lorem"]
    assert e and e[0].fixability is Fixability.AUTO


def test_dead_href_detected():
    f = run_file_rules(sf('<a href="#">x</a>\n'))
    assert any(x.rule_id == "placeholder.dead_href" for x in f)


def test_valid_anchor_not_flagged():
    f = run_file_rules(sf('<a href="#section">x</a>\n'))
    assert not any(x.rule_id == "placeholder.dead_href" for x in f)


def test_buzzword_density_summary():
    text = ("cutting-edge seamless world-class synergy revolutionize "
            "elevate your supercharge best-in-class")
    f = run_file_rules(sf(text))
    assert any(x.rule_id == "buzzword.density" for x in f)


def test_accessibility_img_no_alt():
    f = run_file_rules(sf('<img src="a.png">'))
    assert any(x.rule_id == "a11y.img_no_alt" for x in f)


def test_accessibility_generic_alt_prompt():
    f = run_file_rules(sf('<img src="a.png" alt="image">'))
    g = [x for x in f if x.rule_id == "a11y.img_generic_alt"]
    assert g and g[0].fixability is Fixability.PROMPT


def test_clean_content_no_ai_leak():
    f = run_file_rules(sf("<p>Our bakery opens at 8am on Main Street.</p>\n"))
    assert not any(x.category is Category.AI_LEAK for x in f)


def test_duplicate_cross_file():
    block = ("This is a sufficiently long paragraph of real content that should "
             "be flagged as duplicate when it appears in two separate files.")
    cross = run_cross_rules([sf(block, "a.html"), sf(block, "b.html")])
    dup = [x for x in cross if x.rule_id == "duplicate.block"]
    assert len(dup) >= 2


def test_duplicate_is_info_severity():
    block = ("This is a sufficiently long paragraph of real content that should "
             "be flagged as duplicate when it appears in two separate files.")
    cross = run_cross_rules([sf(block, "a.html"), sf(block, "b.html")])
    dup = [x for x in cross if x.rule_id == "duplicate.block"]
    assert dup and all(x.severity.name == "INFO" for x in dup)


def test_duplicate_within_single_file_not_flagged():
    # The same block twice in ONE file is usually a legitimate template, not the
    # cross-page copy-paste slop we target. Only cross-file repeats are reported.
    block = ("This is a sufficiently long paragraph of real content that should "
             "be flagged as duplicate when it appears in two separate files.")
    cross = run_cross_rules([sf(block + "\n\n" + block, "a.html")])
    assert not [x for x in cross if x.rule_id == "duplicate.block"]


def test_duplicate_imports_not_flagged():
    # The same imports in different files are normal, not slop (the reported bug).
    code = (
        "import React from 'react';\n"
        "import { useState, useEffect, useCallback } from 'react';\n"
        "import { Button } from './ui/button';\n"
        "import { Card, CardHeader } from './ui/card';\n"
    )
    cross = run_cross_rules([sf(code, "a.tsx"), sf(code, "b.tsx")])
    assert not [x for x in cross if x.rule_id == "duplicate.block"]


def test_duplicate_code_block_not_flagged():
    block = (
        "export function handler(req, res) {\n"
        "  const value = compute(req.body);\n"
        "  return res.json({ ok: true, value });\n"
        "}"
    )
    cross = run_cross_rules([sf(block, "a.js"), sf(block, "b.js")])
    assert not [x for x in cross if x.rule_id == "duplicate.block"]


def test_img_no_alt_is_prompt_fixable():
    f = run_file_rules(sf('<img src="a.png">\n'))
    g = [x for x in f if x.rule_id == "a11y.img_no_alt"]
    assert g and g[0].fixability is Fixability.PROMPT


def test_html_missing_lang_flagged():
    f = run_file_rules(sf("<html>\n<head><title>Hi there</title></head>\n</html>\n"))
    g = [x for x in f if x.rule_id == "a11y.no_lang"]
    assert g and g[0].fixability is Fixability.PROMPT


def test_html_with_lang_not_flagged():
    f = run_file_rules(sf('<html lang="en">\n<head><title>Hi</title></head>\n</html>\n'))
    assert not any(x.rule_id == "a11y.no_lang" for x in f)
