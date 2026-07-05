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
    Category.SECURITY: 0.93,
    Category.AI_LEAK: 1.0,
    Category.CODE_SLOP: 0.92,
    Category.PLACEHOLDER: 0.80,
    Category.BUZZWORD: 0.55,
    Category.ACCESSIBILITY: 0.45,
    Category.DUPLICATE: 0.40,
    Category.DESIGN: 0.60,
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
    # Swallowed errors: a strong generated-code habit, but empty catches exist
    # in human code too — keep below the auto-fix floor.
    "codegen.empty_catch": 0.66,
    # Weaker catch shapes: masked failures, but common in human code too.
    "codegen.catch_return_default": 0.62,
    "codegen.log_only_catch": 0.45,
    # Aggregate over-commenting signal — meaningful only in bulk.
    "codegen.comment_density": 0.50,
    # An import that resolves to no declared package breaks the build and may be
    # a hallucinated (typo-squattable) dependency.
    "import.undeclared": 0.85,
    # A named import the target module demonstrably never exports.
    "import.missing_export": 0.82,
    # Leftover unused bindings: real but weak (type-only uses can fool the check).
    "import.unused": 0.55,
    # Token-near-identical logic repeated across files.
    "duplicate.code_block": 0.45,
    # A chat code-fence pasted into a source file is broken source.
    "codegen.markdown_fence": 0.90,
    # Unresolved merge markers are broken source, not a stylistic guess.
    "merge.conflict_marker": 0.98,
    # Placeholder/hardcoded secrets: high-confidence, runtime-breaking.
    "secret.placeholder_token": 0.85,
    "secret.fake_key": 0.88,
    "secret.assignment": 0.80,
    # Security vulnerabilities — the serious, modern AI-slop class. Defaults from
    # CAT_PRIOR(SECURITY)×severity; these deviate where the shape is more/less sure.
    "security.hardcoded_secret": 0.96,
    "security.eval": 0.90,
    "security.sqli": 0.90,
    "security.command_injection": 0.92,
    "security.tls_disabled": 0.92,
    "security.xss_dangerously_set": 0.62,
    "security.xss_v_html": 0.62,
    "security.cors_wildcard": 0.58,
    "security.insecure_random": 0.58,
    "security.token_in_storage": 0.62,
    "security.postmessage_wildcard": 0.60,
    # Entropy heuristic — lower than the provider-prefix match; can misjudge.
    "security.high_entropy_secret": 0.72,
    # Visual design tells: each is a style choice a human *could* make, so none
    # clears the auto-fix floor alone — corroboration lifts them when the file
    # carries other authorship tells.
    "design.gradient_cliche": 0.62,
    "design.fake_social_proof": 0.68,
    "design.emoji_ui": 0.72,
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


# Independent "this file was AI-authored" tells. When several distinct families
# co-occur in one file each finding is likelier real — weak signals corroborate.
# Restricted to authorship tells, so a page of (legitimate) buzzwords alone is
# never inflated; a file mixing, say, an elision marker + a stub + a debug log is.
_TELL_FAMILIES: tuple[str, ...] = (
    "ai_leak", "codegen", "merge.conflict", "secret", "security",
    "md.emoji", "buzzword.density", "import.", "design.",
)
_CORROBORATION_STEP = 0.12  # confidence gained per extra co-occurring family


def _family(rule_id: str) -> str | None:
    for fam in _TELL_FAMILIES:
        if rule_id.startswith(fam):
            return fam
    return None


def corroborate(findings: list[Finding]) -> list[Finding]:
    """Boost confidences when ≥2 distinct AI-tell families co-occur in one file."""
    families = {fam for f in findings if (fam := _family(f.rule_id))}
    extra = len(families) - 1
    if extra <= 0:
        return findings
    factor = min(0.4, _CORROBORATION_STEP * extra)
    for f in findings:
        f.confidence = _clamp01(f.confidence + (1.0 - f.confidence) * factor)
    return findings


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
