"""Turn open findings into a fix prompt for the user's AI coding assistant.

aislopfixer *detects* deterministically, but many findings (security sinks,
hallucinated imports, buzzword prose) need judgement to fix — exactly what a
coding agent is good at once it is told precisely what is wrong and where.
:func:`render_fix_prompt` produces a self-contained markdown brief the user can
paste into Claude Code, Cursor, Copilot or any other assistant: exact
locations, the offending source, per-finding fix guidance, and guardrails so
the agent fixes only what was found — without introducing new slop.

The brief is organised by :class:`~aislopfixer.engine.models.Impact`, not by
category, because that is the split the agent must act on. ``BROKEN`` and
``RISKY`` findings — the *application problems* — get a full entry each: source
excerpt, location, fix guidance. ``POLISH`` findings are the simple-warning
tail (buzzwords, gradients, tidiness); they are real, but listing twenty-five
of them as peers of an SQL injection is how an agent ends up rewriting the word
"seamless" and leaving the sink. They collapse into one rolled-up line per rule
family at the end, so the agent knows what was set aside without drowning in it.

Exposed as ``--prompt`` in headless mode (composable with ``--fix``: auto-fix
the safe findings first, brief the agent on the rest) and as ``x`` on the TUI
results screen (written to ``.aislopfixer/fix-prompt.md`` and copied to the
clipboard).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .engine.models import Category, Finding, Fixability, Impact, Status

# Keep the source excerpt per finding short — the brief must stay pasteable.
_SNIPPET_LINES = 8

# How many distinct examples/files a rolled-up warning line names before "+N more".
_ROLLUP_SAMPLES = 4
_ROLLUP_FILES = 3

_FIX_MODE = {
    Fixability.AUTO: "safe to delete/replace outright",
    Fixability.PROMPT: "needs a real value from the project owner",
    Fixability.MANUAL: "judgement call — rewrite by hand",
}

# The lead for each application-problem section: what this class of finding is
# and the posture to take on it. RISKY's lead is built per run (see
# :func:`_risky_lead`) — its title is the only fixed half.
_IMPACT_LEAD: dict[Impact, tuple[str, str]] = {
    Impact.BROKEN: (
        "Broken — this code does not work as written",
        "Ship blockers. Something is missing, unresolved, or points at a "
        "module that does not exist: the file cannot do its job. Restore the "
        "real code — do not paper over the symptom by deleting the marker.",
    ),
    Impact.RISKY: ("Risky — it runs, but ships a hazard", ""),
}

# What each RISKY rule family actually is, in the terms the agent will act on.
# The lead names the families *present* instead of printing a fixed list: on a
# project whose risky findings are seven placeholders and three missing alt
# attributes — no sinks, no credentials — promising "a sink, a credential … an
# attacker will find" sends the agent hunting a vulnerability that is not there,
# and it spends its trust on the first thing it fails to find.
_RISKY_KINDS: tuple[tuple[str, str], ...] = (
    ("security.", "a security sink"),
    ("secret.", "a hardcoded credential"),
    ("ai_leak.strong", "chat residue in shipped copy"),
    ("codegen.debugger", "a breakpoint shipped to every visitor"),
    ("codegen.empty_catch", "a swallowed failure"),
    ("codegen.catch_return_default", "a swallowed failure"),
    ("codegen.log_only_catch", "a swallowed failure"),
    ("placeholder.dead_href", "a dead link"),
    ("placeholder.void_href", "a dead link"),
    ("placeholder.fake_api", "a request to a domain you do not own"),
    ("placeholder.example_domain", "a request to a domain you do not own"),
    ("placeholder.email", "a contact address that reaches nobody"),
    ("placeholder.phone", "a contact number that reaches nobody"),
    ("placeholder.image", "art served from someone else's host"),
    ("placeholder.lorem", "filler text shipped to users"),
    ("placeholder.bracket", "an unfilled placeholder on the page"),
    ("a11y.img_no_alt", "an image no screen reader can describe"),
    ("design.fake_", "an invented claim"),
)


def _oxford(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _risky_lead(items: list[Finding]) -> str:
    """The RISKY lead, named from the findings this run actually produced."""
    kinds: list[str] = []
    for f in items:
        for prefix, phrase in _RISKY_KINDS:
            if f.rule_id.startswith(prefix):
                if phrase not in kinds:
                    kinds.append(phrase)
                break
    hostile = any(f.rule_id.startswith(("security.", "secret.")) for f in items)
    who = "a user or an attacker" if hostile else "a user"
    what = _oxford(kinds) if kinds else "each of these ships a real hazard"
    return (
        "No syntax error here, which is exactly why these survive review: "
        f"{what}. Each one is a defect {who} will hit in the shipped product."
    )

# One line of category-level strategy, shown once per category inside a section.
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
6. When you are done, verify with `aislopfixer "{target}" --check` — it must \
report fewer findings and no new ones."""

