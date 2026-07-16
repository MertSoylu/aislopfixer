"""Marketing-copy slop: template microcopy and interchangeable testimonials.

Two families, both prose-only (HTML/JSX text nodes, Markdown):

* **generic microcopy** (``copy.microcopy.*``) — "No credit card required",
  "Cancel anytime", "Everything you need to…", "Get started in minutes".
  Any one of these is ordinary SaaS copy, so a single hit stays silent; two or
  more *distinct* phrases in one file is the interchangeable template voice.
* **template testimonials** (``copy.testimonial.*``) — "completely transformed
  the way we work", "can't imagine working without it", "game-changer for our
  team". Each shape is specific enough to fire alone; a quote with real
  specifics ("cut month-end close from 4 days to 6 hours") never matches.

Both report under BUZZWORD with modest confidence — they are copy-quality
tells, and corroboration lifts them when the file carries other AI signals.
"""
from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule

_I = re.IGNORECASE

_MICROCOPY: list[tuple[str, str]] = [
    ("no_credit_card", r"no\s+credit\s+card\s+(?:required|needed)"),
    ("cancel_anytime", r"cancel\s+(?:at\s+)?any\s*time"),
    ("free_forever", r"free\s+forever"),
    ("start_in_minutes",
     r"(?:get\s+started|up\s+and\s+running|set\s*up)\s+in\s+(?:seconds|minutes)"),
    ("minutes_not_days", r"in\s+minutes,?\s+not\s+(?:hours|days|weeks|months)"),
    ("everything_you_need", r"everything\s+you\s+need\s+to\b"),
    ("loved_by",
     r"loved\s+by\s+(?:developers|teams|thousands|founders|creators)"),
    ("join_thousands", r"join\s+thousands\s+of"),
    ("start_free_trial", r"start\s+your\s+free\s+trial"),
    ("all_in_one_place", r"all\s+in\s+one\s+place"),
    ("the_x_way",
     r"the\s+(?:smartest|fastest|easiest|simplest|best)\s+way\s+to\b"),
    ("made_simple", r"\b\w+\s+made\s+(?:simple|easy|effortless)\b"),
]
_MICROCOPY_MIN = 2  # distinct phrases required before any of them fires

_TESTIMONIAL: list[tuple[str, str]] = [
    ("transformed",
     r"(?:completely|totally|absolutely|truly)?\s*(?:transformed|revolutionized)"
     r"\s+(?:the\s+way\s+|how\s+)(?:we|our|i)\b"),
    ("cant_imagine",
     r"can'?t\s+imagine\s+(?:working|life|(?:our|my)\s+(?:workflow|day))\s+without"),
    ("game_changer_for", r"game[-\s]?chang(?:er|ing)\s+for\s+(?:us|our|my|me)\b"),
    ("best_decision",
     r"best\s+(?:decision|investment)\s+(?:we|i)(?:'ve|\s+have)?\s+(?:ever\s+)?made"),
    ("highly_recommend", r"highly\s+recommend(?:ed)?\s+(?:to|for)\s+any(?:one|body)"),
    ("couldnt_be_happier", r"couldn'?t\s+be\s+happier"),
    ("ten_out_of_ten", r"\b10\s*/\s*10\b[^.\n]{0,20}(?:would|recommend)"),
]


@file_rule
class CopySlopRule(PatternRule):
    category = Category.BUZZWORD
    patterns = [
        Pattern(
            id=f"copy.microcopy.{slug}",
            regex=re.compile(r"\b" + rx, _I),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Template SaaS microcopy — interchangeable AI landing voice",
            suggested_fix="Say something only this product can say",
        )
        for slug, rx in _MICROCOPY
    ] + [
        Pattern(
            id=f"copy.testimonial.{slug}",
            regex=re.compile(r"\b" + rx, _I),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Template testimonial phrasing — reads as a fabricated quote",
            suggested_fix="Quote a real customer with concrete, checkable specifics",
        )
        for slug, rx in _TESTIMONIAL
    ]

    def scan(self, sf: SourceFile) -> list[Finding]:
        regions = prose_regions(sf.text, file_kind(sf.rel_path))
        findings = [f for f in super().scan(sf) if in_any(regions, f.start, f.end)]
        micro = {f.rule_id for f in findings if f.rule_id.startswith("copy.microcopy")}
        if len(micro) < _MICROCOPY_MIN:
            findings = [
                f for f in findings if not f.rule_id.startswith("copy.microcopy")
            ]
        return findings
