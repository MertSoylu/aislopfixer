"""Tests for marketing-copy slop rules (engine/rules/copy_slop.py)."""

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_file_rules


def sf(text: str, name: str = "index.html") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings):
    return [f.rule_id for f in findings]


def prefixed(findings, prefix: str):
    return [f for f in findings if f.rule_id.startswith(prefix)]


# --------------------------------------------------------- generic microcopy
def test_two_microcopy_phrases_flagged():
    f = run_file_rules(
        sf("<p>No credit card required. Cancel anytime.</p>\n")
    )
    assert len(prefixed(f, "copy.microcopy")) == 2


def test_single_microcopy_phrase_quiet():
    f = run_file_rules(sf("<p>Cancel anytime from your account settings.</p>\n"))
    assert not prefixed(f, "copy.microcopy")


def test_repeated_same_phrase_still_quiet():
    """Twice the same phrase is one habit, not a template kit — needs variety."""
    f = run_file_rules(
        sf("<p>Cancel anytime.</p>\n<footer>Cancel anytime.</footer>\n")
    )
    assert not prefixed(f, "copy.microcopy")


def test_microcopy_in_code_not_flagged():
    f = run_file_rules(
        sf(
            'const label = "No credit card required";\n'
            'const note = "Cancel anytime";\n',
            "labels.js",
        )
    )
    assert not prefixed(f, "copy.microcopy")


def test_hero_promise_pair_flagged():
    f = run_file_rules(
        sf("<h1>Everything you need to ship faster</h1>"
           "<p>Get started in minutes.</p>\n")
    )
    assert len(prefixed(f, "copy.microcopy")) == 2


# ------------------------------------------------------ template testimonial
def test_transformed_testimonial_flagged():
    f = run_file_rules(
        sf(
            "<blockquote>This tool has completely transformed the way we "
            "work.</blockquote>\n"
        )
    )
    assert prefixed(f, "copy.testimonial")


def test_cant_imagine_testimonial_flagged():
    f = run_file_rules(
        sf("<blockquote>I can't imagine working without it now.</blockquote>\n")
    )
    assert prefixed(f, "copy.testimonial")


def test_game_changer_for_us_flagged():
    f = run_file_rules(
        sf("<blockquote>It's been a game-changer for our team.</blockquote>\n")
    )
    assert prefixed(f, "copy.testimonial")


def test_plain_specific_quote_not_flagged():
    f = run_file_rules(
        sf(
            "<blockquote>Migrating our invoicing to Billfold cut month-end "
            "close from 4 days to 6 hours.</blockquote>\n"
        )
    )
    assert not prefixed(f, "copy.testimonial")


def test_testimonial_in_docs_prose_md():
    """Markdown marketing pages carry the same fabricated quotes."""
    f = run_file_rules(
        sf(
            "> This platform completely transformed how we onboard clients.\n",
            "landing.md",
        )
    )
    assert prefixed(f, "copy.testimonial")
