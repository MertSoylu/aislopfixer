"""Turn open findings into a fix prompt for the user's AI coding assistant.

aislopfixer *detects* deterministically, but many findings (security sinks,
hallucinated imports, buzzword prose) need judgement to fix — exactly what a
coding agent is good at once it is told precisely what is wrong and where.
:func:`render_fix_prompt` produces a self-contained markdown brief the user can
paste into Claude Code, Cursor, Copilot or any other assistant: exact
locations, the offending source, per-finding fix guidance, and guardrails so
the agent fixes only what was found — without introducing new slop.

Exposed as ``--prompt`` in headless mode (composable with ``--fix``: auto-fix
the safe findings first, brief the agent on the rest) and as ``x`` on the TUI
results screen (written to ``.aislopfixer/fix-prompt.md`` and copied to the
clipboard).
"""

from __future__ import annotations

from collections import defaultdict

from .engine.models import Category, Finding, Fixability, Status

# Keep the source excerpt per finding short — the brief must stay pasteable.
_SNIPPET_LINES = 8

_FIX_MODE = {
    Fixability.AUTO: "safe to delete/replace outright",
    Fixability.PROMPT: "needs a real value from the project owner",
    Fixability.MANUAL: "judgement call — rewrite by hand",
}

# One line of category-level strategy, shown once above that category's findings.
_CATEGORY_ADVICE = {
    Category.SECURITY: (
        "Close the vulnerability without changing observable behavior: "
        "parameterized queries, textContent/sanitizers, explicit origins, "
        "real crypto APIs. If a fix needs a secret, load it from the "
        "environment — never hardcode one."
    ),
    Category.AI_LEAK: "Delete the chat residue; keep the real content around it intact.",
    Category.PLACEHOLDER: (
        "Replace with real values only if they exist somewhere in the repo; "
        "otherwise insert a clearly named TODO and flag it in your summary. "
        "Never invent plausible-looking emails, URLs or keys."
    ),
    Category.BUZZWORD: (
        "Rewrite in plain, specific language: say what the product actually "
        "does, for whom, with concrete facts instead of superlatives."
    ),
    Category.DUPLICATE: (
        "Extract duplicated code into one shared module and import it; "
        "rewrite duplicated prose so each page says something specific."
    ),
    Category.ACCESSIBILITY: (
        "Write alt text that describes the image's content and purpose in "
        "context; use alt=\"\" only for purely decorative images."
    ),
    Category.CODE_SLOP: (
        "Restore omitted code, implement stubs for real, and make error "
        "handling honest: report or rethrow — an empty catch is not handling."
    ),
    Category.DESIGN: (
        "Restyle with the project's actual brand palette and voice; delete "
        "invented statistics rather than replacing them with new ones."
    ),
}

_GROUND_RULES = """\
1. Fix ONLY the findings listed below. No drive-by refactors, renames or \
formatting changes.
2. Keep every edit minimal and behavior-preserving — except where the flagged \
behavior *is* the defect (swallowed errors, security sinks, broken pastes).
3. Where a fix needs a real-world value (URL, email, brand color) that exists \
nowhere in the repo, insert a clearly named `TODO` and list it in your \
summary — do not invent plausible-looking values.
4. Do not introduce new AI slop: no marketing buzzwords, no decorative emoji, \
no stock purple→pink gradients, no invented statistics, no narration comments.
5. If a finding looks like a false positive, leave the code alone and say why \
in your summary instead of "fixing" it.
6. When you are done, verify with `aislopfixer {target} --check` — it must \
report fewer findings and no new ones."""


def render_fix_prompt(findings: list[Finding], target: str = ".") -> str:
    """A markdown fix brief covering every OPEN finding, or a clean notice."""
    open_ = sorted(
        (f for f in findings if f.status is Status.OPEN),
        key=lambda f: (f.category.value, f.file, f.line, f.col),
    )
    if not open_:
        return "No open findings — nothing to fix.\n"

    n_files = len({f.file for f in open_})
    lines: list[str] = []
    lines.append("# Fix brief — aislopfixer findings")
    lines.append("")
    lines.append(
        f"aislopfixer (an offline, deterministic detector of AI-generated "
        f"slop) found **{len(open_)} issue(s) in {n_files} file(s)** of this "
        f"project. Your job is to fix them. Each finding below gives the "
        f"exact location, the offending source and how to fix it."
    )
    lines.append("")
    lines.append("## Ground rules")
    lines.append("")
    lines.append(_GROUND_RULES.format(target=target))
    lines.append("")
    lines.append("## Findings")

    by_cat: dict[Category, dict[str, list[Finding]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for f in open_:
        by_cat[f.category][f.file].append(f)

    counter = 0
    for cat in Category:
        files = by_cat.get(cat)
        if not files:
            continue
        total = sum(len(v) for v in files.values())
        lines.append("")
        lines.append(f"### {cat.value} ({total})")
        lines.append("")
        advice = _CATEGORY_ADVICE.get(cat)
        if advice:
            lines.append(f"> Strategy: {advice}")
        for path, items in files.items():
            for f in items:
                counter += 1
                lines.append("")
                lines.extend(_entry(counter, f))
    lines.append("")
    return "\n".join(lines)


def _entry(n: int, f: Finding) -> list[str]:
    out: list[str] = []
    out.append(
        f"#### {n}. `{f.file}:{f.line}:{f.col}` — {f.rule_id} "
        f"({f.severity.value}, {round(f.confidence * 100)}% confidence)"
    )
    out.append("")
    out.append(f.message)
    out.append("")
    out.append("```")
    out.extend(_numbered_snippet(f))
    out.append("```")
    match = _one_line(f.matched_text)
    if match and match != _one_line(f.snippet):
        out.append(f"- match: `{match}`")
    out.append(f"- fix mode: {_FIX_MODE[f.fixability]}")
    if f.suggested_fix:
        out.append(f"- how to fix: {f.suggested_fix}")
    if f.fixability is Fixability.PROMPT and f.replace_template:
        out.append(
            f"- replace the match with `{f.replace_template}` "
            f"({f.prompt_label or 'value'} = the real value)"
        )
    return out


def _numbered_snippet(f: Finding) -> list[str]:
    src = (f.snippet or f.matched_text or "").splitlines() or ["—"]
    out = [
        f"{f.line + i:>5} | {line}"
        for i, line in enumerate(src[:_SNIPPET_LINES])
    ]
    if len(src) > _SNIPPET_LINES:
        out.append("      | …")
    return out


def _one_line(s: str, n: int = 120) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"