# Rule families whose leaf is a single vocabulary item ("buzzword.seamless",
# "copy.microcopy.cancel_anytime"). One rolled-up line for the family beats one
# line per word — the family, not the word, is the thing to act on.
_ROLLUP_FAMILIES = (
    "buzzword.",
    "copy.microcopy.",
    "copy.testimonial.",
    "prose.",
    "ai_leak.soft",
)


def render_fix_prompt(findings: list[Finding], target: str = ".") -> str:
    """A markdown fix brief covering every OPEN finding, or a clean notice.

    Application problems (BROKEN, RISKY) are written out in full; POLISH
    findings are rolled up into a closing summary section.
    """
    open_ = sorted(
        (f for f in findings if f.status is Status.OPEN),
        key=lambda f: (-f.impact.rank, f.category.value, f.file, f.line, f.col),
    )
    if not open_:
        return "No open findings — nothing to fix.\n"

    problems = [f for f in open_ if f.impact.is_application]
    warnings = [f for f in open_ if not f.impact.is_application]

    lines: list[str] = []
    lines.append("# Fix brief — aislopfixer findings")
    lines.append("")
    lines.extend(_intro(problems, warnings))
    lines.append("")
    lines.append("## Ground rules")
    lines.append("")
    lines.append(_GROUND_RULES.format(target=target))

    counter = 0
    section = 0
    for impact in (Impact.BROKEN, Impact.RISKY):
        items = [f for f in problems if f.impact is impact]
        if not items:
            continue
        section += 1
        counter = _emit_section(lines, section, impact, items, counter)

    if warnings:
        section += 1
        _emit_warnings(lines, section, warnings)
    lines.append("")
    return "\n".join(lines)


def _intro(problems: list[Finding], warnings: list[Finding]) -> list[str]:
    """The mission statement: what was found and which part is the agent's job."""
    n_files = len({f.file for f in problems + warnings})
    out = [
        "aislopfixer (an offline, deterministic detector of AI-generated "
        f"slop) scanned {n_files} file(s) of this project."
    ]
    out.append("")
    if problems and warnings:
        out.append(
            f"It found **{len(problems)} application problem(s)** — code that "
            f"does not work, or that ships a real hazard — and "
            f"**{len(warnings)} simple warning(s)** about voice and aesthetics."
        )
        out.append("")
        out.append(
            "**Your job is the application problems.** They are written out in "
            "full below, each with its exact location, the offending source and "
            "how to fix it. The simple warnings are summarized at the end for "
            "context only — do not spend this pass on them."
        )
    elif problems:
        out.append(
            f"It found **{len(problems)} application problem(s)** — code that "
            "does not work, or that ships a real hazard. Each one is written "
            "out below with its exact location, the offending source and how "
            "to fix it. Fix them."
        )
    else:
        out.append(
            f"It found **no application problems** — nothing here is broken or "
            f"dangerous. What remains is **{len(warnings)} simple warning(s)** "
            "about voice and aesthetics, summarized below. Treat this as a "
            "copy/design polish pass, not a bug hunt."
        )
    return out


def _emit_section(
    lines: list[str], section: int, impact: Impact, items: list[Finding], counter: int
) -> int:
    """Write one application-problem section; returns the running entry counter."""
    title, lead = _IMPACT_LEAD[impact]
    if impact is Impact.RISKY:
        lead = _risky_lead(items)
    lines.append("")
    lines.append(f"## {section}. {title} ({len(items)})")
    lines.append("")
    lines.append(lead)

    by_cat: dict[Category, list[Finding]] = defaultdict(list)
    for f in items:
        by_cat[f.category].append(f)
    for cat in Category:
        group = by_cat.get(cat)
        if not group:
            continue
        lines.append("")
        lines.append(f"### {cat.value} ({len(group)})")
        advice = _CATEGORY_ADVICE.get(cat)
        if advice:
            lines.append("")
            lines.append(f"> Strategy: {advice}")
        for f in group:
            counter += 1
            lines.append("")
            lines.extend(_entry(counter, f))
    return counter


