"""Structural landing-page tells of the modern AI template dialect.

Where :mod:`design_slop` flags *visual* signatures (gradients, glass, blobs are
there too), this module targets the page *recipe* current models converge on:

* **fake metric strip** — "99.9% uptime · 24/7 support · 10k+ users". A single
  real metric is normal marketing; two or more of these round, unverifiable
  stats in one file is the template. Counts already claimed by
  ``design.fake_social_proof`` ("Trusted by 10,000+ developers") are skipped so
  the same span is never flagged twice.
* **pricing triad cliché** — a "Most Popular"/"Best Value" badge + per-month
  pricing + an Enterprise/contact-sales tier, all in one file. Each element is
  common alone; the trio is the stock SaaS pricing card.
* **section recipe** — ``<!-- Hero Section -->`` / ``{/* Testimonials */}``
  scaffold comments. Three or more distinct stock section names is a generated
  page skeleton; Header/Main/Footer never count.
* **fake logo cloud** — a trust lead-in ("Trusted by…") followed by four or
  more big-brand names as bare text. Real logo walls ship image assets and
  permission; fabricated ones name-drop text spans.
* **blob glow** — the decorative ``rounded-full`` + ``blur-2xl/3xl`` gradient
  blob floating behind a hero. ``backdrop-blur`` (glassmorphism) never matches.

All of these are authorship tells, not broken code: DESIGN category,
WARNING/INFO severities, MANUAL fixes.
"""
from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding

_I = re.IGNORECASE

# ------------------------------------------------------------- fake metrics
_METRIC_RES: list[re.Pattern] = [
    # 99.9% uptime (any two-digit percent + uptime)
    re.compile(r"\b\d{2}(?:\.\d{1,3})?%\s+uptime\b", _I),
    # 24/7 support / monitoring / availability
    re.compile(
        r"\b24\s*/\s*7\s+(?:customer\s+|live\s+|expert\s+|human\s+)?"
        r"(?:support|monitoring|assistance|availability|coverage|access)\b",
        _I,
    ),
    # 10x faster / 3x more conversions
    re.compile(
        r"\b\d{1,4}x\s+(?:faster|quicker|better|cheaper|more\s+\w+|"
        r"productivity|growth|improvement|efficiency|engagement)\b",
        _I,
    ),
    # 10k+ users / 500+ integrations — the plus-rounded invented count
    re.compile(
        r"\b\d[\d,]*[km]?\+\s*(?:users?|customers?|companies|teams?|"
        r"developers?|downloads?|installs?|projects?|integrations?|"
        r"countries|stars?|clients?)\b",
        _I,
    ),
]
# Counts introduced by "trusted/used/loved by" or "join" belong to
# design.fake_social_proof — skip them here so one claim isn't flagged twice.
_PROOF_INTRO = re.compile(
    r"(?:(?:trusted|used|loved)\s+by|join(?:ed\s+by)?)\s+(?:over\s+)?$", _I
)
_METRIC_MIN = 2  # distinct stat matches required before anything fires


def metric_spans(text: str) -> list[tuple[int, int]]:
    """Spans of fabricated-stat matches (social-proof-claimed counts excluded)."""
    out: list[tuple[int, int]] = []
    for rx in _METRIC_RES:
        for m in rx.finditer(text):
            lead = text[max(0, m.start() - 40):m.start()]
            if _PROOF_INTRO.search(lead):
                continue
            out.append(m.span())
    return sorted(set(out))


# ------------------------------------------------------------ pricing triad
PRICE_BADGE = re.compile(r"\b(?:most\s+popular|best\s+value)\b", _I)
PER_MONTH = re.compile(
    r"(?:/\s*mo(?:nth)?\b|\bper\s+month\b|/\s*yr\b|\bper\s+year\b)", _I
)
_TOP_TIER = re.compile(r"\benterprise\b|\bcontact\s+sales\b", _I)

