"""Detect generic AI marketing buzzwords and high-density filler blocks."""

from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Fixability, Severity, SourceFile, Finding
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding

_I = re.IGNORECASE

_WORDS = [
    "cutting-edge",
    "state-of-the-art",
    "seamlessly",
    "seamless",
    "revolutionize",
    "revolutionary",
    "game-changer",
    "game-changing",
    "unlock the power",
    "take it to the next level",
    "next-level",
    "in today's fast-paced world",
    "in today's digital age",
    "leverage",
    "synergy",
    "synergize",
    "elevate your",
    "best-in-class",
    "world-class",
    "paradigm shift",
    "think outside the box",
    "low-hanging fruit",
    "move the needle",
    "deep dive",
    "robust solution",
    "holistic approach",
    "empower your",
    "supercharge",
    "unleash the",
    "transformative",
    "turnkey solution",
    "one-stop shop",
    # classic large-language-model tells
    "delve into",
    "delve",
    "tapestry",
    "testament to",
    "in the realm of",
    "treasure trove",
    "ever-evolving",
    "ever-changing",
    "look no further",
    "rest assured",
    "a myriad of",
    "plethora of",
    "navigating the",
    "comprehensive suite",
    "unparalleled",
    "bustling",
]

_DENSITY_THRESHOLD = 5


@file_rule
class BuzzwordRule(PatternRule):
    category = Category.BUZZWORD
    patterns = [
        Pattern(
            id=f"buzzword.{re.sub(r'[^a-z]+', '_', w)}",
            regex=re.compile(r"\b" + re.escape(w) + r"\b", _I),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message=f"Generic buzzword: {w!r}",
            suggested_fix="Rewrite in plain, specific language",
        )
        for w in _WORDS
    ]

    def scan(self, sf: SourceFile) -> list[Finding]:
        # Buzzwords only count as slop in human-visible prose. In pure code
        # ('leverage', 'synergy' as identifiers) or CSS they are not slop.
        regions = prose_regions(sf.text, file_kind(sf.rel_path))
        findings = [f for f in super().scan(sf) if in_any(regions, f.start, f.end)]
        if len(findings) >= _DENSITY_THRESHOLD:
            findings.append(
                build_finding(
                    sf,
                    rule_id="buzzword.density",
                    category=self.category,
                    severity=Severity.WARNING,
                    message=(
                        f"High buzzword density ({len(findings)} hits) "
                        "— reads as generic AI filler"
                    ),
                    start=0,
                    end=0,
                    fixability=Fixability.MANUAL,
                    suggested_fix="Rewrite this content to be concrete and specific",
                )
            )
        return findings