def _emit_warnings(lines: list[str], section: int, warnings: list[Finding]) -> None:
    """Roll POLISH findings up to one line per rule family — the set-aside tail."""
    n_files = len({f.file for f in warnings})
    lines.append("")
    lines.append(
        f"## {section}. Simple warnings — {len(warnings)} finding(s) "
        f"in {n_files} file(s)"
    )
    lines.append("")
    lines.append(
        "Taste, not defects: nothing here blocks a ship. Listed as a summary "
        "so you know what was set aside — **not** as work for this pass. If "
        "the user asks for a copy/design pass later, start here."
    )
    lines.append("")
    groups: dict[str, list[Finding]] = defaultdict(list)
    for f in warnings:
        groups[_rollup_key(f.rule_id)].append(f)
    for key, group in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.extend(_rollup_line(key, group))


def _rollup_key(rule_id: str) -> str:
    """The family a warning rolls up under; word-list rules collapse to the family."""
    for fam in _ROLLUP_FAMILIES:
        if rule_id.startswith(fam):
            return fam.rstrip(".")
    return rule_id


def _rollup_line(key: str, group: list[Finding]) -> list[str]:
    """``- **family** — N hit(s) in a.html, b.jsx`` + examples + one fix line."""
    files = _sample([f.file for f in group], _ROLLUP_FILES)
    out = [f"- **{key}** — {len(group)} finding(s) in {files}"]
    samples = _sample(
        [_one_line(f.matched_text, 40) for f in group if f.matched_text.strip()],
        _ROLLUP_SAMPLES,
        quote=True,
    )
    if samples:
        out.append(f"  - examples: {samples}")
    else:
        # Doc-level aggregates (density scores) have no span to quote — the
        # message is the only thing that says what the finding means.
        out.append(f"  - {_one_line(group[0].message, 90)}")
    fix = Counter(f.suggested_fix for f in group if f.suggested_fix).most_common(1)
    if fix:
        out.append(f"  - fix: {fix[0][0]}")
    return out


def _sample(values: list[str], limit: int, *, quote: bool = False) -> str:
    """``a, b, c (+2 more)`` over the distinct ``values``, order preserved."""
    seen: list[str] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    shown = [f"`{v}`" if quote else v for v in seen[:limit]]
    if not shown:
        return ""
    extra = len(seen) - len(shown)
    return ", ".join(shown) + (f" (+{extra} more)" if extra else "")


def _entry(n: int, f: Finding) -> list[str]:
    out: list[str] = []
    out.append(
        f"#### {n}. `{f.file}:{f.line}:{f.col}` — {f.rule_id} "
        f"({f.severity.value}, {round(f.confidence * 100)}% confidence)"
    )
    out.append("")
    out.append(f.message)
    out.append("")
    if f.start == f.end == 0 and not f.matched_text:
        # Doc-level aggregate — quoting line 1 would misdirect the agent.
        out.append("- scope: the whole file (aggregate finding, no single span)")
    else:
        snippet = _numbered_snippet(f)
        fence = _fence_for("\n".join(snippet))
        out.append(fence)
        out.extend(snippet)
        out.append(fence)
    match = _one_line(f.matched_text)
    if match and match != _one_line(f.snippet):
        out.append(f"- match: `{match}`")
    out.append(f"- fix mode: {_FIX_MODE[f.fixability]}")
    if f.suggested_fix:
        out.append(f"- how to fix: {f.suggested_fix}")
    # Only worth a line when the template wraps the value in real structure.
    # A bare `{value}` restated the fix mode and nothing else, and the
    # parenthetical that used to follow — "(Real URL = the real value)" — was a
    # tautology: it spelled the label back out and added no information. What
    # the value should be is already on the "how to fix" line above.
    if (
        f.fixability is Fixability.PROMPT
        and f.replace_template
        and f.replace_template.strip() != "{value}"
    ):
        out.append(f"- replace the match with `{f.replace_template}`")
    return out


def _fence_for(body: str) -> str:
    """A code fence longer than any backtick run in ``body``.

    Findings from Markdown files (``codegen.markdown_fence`` above all) carry
    ``` in their snippet — a fixed three-backtick fence would end early and
    break the brief's rendering.
    """
    longest = max((len(m) for m in re.findall(r"`+", body)), default=0)
    return "`" * max(3, longest + 1)


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
