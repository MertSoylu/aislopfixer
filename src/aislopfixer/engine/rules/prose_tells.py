"""LLM prose-writing tells beyond single marketing buzzwords.

These fire only inside human-visible prose (HTML/JSX text nodes, Markdown
non-code) — never in identifiers, CSS or code, because :func:`prose_regions`
returns ``[]`` for pure code. Each phrase is a recognizable large-language-model
crutch, tightened so ordinary writing slips through:

* ``not only … but also`` — both halves required within one clause.
* ``let's dive in`` / ``dive into`` — only with a call-to-action lead-in, so a
  neutral "you can dive into the source" is left alone.
* ``in this article/post/guide`` — self-referential blog opener (doc nouns only).
* stock connectives — ``that being said``, ``at the end of the day``, … (fixed
  idioms; phrases already owned by ai_leaks are excluded to avoid double-flagging).
* ``when it comes to`` — exact topic-introducer.
* **em-dash overuse** — an aggregate WARNING when a file's prose carries four or
  more letter-flanked em-dashes (U+2014); compound hyphens and numeric ranges
  are never counted.
"""

from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding

_I = re.IGNORECASE

# Letter-flanked em-dash only: excludes "state-of-the-art" (hyphen), "pp. 4–8"
# (en-dash) and "9—17" (digit-flanked range).
_EMDASH = re.compile(r"(?<=[A-Za-z])\s*—\s*(?=[A-Za-z])")
_EMDASH_THRESHOLD = 4


@file_rule
class ProseTellRule(PatternRule):
    category = Category.BUZZWORD
    patterns = [
        Pattern(
            id="prose.not_only_but_also",
            regex=re.compile(r"\bnot only\b[^.!?\n]{1,80}?\bbut also\b", _I),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="'not only … but also' — LLM correlative-conjunction crutch",
            suggested_fix="Rewrite as a direct statement",
        ),
        Pattern(
            id="prose.dive_in",
            regex=re.compile(
                r"\b(?:let'?s|we'?ll|time to|ready to|so,?\s+let'?s)\s+"
                r"dive\s+(?:right\s+)?in(?:to)?\b"
                r"|(?:^|[.!?]\s+)dive\s+(?:right\s+)?in\b",
                _I,
            ),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="'dive in' — LLM intro/CTA filler",
            suggested_fix="Get to the point without the warm-up",
        ),
        Pattern(
            id="prose.in_this_article",
            regex=re.compile(
                r"\bin this (?:article|post|blog post|guide|tutorial|write-?up|piece)\b",
                _I,
            ),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="'in this article/post' — self-referential blog opener",
            suggested_fix="Drop the meta-commentary",
        ),
        Pattern(
            id="prose.transition_filler",
            regex=re.compile(
                r"\b(?:that being said|with that being said|needless to say|"
                r"at the end of the day|without further ado|last but not least)\b",
                _I,
            ),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Empty connective phrase — LLM paragraph glue",
            suggested_fix="Delete the filler phrase",
        ),
        Pattern(
            id="prose.when_it_comes_to",
            regex=re.compile(r"\bwhen it comes to\b", _I),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="'when it comes to' — stock LLM topic-introducer",
            suggested_fix="State the topic directly",
        ),
    ]

    def scan(self, sf: SourceFile) -> list[Finding]:
        regions = prose_regions(sf.text, file_kind(sf.rel_path))
        findings = [f for f in super().scan(sf) if in_any(regions, f.start, f.end)]

        dashes = sum(
            1
            for m in _EMDASH.finditer(sf.text)
            if in_any(regions, m.start(), m.end())
        )
        if dashes >= _EMDASH_THRESHOLD:
            findings.append(
                build_finding(
                    sf,
                    rule_id="prose.emdash_density",
                    category=self.category,
                    severity=Severity.WARNING,
                    message=(
                        f"Em-dash overuse ({dashes} in prose) — a recognizable "
                        "LLM copy habit"
                    ),
                    start=0,
                    end=0,
                    fixability=Fixability.MANUAL,
                    suggested_fix="Replace most em-dashes with commas, periods or parentheses",
                )
            )
        return findings