# ----------------------------------------------------------- section recipe
_SECTION_NAME = (
    r"(hero|features?|benefits|how\s+it\s+works|testimonials?|pricing|"
    r"faqs?|cta|call[-\s]to[-\s]action|social\s+proof|stats|newsletter|"
    r"final\s+cta|trust(?:ed)?\s+by|logo\s+cloud|integrations)"
)
_SECTION_COMMENT = re.compile(
    r"<!--\s*(?:the\s+)?" + _SECTION_NAME + r"(?:\s+section)?\s*-->"
    r"|\{\s*/\*\s*(?:the\s+)?" + _SECTION_NAME + r"(?:\s+section)?\s*\*/\s*\}",
    _I,
)
_RECIPE_MIN = 3  # distinct stock section names required


def section_comments(text: str) -> list[tuple[str, tuple[int, int]]]:
    """``(normalized_name, span)`` for each stock section-scaffold comment."""
    out: list[tuple[str, tuple[int, int]]] = []
    for m in _SECTION_COMMENT.finditer(text):
        name = m.group(1) or m.group(2)
        out.append((re.sub(r"\s+", " ", name.lower()), m.span()))
    return out


# ---------------------------------------------------------- fake logo cloud
# Case-sensitive on purpose: brand names appear capitalized in a logo row;
# lowercase prose ("uber cool", "meta description") never matches.
_BRAND = re.compile(
    r"\b(Google|Microsoft|Amazon|Meta|Netflix|Spotify|Airbnb|Uber|Slack|"
    r"Shopify|Stripe|Notion|Figma|Linear|Vercel|OpenAI|Coinbase|Dropbox|"
    r"Salesforce|Adobe|IBM|Intel|Samsung|Tesla|GitHub|Atlassian)\b"
)
_TRUST_INTRO = re.compile(
    r"(?:trusted|used|loved)\s+by|as\s+seen\s+(?:in|on)|featured\s+in|"
    r"\bpowering\b|join\s+(?:the\s+)?(?:likes\s+of|teams)",
    _I,
)
_CLOUD_MIN = 4        # distinct brands required
_CLOUD_WINDOW = 400   # brands must sit this close together
_INTRO_REACH = 600    # intro must sit this close to the brand row

# ------------------------------------------------------------------ blob glow
# Decorative glow blob: rounded-full + heavy blur in one class attribute.
# (?<!backdrop-) keeps glassmorphism out of this rule.
_BLOB = re.compile(
    r"(?<!backdrop-)\bblur-(?:2xl|3xl|\[\d{2,3}px\])[^\"'<>\n]{0,120}"
    r"\brounded-full\b"
    r"|\brounded-full\b[^\"'<>\n]{0,120}(?<!backdrop-)\bblur-(?:2xl|3xl|\[\d{2,3}px\])"
)


