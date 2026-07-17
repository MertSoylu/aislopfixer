"""Tests for the confidence + slop-score layer."""

from aislopfixer.engine.models import Category, Finding, Fixability, Severity, SourceFile
from aislopfixer.engine.runner import run_file_rules
from aislopfixer.engine.scoring import (
    file_score,
    project_score,
    project_score_from_findings,
    score_finding,
)


def _f(rule_id: str, category: Category, severity: Severity, confidence: float = 0.0) -> Finding:
    return Finding(
        rule_id=rule_id, category=category, severity=severity, message="",
        file="a", abs_path="a", line=1, col=1, start=0, end=0, snippet="",
        matched_text="", fixability=Fixability.MANUAL, confidence=confidence,
    )


def test_override_longest_prefix_wins():
    assert score_finding(_f("ai_leak.strong.3", Category.AI_LEAK, Severity.ERROR)) == 0.97
    assert score_finding(_f("ai_leak.soft.1", Category.AI_LEAK, Severity.WARNING)) == 0.50


def test_checkmark_bullets_override_clears_auto_fix_floor():
    # md.checkmark_bullets is AUTO-fixable; without an override it falls to
    # CODE_SLOP x INFO = 0.506, below the 0.60 bulk-auto-fix floor.
    assert score_finding(
        _f("md.checkmark_bullets", Category.CODE_SLOP, Severity.INFO)
    ) >= 0.60


def test_design_landing_kit_override():
    assert score_finding(
        _f("design.landing_kit", Category.DESIGN, Severity.WARNING)
    ) == 0.82


def test_category_severity_fallback():
    # BUZZWORD INFO -> 0.55 * 0.55
    v = score_finding(_f("buzzword.seamless", Category.BUZZWORD, Severity.INFO))
    assert abs(v - 0.3025) < 1e-9


def test_file_score_noisy_or_within_an_impact_class():
    assert file_score([]) == 0.0
    # Three POLISH findings noisy-OR to 0.661, then take the POLISH ceiling.
    fs = [_f("x", Category.BUZZWORD, Severity.INFO, 0.303) for _ in range(3)]
    assert abs(file_score(fs) - 0.661 * 0.40) < 0.01


def test_polish_alone_cannot_max_out_the_score():
    """A page whose only sin is adjectives must never read like a broken one.

    Under a flat noisy-OR the weak buzzwords stacked up: 13 of them scored
    100/100 — the same as a file shipping three injection vulns.
    """
    buzz = [_f("buzzword.seamless", Category.BUZZWORD, Severity.INFO, 0.30)] * 13
    assert file_score(buzz) <= 0.40
    vulns = [
        _f("security.sqli", Category.SECURITY, Severity.ERROR, 0.90),
        _f("security.xss_v_html", Category.SECURITY, Severity.ERROR, 0.90),
        _f("security.command_injection", Category.SECURITY, Severity.ERROR, 0.92),
    ]
    assert file_score(vulns) > file_score(buzz) + 0.3


def test_file_score_still_accumulates_and_stays_monotone():
    one = [_f("buzzword.seamless", Category.BUZZWORD, Severity.INFO, 0.30)]
    assert file_score(one * 5) > file_score(one)          # volume still counts
    vulns = [_f("security.sqli", Category.SECURITY, Severity.ERROR, 0.90)]
    # A hazard *plus* a polish tail outranks the hazard alone.
    assert file_score(vulns + one * 5) > file_score(vulns)
    broken = [_f("codegen.elision", Category.CODE_SLOP, Severity.ERROR, 0.96)]
    assert file_score(broken) > file_score(vulns)


def test_project_score_self_weighted():
    assert project_score([]) == 0.0
    # one bad file is not diluted to a plain mean (~0.234)
    assert abs(project_score([0.97, 0.05, 0.05, 0.05, 0.05]) - 0.813) < 0.01


def test_runner_backfills_confidence():
    sf = SourceFile(abs_path="a.html", rel_path="a.html",
                    text="As an AI language model, I cannot help.\n")
    fs = run_file_rules(sf)
    assert fs and all(f.confidence > 0 for f in fs)
    assert any(abs(f.confidence - 0.97) < 1e-9 for f in fs)


def test_project_score_from_findings_groups_by_file():
    a = _f("ai_leak.strong.0", Category.AI_LEAK, Severity.ERROR, 0.97)
    a.file = "a.html"
    b = _f("buzzword.x", Category.BUZZWORD, Severity.INFO, 0.30)
    b.file = "b.html"
    assert project_score_from_findings([a, b]) > 0.0


def test_pinned_confidence_survives_reset_and_corroborate():
    from aislopfixer.engine.scoring import reset_and_corroborate

    pinned = _f("design.custom_rule", Category.DESIGN, Severity.WARNING, 0.33)
    pinned.pinned = True
    other = _f("ai_leak.strong.0", Category.AI_LEAK, Severity.ERROR)
    reset_and_corroborate([pinned, other])
    assert pinned.confidence == 0.33   # not reset, not corroboration-boosted
    assert other.confidence > 0.97     # two tell families -> boosted past base


