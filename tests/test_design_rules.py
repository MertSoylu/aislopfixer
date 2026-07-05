"""Tests for the AI-slop visual-design rules (engine/rules/design_slop.py)."""

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "index.html") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings):
    return [f.rule_id for f in findings]


# ------------------------------------------------------------ gradient cliché
def test_tailwind_purple_pink_gradient_flagged():
    f = run_file_rules(
        sf('<div class="bg-gradient-to-r from-purple-500 to-pink-500"></div>\n')
    )
    assert "design.gradient_cliche" in ids(f)


def test_tailwind_gradient_in_jsx_flagged():
    f = run_file_rules(
        sf(
            'export const Hero = () => (\n  <div className="bg-gradient-to-br '
            'from-indigo-500 via-purple-500 to-pink-500">hi</div>\n);\n',
            "Hero.tsx",
        )
    )
    assert "design.gradient_cliche" in ids(f)


def test_slate_gradient_not_flagged():
    f = run_file_rules(
        sf('<div class="bg-gradient-to-r from-slate-900 to-slate-700"></div>\n')
    )
    assert "design.gradient_cliche" not in ids(f)


def test_css_purple_pink_gradient_flagged():
    f = run_file_rules(
        sf(".hero { background: linear-gradient(135deg, #8b5cf6, #ec4899); }\n",
           "hero.css")
    )
    assert "design.gradient_cliche" in ids(f)


def test_css_blue_gradient_not_flagged():
    f = run_file_rules(
        sf(".hero { background: linear-gradient(#0ea5e9, #0369a1); }\n", "hero.css")
    )
    assert "design.gradient_cliche" not in ids(f)


# ------------------------------------------------------- fabricated social proof
def test_trusted_by_stat_flagged():
    f = run_file_rules(sf("<p>Trusted by 10,000+ developers worldwide</p>\n"))
    assert "design.fake_social_proof" in ids(f)


def test_join_users_stat_flagged():
    f = run_file_rules(sf("<p>Join 50k+ happy users today</p>\n"))
    assert "design.fake_social_proof" in ids(f)


def test_named_customers_not_flagged():
    f = run_file_rules(sf("<p>Used by teams at Acme and Globex.</p>\n"))
    assert "design.fake_social_proof" not in ids(f)


# ------------------------------------------------------------------ emoji UI
def test_three_decorative_emoji_flagged():
    f = run_file_rules(
        sf(
            "<ul><li>\U0001f680 Fast</li><li>✨ Simple</li>"
            "<li>⚡ Light</li></ul>\n"
        )
    )
    assert ids(f).count("design.emoji_ui") == 3


def test_two_emoji_below_gate_not_flagged():
    f = run_file_rules(
        sf("<ul><li>\U0001f680 Fast</li><li>✨ Simple</li></ul>\n")
    )
    assert "design.emoji_ui" not in ids(f)


def test_emoji_in_plain_js_not_flagged():
    f = run_file_rules(
        sf(
            'const reactions = ["\U0001f680", "✨", "⚡"];\n'
            "export default reactions;\n",
            "reactions.js",
        )
    )
    assert "design.emoji_ui" not in ids(f)
