"""Per-finding confidence and aggregate slop scores.

Every finding carries a ``confidence`` in ``[0, 1]``: how sure we are it is real
AI slop rather than a borderline signal. The runner backfills it centrally
(see :func:`score_finding`) so individual rules stay free of scoring concerns —
a rule may still pin its own confidence and the runner leaves that value alone.

Confidence is derived from three layers, most specific first:

1. a ``rule_id``-prefix override table (longest matching prefix wins), for rules
   whose strength is not captured by category + severity alone;
2. otherwise the product of a per-category prior and a per-severity weight.

File and project scores aggregate those confidences:

* :func:`file_score` — noisy-OR, so one strong finding dominates and many weak
  ones still accumulate without ever exceeding 1.0;
* :func:`project_score` — a self-weighted mean of file scores, so a single very
  sloppy file is not diluted by a sea of clean ones.
"""

from __future__ import annotations

from .models import Category, Finding, Severity

SEV_W: dict[Severity, float] = {
    Severity.INFO: 0.55,
    Severity.WARNING: 0.78,
    Severity.ERROR: 0.95,
}

CAT_PRIOR: dict[Category, float] = {
    Category.AI_LEAK: 1.0,
    Category.CODE_SLOP: 0.92,
    Category.PLACEHOLDER: 0.80,
    Category.BUZZWORD: 0.55,
    Category.ACCESSIBILITY: 0.45,
    Category.DUPLICATE: 0.40,
}

# rule_id prefix -> fixed confidence. Longest matching prefix wins.
RULE_OVERRIDE: dict[str, float] = {
    "ai_leak.strong": 0.97,
    "ai_leak.soft": 0.50,
    "buzzword.density": 0.85,
    "codegen.elision": 0.95,
    "codegen.stub_body": 0.85,
    "codegen.stub_comment": 0.80,
    "codegen.debugger": 0.88,
    "codegen.debug_log": 0.60,
    "codegen.restate_comment": 0.30,
    "prose.emdash_density": 0.45,
    "md.bold_lead_list": 0.55,
    "md.boilerplate_section": 0.70,
    "md.emoji_header": 0.78,
    # Count-gated (>=3 per file) decorative-emoji strip, same AUTO family as
    # emoji_header. Without this it scored CODE_SLOP x INFO = 0.51, below the
    # 0.60 bulk-auto-fix floor, so "fix all auto" silently skipped it.
    "md.checkmark_bullets": 0.80,
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def score_finding(f: Finding) -> float:
    """Confidence for one finding from the override table or category×severity."""
    best_len = -1
    best_val = None
    for prefix, val in RULE_OVERRIDE.items():
        if f.rule_id.startswith(prefix) and len(prefix) > best_len:
            best_len, best_val = len(prefix), val
    if best_val is not None:
        return best_val
    prior = CAT_PRIOR.get(f.category, 0.5)
    weight = SEV_W.get(f.severity, 0.55)
    return _clamp01(prior * weight)


def file_score(findings: list[Finding]) -> float:
    """Noisy-OR of a file's finding confidences: ``1 - Π(1 - c)``."""
    prod = 1.0
    for f in findings:
        prod *= 1.0 - _clamp01(f.confidence)
    return _clamp01(1.0 - prod)


def project_score(file_scores: list[float]) -> float:
    """Self-weighted mean ``Σ s² / Σ s`` — sloppy files dominate, clean dilute less."""
    num = sum(s * s for s in file_scores)
    den = sum(file_scores)
    return _clamp01(num / den) if den > 0 else 0.0


def project_score_from_findings(findings: list[Finding]) -> float:
    """Project score computed straight from a flat finding list."""
    by_file: dict[str, list[Finding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)
    return project_score([file_score(v) for v in by_file.values()])