def test_build_finding_confidence_param_pins():
    from aislopfixer.engine.util import build_finding

    src = SourceFile(abs_path="a.html", rel_path="a.html", text="hello world\n")
    f = build_finding(
        src, rule_id="x.y", category=Category.DESIGN,
        severity=Severity.INFO, message="m", start=0, end=5, confidence=0.5,
    )
    assert f.confidence == 0.5 and f.pinned


def test_checkmark_and_emoji_count_as_one_family():
    from aislopfixer.engine.scoring import corroborate

    # Both are Markdown emoji decoration — one habit must not corroborate itself.
    a = _f("md.emoji_header", Category.CODE_SLOP, Severity.INFO, 0.5)
    b = _f("md.checkmark_bullets", Category.CODE_SLOP, Severity.INFO, 0.5)
    corroborate([a, b])
    assert a.confidence == 0.5 and b.confidence == 0.5

    # But checkmark bullets DO corroborate against a genuinely distinct family.
    c = _f("md.checkmark_bullets", Category.CODE_SLOP, Severity.INFO, 0.5)
    d = _f("ai_leak.strong.0", Category.AI_LEAK, Severity.ERROR, 0.9)
    corroborate([c, d])
    assert c.confidence > 0.5


# ------------------------------------------------------------------- impact
def test_impact_splits_application_problems_from_simple_warnings():
    from aislopfixer.engine.models import Impact
    from aislopfixer.engine.scoring import impact_of

    # Broken: the file cannot do its job as written.
    for rule in ("merge.conflict_marker", "codegen.elision", "import.undeclared",
                 "import.missing_export", "codegen.markdown_fence"):
        assert impact_of(rule) is Impact.BROKEN, rule
    # Risky: it runs, but ships a hazard.
    for rule in ("security.sqli_template", "secret.fake_key", "ai_leak.strong.0",
                 "codegen.empty_catch", "placeholder.dead_href", "a11y.img_no_alt",
                 "design.fake_metrics"):
        assert impact_of(rule) is Impact.RISKY, rule
    # Polish: real slop, but a matter of voice and taste.
    for rule in ("buzzword.seamless", "copy.microcopy.cancel_anytime",
                 "design.gradient_cliche", "design.landing_kit", "prose.dive_in",
                 "import.unused", "placeholder.todo", "ai_leak.soft.2"):
        assert impact_of(rule) is Impact.POLISH, rule


def test_impact_defaults_to_polish_for_unknown_rules():
    from aislopfixer.engine.models import Impact
    from aislopfixer.engine.scoring import impact_of

    # A new rule is a simple warning until someone classifies it — the safe
    # default, since POLISH never inflates the "fix this" headline.
    assert impact_of("brand.new_rule") is Impact.POLISH


def test_impact_longest_prefix_wins():
    from aislopfixer.engine.models import Impact
    from aislopfixer.engine.scoring import impact_of

    # "codegen.elision" (BROKEN) must beat no-match-default, and the narrower
    # "ai_leak.strong" must not be shadowed by a shorter family entry.
    assert impact_of("codegen.elision") is Impact.BROKEN
    assert impact_of("codegen.restate_comment") is Impact.POLISH
    assert impact_of("ai_leak.strong.9") is Impact.RISKY
    assert impact_of("ai_leak.soft.9") is Impact.POLISH


def test_impact_is_derived_not_stored():
    from aislopfixer.engine.models import Impact

    # Impact is a property of the rule, so a hand-built Finding is classified
    # correctly without any backfill step having run.
    f = _f("security.eval", Category.SECURITY, Severity.ERROR)
    assert f.impact is Impact.RISKY and f.impact.is_application
    assert not _f("buzzword.leverage", Category.BUZZWORD, Severity.INFO).impact.is_application


def test_every_registered_rule_has_a_deliberate_impact():
    """Guard the table against drift: every BROKEN/RISKY id must still exist.

    A rule renamed out from under IMPACT_OVERRIDE would silently demote real
    defects to POLISH — where the brief only summarizes them.
    """
    import re
    from pathlib import Path

    from aislopfixer.engine.scoring import IMPACT_OVERRIDE

    src = Path(__file__).parent.parent / "src" / "aislopfixer" / "engine" / "rules"
    text = "\n".join(p.read_text(encoding="utf-8") for p in src.glob("*.py"))
    # Unterminated on purpose: several rules build ids with an f-string
    # (f"ai_leak.strong.{i}"), so capture the literal head up to the brace.
    known = set(re.findall(r'["\']([a-z_0-9]+\.[a-z_0-9.]+)', text))
    # Only this direction: every table key must still prefix a live rule id.
    # The reverse (prefix.startswith(r)) would let `import.undeclared_RENAMED`
    # pass against the old `import.undeclared` — exactly the drift we guard.
    for prefix in IMPACT_OVERRIDE:
        assert any(r.startswith(prefix) for r in known), (
            f"IMPACT_OVERRIDE key {prefix!r} matches no rule_id in engine/rules/"
        )
