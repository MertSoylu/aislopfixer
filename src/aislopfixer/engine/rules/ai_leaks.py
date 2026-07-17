"""Detect AI assistant phrases accidentally left in site content."""

from __future__ import annotations

import re

from ..context import ext_of, file_kind, prose_regions
from ..models import Category, Fixability, Severity, Finding, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding, line_bounds

_I = re.IGNORECASE

# STRONG: unmistakable AI assistant residue. Deleted outright — but only ever
# the line it owns; see :func:`_owns_its_line`.
_STRONG = [
    r"as an ai language model",
    r"as a large language model",
    r"as of my last (?:knowledge |training )?(?:update|cutoff|data)",
    r"\bmy (?:last )?training data\b",
    r"i (?:do not|don'?t) have (?:real[- ]time|access to real)",
    r"i (?:cannot|can'?t) fulfill (?:that|this|your) request",
    r"i (?:don'?t|do not) have personal (?:opinions|feelings|preferences|experiences|beliefs)",
    r"i (?:can'?t|cannot|am unable to) (?:browse|access) (?:the )?(?:internet|web|real[- ]time)",
    r"i'?m (?:a |an )?(?:large )?language model",
    r"as an ai,? i (?:can'?t|cannot|don'?t|do not|am)\b",
]

# SOFT: conversational sign-offs that can be legitimate copy (a contact page may
# genuinely say "feel free to reach out"). Flag for review; never auto-delete.
# Tightened so common prose ("I can't help but smile") does not trip them.
_SOFT = [
    r"feel free to (?:customize|modify|adjust|tweak|edit|change|use this)",
    r"let me know if you(?:'?d like| need| want| have)[^.\n]{0,40}"
    r"(?:question|change|adjust|help|else|further)",
    r"please note that i (?:can|cannot|can'?t|do not|don'?t|am)\b",
    r"i (?:cannot|can'?t) (?:help|assist|provide|comply)\b(?! but)",
    r"it'?s (?:important|worth) (?:to note|noting) that",
    r"i'?d be happy to (?:help|assist)",
    r"i hope this helps[.!]?",
    # common conversational phrases that can appear in legitimate docs
    r"certainly[.!]? here(?:'?s| is)",
    r"sure[.!]?,? here(?:'?s| is) (?:the|a|an|your)",
    r"here(?:'?s| is) (?:the|a|an|your) (?:updated|revised|complete|rewritten|requested|final) ",
    r"of course[.!] here(?:'?s| is)",
    r"i'?m sorry,? but i (?:can'?t|cannot|am unable)",
    # specific phrases that overlap with legitimate content
    r"as an ai assistant",
    r"\bknowledge cutoff\b",
]

_TAG = re.compile(r"<[^>]*>")

# Characters that close the text run *before* a leak, or open the one after it.
# Deliberately generous: a stop char only ever makes the sentence span smaller,
# and a smaller span means more leftover in ``rest`` — i.e. it errs toward
# MANUAL, which is the safe direction. ``}``/``{`` bound a JSX expression.
_SENT_BACK = ".!?>}"
_SENT_FWD = ".!?<{"


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """The span of the sentence carrying ``[start, end)``, clamped to its line."""
    ls, le = line_bounds(text, start)
    s = start
    while s > ls and text[s - 1] not in _SENT_BACK:
        s -= 1
    e = max(end, s)
    while e < le and text[e] not in _SENT_FWD:
        e += 1
    if e < le and text[e] in ".!?":
        e += 1  # the sentence owns its terminator
    return s, e


def _owns_its_line(text: str, start: int, end: int) -> bool:
    """True when the leak's sentence is the only real content on its line.

    Deleting the whole line is only safe when nothing else lives there. This
    used to be unconditional (``expand_line=True`` + ``replacement=""``), so a
    leak sitting mid-line took real code with it: on
    ``return <p>Hi {name} — as an AI language model, …</p>;`` the *return*
    vanished and the component rendered nothing, and the run still reported
    "no slop found — fixed automatically". Markup and punctuation around the
    sentence don't count as content; a word does.
    """
    ls, le = line_bounds(text, start)
    s, e = _sentence_span(text, start, end)
    rest = _TAG.sub("", text[ls:s] + text[e:le])  # the wrapper is not content
    return not re.sub(r"[\W_]+", "", rest)


@file_rule
class AILeakRule(PatternRule):
    category = Category.AI_LEAK

    def scan(self, sf: SourceFile) -> list[Finding]:
        # Code comments are human prose too — an "as an AI language model" tell
        # leaks into a JSDoc block as readily as into page copy (ext enables it).
        # Soft sign-offs are gated the same way: a string literal or test fixture
        # that quotes "I hope this helps" is not site content.
        regions = prose_regions(sf.text, file_kind(sf.rel_path), ext_of(sf.rel_path))
        # overlap check instead of strict containment — the SOFT patterns still
        # use expand_line, pushing start/end to full line boundaries that may
        # include HTML tags. As long as the line overlaps prose, it's valid.
        out: list[Finding] = []
        for f in super().scan(sf):
            if not any(a < f.end and f.start < b for a, b in regions):
                continue
            if f.rule_id.startswith("ai_leak.strong"):
                f = self._resolve_strong(sf, f)
            out.append(f)
        return out

    def _resolve_strong(self, sf: SourceFile, f: Finding) -> Finding:
        """Delete the line only when the leak owns it; otherwise hand it back.

        The phrase alone cannot be excised — "Hi {name} — , I cannot browse the
        web." is not a fix — so when real content shares the line there is no
        safe automatic edit and a human or an agent has to make the call.
        """
        if _owns_its_line(sf.text, f.start, f.end):
            return build_finding(
                sf,
                rule_id=f.rule_id,
                category=self.category,
                severity=f.severity,
                message=f.message,
                start=f.start,
                end=f.end,
                fixability=Fixability.AUTO,
                suggested_fix="Delete this line",
                replacement="",
                expand_line=True,
            )
        f.fixability = Fixability.MANUAL
        f.suggested_fix = (
            "Remove the AI phrase and repair the sentence around it — real "
            "content shares this line, so there is no safe automatic edit"
        )
        return f

    # STRONG first: on a line matching both, dedupe keeps the AUTO-fix finding.
    # No expand_line here: the span is the phrase, and _resolve_strong widens it
    # to the line only for the leaks that own one.
    patterns = [
        Pattern(
            id=f"ai_leak.strong.{i}",
            regex=re.compile(p, _I),
            severity=Severity.ERROR,
            fixability=Fixability.AUTO,
            message="AI assistant phrase left in content",
            suggested_fix="Delete this line",
            replacement="",
        )
        for i, p in enumerate(_STRONG)
    ] + [
        Pattern(
            id=f"ai_leak.soft.{i}",
            regex=re.compile(p, _I),
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Conversational AI sign-off — verify this is intentional",
            suggested_fix="Remove if this is leftover AI chatter",
            expand_line=True,
        )
        for i, p in enumerate(_SOFT)
    ]