@file_rule
class LandingTellRule(PatternRule):
    category = Category.DESIGN
    patterns = [
        Pattern(
            id="design.blob_glow",
            regex=_BLOB,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Decorative glow blob (rounded-full + heavy blur) — stock AI hero dressing",
            suggested_fix="Remove the decorative blob or design intentional brand art",
            kinds=frozenset({"html", "jsx"}),
        ),
    ]

    def scan(self, sf: SourceFile) -> list[Finding]:
        out = super().scan(sf)
        kind = file_kind(sf.rel_path)
        if kind in ("html", "jsx", "md"):
            out.extend(self._fake_metrics(sf, kind))
        if kind in ("html", "jsx"):
            out.extend(self._pricing_triad(sf, kind))
            out.extend(self._section_recipe(sf))
            out.extend(self._fake_logo_cloud(sf, kind))
        return out

    def _fake_metrics(self, sf: SourceFile, kind: str) -> list[Finding]:
        """≥2 round, unverifiable stats in visible copy — the stat strip."""
        regions = prose_regions(sf.text, kind)
        spans = [
            (a, b) for a, b in metric_spans(sf.text) if in_any(regions, a, b)
        ]
        if len(spans) < _METRIC_MIN:
            return []
        return [
            build_finding(
                sf,
                rule_id="design.fake_metrics",
                category=self.category,
                severity=Severity.WARNING,
                message="Invented metric — part of a stat strip of unverifiable claims",
                start=a,
                end=b,
                fixability=Fixability.MANUAL,
                suggested_fix="Use a real, sourced number or drop the claim",
            )
            for a, b in spans
        ]

    def _pricing_triad(self, sf: SourceFile, kind: str) -> list[Finding]:
        """Badge + per-month price + Enterprise tier — the stock pricing card."""
        text = sf.text
        regions = prose_regions(text, kind)

        def hit(rx: re.Pattern) -> re.Match | None:
            for m in rx.finditer(text):
                if in_any(regions, m.start(), m.end()):
                    return m
            return None

        badge = hit(PRICE_BADGE)
        if badge is None or hit(PER_MONTH) is None or hit(_TOP_TIER) is None:
            return []
        return [
            build_finding(
                sf,
                rule_id="design.pricing_triad",
                category=self.category,
                severity=Severity.INFO,
                message=(
                    "Stock SaaS pricing triad ('Most Popular' badge + per-month "
                    "+ Enterprise tier) — template pricing section"
                ),
                start=badge.start(),
                end=badge.end(),
                fixability=Fixability.MANUAL,
                suggested_fix=(
                    "Price from your actual plans and language, not the "
                    "three-card template"
                ),
            )
        ]

    def _section_recipe(self, sf: SourceFile) -> list[Finding]:
        """≥3 distinct stock section-scaffold comments — a generated skeleton."""
        found = section_comments(sf.text)
        names = {n for n, _ in found}
        if len(names) < _RECIPE_MIN:
            return []
        first = min(span for _, span in found)
        return [
            build_finding(
                sf,
                rule_id="design.section_recipe",
                category=self.category,
                severity=Severity.WARNING,
                message=(
                    f"AI section recipe ({len(names)} stock sections: "
                    f"{', '.join(sorted(names))}) — generated page skeleton"
                ),
                start=first[0],
                end=first[1],
                fixability=Fixability.MANUAL,
                suggested_fix=(
                    "Restructure the page around your actual content instead "
                    "of the hero→features→pricing→FAQ template"
                ),
            )
        ]

    def _fake_logo_cloud(self, sf: SourceFile, kind: str) -> list[Finding]:
        """Trust lead-in + ≥4 big-brand names as bare text — fabricated logos."""
        text = sf.text
        regions = prose_regions(text, kind)
        intros = [m.start() for m in _TRUST_INTRO.finditer(text)
                  if in_any(regions, m.start(), m.end())]
        if not intros:
            return []
        brands = [
            m for m in _BRAND.finditer(text)
            if in_any(regions, m.start(), m.end())
        ]
        for i in range(len(brands)):
            window = [brands[i]]
            seen = {brands[i].group(1)}
            for m in brands[i + 1:]:
                if m.start() - brands[i].start() > _CLOUD_WINDOW:
                    break
                window.append(m)
                seen.add(m.group(1))
            if len(seen) < _CLOUD_MIN:
                continue
            if not any(abs(p - brands[i].start()) <= _INTRO_REACH for p in intros):
                continue
            anchor = window[0]
            return [
                build_finding(
                    sf,
                    rule_id="design.fake_logo_cloud",
                    category=self.category,
                    severity=Severity.WARNING,
                    message=(
                        f"Fabricated logo cloud ({len(seen)} big-brand names "
                        "under a trust claim)"
                    ),
                    start=anchor.start(),
                    end=anchor.end(),
                    fixability=Fixability.MANUAL,
                    suggested_fix=(
                        "Only name customers you actually have (with "
                        "permission) — or remove the logo row"
                    ),
                )
            ]
        return []
