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


def test_category_severity_fallback():
    # BUZZWORD INFO -> 0.55 * 0.55
    v = score_finding(_f("buzzword.seamless", Category.BUZZWORD, Severity.INFO))
    assert abs(v - 0.3025) < 1e-9


def test_file_score_noisy_or():
    assert file_score([]) == 0.0
    fs = [_f("x", Category.BUZZWORD, Severity.INFO, 0.303) for _ in range(3)]
    assert abs(file_score(fs) - 0.661) < 0.01


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
