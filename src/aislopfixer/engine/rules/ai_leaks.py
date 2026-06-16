"""Detect AI assistant phrases accidentally left in site content."""

from __future__ import annotations

import re

from ..context import file_kind, prose_regions
from ..models import Category, Fixability, Severity, Finding
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule

_I = re.IGNORECASE

# STRONG: unmistakable AI assistant residue. Safe to delete the whole line.
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


@file_rule
class AILeakRule(PatternRule):
    category = Category.AI_LEAK

    def scan(self, sf: SourceFile) -> list[Finding]:
        regions = prose_regions(sf.text, file_kind(sf.rel_path))
        # overlap check instead of strict containment — expand_line pushes
        # start/end to full line boundaries which may include HTML tags
        # on the same line. As long as the line overlaps prose, it's valid.
        return [
            f for f in super().scan(sf)
            if f.fixability != Fixability.AUTO
            or any(a < f.end and f.start < b for a, b in regions)
        ]

    # STRONG first: on a line matching both, dedupe keeps the AUTO-fix finding.
    patterns = [
        Pattern(
            id=f"ai_leak.strong.{i}",
            regex=re.compile(p, _I),
            severity=Severity.ERROR,
            fixability=Fixability.AUTO,
            message="AI assistant phrase left in content",
            suggested_fix="Delete this line",
            replacement="",
            expand_line=True,
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
