"""The AI-slop *visual design* signature (HTML/JSX/CSS).

Current-generation models converge on a recognizable landing-page aesthetic.
This module flags its three strongest, least-ambiguous tells:

* **gradient cliché** — the purple/indigo→pink hero gradient, both as Tailwind
  utility runs (``bg-gradient-to-r from-purple-500 to-pink-500``) and as raw CSS
  ``linear-gradient(...)`` mixing the same hue families. Only that specific
  color family fires; a slate/brand-colored gradient never matches.
* **fabricated social proof** — "Trusted by 10,000+ developers" / "Join 50k+
  happy users" copy with a round invented number, the default filler stat.
* **emoji-decorated UI copy** — 🚀✨💡-style decoration sprinkled through
  headings/feature cards. Count-gated (≥3 per file) so a single intentional
  emoji never fires; matches only a curated decorative set, not all emoji,
  so genuine emoji *content* (chat apps, reaction pickers) stays quiet.

Everything here is a stylistic authorship tell, not broken code — severities
stay at WARNING/INFO and the category has its own DESIGN bucket.
"""

from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding

_I = re.IGNORECASE

# Tailwind: a gradient starting in the purple/indigo family and passing through
# or ending in the purple/pink family — the stock AI hero. Bounded by quote/
# backtick/newline so the run must sit inside one class attribute.
_TW_GRADIENT = re.compile(
    r"\bbg-gradient-to-[trbl]{1,2}\b[^\"'`\n]{0,120}?"
    r"\bfrom-(?:purple|violet|indigo|fuchsia|blue)-\d{2,3}\b[^\"'`\n]{0,160}?"
    r"\b(?:via|to)-(?:pink|purple|fuchsia|rose|violet)-\d{2,3}\b"
)

# Raw CSS variant: one linear-gradient() containing both a purple-family and a
# pink-family stop (Tailwind's own hex values or the CSS color keywords).
_CSS_GRADIENT = re.compile(
    r"linear-gradient\("
    r"(?=[^)\n]*(?:#(?:8b5cf6|a855f7|7c3aed|6d28d9|6366f1|4f46e5|c084fc|d946ef)\b"
    r"|\b(?:purple|violet|blueviolet|mediumpurple)\b))"
    r"(?=[^)\n]*(?:#(?:ec4899|f472b6|db2777|e879f9|ff00ff)\b"
    r"|\b(?:pink|hotpink|deeppink|magenta|fuchsia)\b))"
    r"[^)\n]*\)",
    _I,
)

_AUDIENCE = (
    r"(?:developers?|companies|teams?|users?|customers?|businesses|"
    r"creators|professionals|brands|founders|engineers)"
)
_SOCIAL_PROOF = re.compile(
    r"\b(?:(?:trusted|used|loved)\s+by|join(?:ed\s+by)?)\s+(?:over\s+)?"
    r"\d[\d,.]*\s*[km]?\+?\s+(?:happy\s+|satisfied\s+)?" + _AUDIENCE + r"\b",
    _I,
)

# Curated decorative set — the emojis models reach for as UI ornament. Kept
# narrow on purpose; arbitrary emoji in real content must not count.
_UI_EMOJI = re.compile(
    "([\U0001f680✨\U0001f3af\U0001f4a1⚡\U0001f525\U0001f389"
    "\U0001f31f⭐\U0001f4aa\U0001f6e0\U0001f512\U0001f4c8\U0001f4ca"
    "\U0001f3a8\U0001f916\U0001f449\U0001f4bb\U0001f308\U0001f9e0✅❤]"
    "(?:️)?[ \t]?)"
)
_EMOJI_COUNT_GATE = 3


@file_rule
class DesignSlopRule(PatternRule):
    category = Category.DESIGN
    patterns = [
        Pattern(
            id="design.gradient_cliche",
            regex=_TW_GRADIENT,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Purple→pink gradient — the stock AI hero aesthetic",
            suggested_fix="Pick colors from the project's actual brand palette",
            kinds=frozenset({"html", "jsx"}),
        ),
        Pattern(
            id="design.gradient_cliche",
            regex=_CSS_GRADIENT,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Purple→pink gradient — the stock AI hero aesthetic",
            suggested_fix="Pick colors from the project's actual brand palette",
            kinds=frozenset({"html", "jsx", "code"}),
        ),
        Pattern(
            id="design.fake_social_proof",
            regex=_SOCIAL_PROOF,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Invented social-proof stat — default AI filler claim",
            suggested_fix="Use a real, verifiable number or drop the claim",
        ),
    ]

    def scan(self, sf: SourceFile) -> list[Finding]:
        out = super().scan(sf)
        kind = file_kind(sf.rel_path)
        if kind in ("html", "jsx"):
            out.extend(self._emoji_ui(sf, kind))
        return out

    def _emoji_ui(self, sf: SourceFile, kind: str) -> list[Finding]:
        """Decorative-emoji copy, count-gated so one intentional emoji is fine."""
        regions = prose_regions(sf.text, kind)
        hits = [
            m
            for m in _UI_EMOJI.finditer(sf.text)
            if in_any(regions, m.start(1), m.start(1) + 1)
        ]
        if len(hits) < _EMOJI_COUNT_GATE:
            return []
        return [
            build_finding(
                sf,
                rule_id="design.emoji_ui",
                category=self.category,
                severity=Severity.INFO,
                message="Decorative emoji in UI copy — AI landing-page dressing",
                start=m.start(1),
                end=m.end(1),
                fixability=Fixability.AUTO,
                suggested_fix="Remove the decorative emoji",
                replacement="",
            )
            for m in hits
        ]
