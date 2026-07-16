"""The AI-slop *visual design* signature (HTML/JSX/CSS).

Current-generation models converge on a recognizable landing-page aesthetic.
This module flags its strongest, least-ambiguous tells:

* **gradient cliché** — purple/indigo/blue→pink/violet hero gradients (Tailwind
  utility runs and raw CSS ``linear-gradient``). Brand-colored slate/teal
  gradients never match.
* **gradient text** — ``bg-clip-text text-transparent`` on a gradient headline
  (the stock AI hero title treatment).
* **fabricated social proof** — "Trusted by 10,000+ developers" / star-rating
  review claims with round invented numbers.
* **emoji-decorated UI copy** — 🚀✨💡-style decoration, count-gated (≥3).
* **fake avatar hosts** — pravatar / dicebear / ui-avatars / randomuser.me.
* **stock illustration CDNs** — undraw / storyset / popsy illustration URLs.
* **glassmorphism** — ``backdrop-blur`` + translucent white/black surface.
* **landing kit** — composite of classic AI-landing signals (Inter font, soft
  2xl radius, soft shadow, feature triad grid, dual CTAs, "How it works",
  glass, purple accent, "Introducing" badge pill, stat strip, pricing badge,
  section-scaffold comments). Fires only when ≥3 distinct families co-occur in
  one file *and* at least one of them is a strong, AI-correlated family (see
  ``_KIT_STRONG``) — single-signal pages and generic human Tailwind marketing
  (radii + shadows + CTAs alone) stay quiet.

The page-*structure* recipe rules (fake metrics, pricing triad, section
recipe, fake logo cloud, blob glow) live in :mod:`landing_tells`; marketing
copy templates live in :mod:`copy_slop`.

Everything here is a stylistic authorship tell, not broken code — severities
stay at WARNING/INFO and the category has its own DESIGN bucket. Most fixes
are MANUAL; only decorative emoji is AUTO-strippable.
"""
from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding
from .landing_tells import PER_MONTH, PRICE_BADGE, metric_spans, section_comments

_I = re.IGNORECASE

# ------------------------------------------------------------------ gradients
# Tailwind: purple-family start → pink/purple-family end (stock AI hero).
_TW_GRADIENT = re.compile(
    r"\bbg-gradient-to-[trbl]{1,2}\b[^\"'`\n]{0,120}?"
    r"\bfrom-(?:purple|violet|indigo|fuchsia|blue)-\d{2,3}\b[^\"'`\n]{0,160}?"
    r"\b(?:via|to)-(?:pink|purple|fuchsia|rose|violet)-\d{2,3}\b"
)

# Blue/sky → indigo/purple (documented "blue-to-purple" AI default, no pink).
_TW_BLUE_PURPLE = re.compile(
    r"\bbg-gradient-to-[trbl]{1,2}\b[^\"'`\n]{0,120}?"
    r"\bfrom-(?:blue|sky|cyan)-\d{2,3}\b[^\"'`\n]{0,160}?"
    r"\b(?:via|to)-(?:indigo|purple|violet|fuchsia)-\d{2,3}\b"
)

# Arbitrary Tailwind hex stops (from-[#8b5cf6] to-[#ec4899]).
_TW_ARBITRARY_GRADIENT = re.compile(
    r"\bbg-gradient-to-[trbl]{1,2}\b[^\"'`\n]{0,80}?"
    r"\bfrom-\[#(?:8b5cf6|a855f7|7c3aed|6d28d9|6366f1|4f46e5|c084fc|d946ef|"
    r"3b82f6|2563eb)\][^\"'`\n]{0,120}?"
    r"\b(?:via|to)-\[#(?:ec4899|f472b6|db2777|e879f9|ff00ff|a855f7|8b5cf6|"
    r"7c3aed|6366f1)\]",
    _I,
)

# Raw CSS: one linear-gradient() containing both a purple-family and a
# pink/violet-family stop (Tailwind hexes or CSS color keywords).
# ``_GINNER`` allows one level of nested parens so ``rgb(139, 92, 246)`` stops
# do not truncate the match at the first ``)``.
_GINNER = r"(?:[^)(\n]|\([^)(\n]*\))*"
_CSS_GRADIENT = re.compile(
    r"linear-gradient\("
    r"(?=" + _GINNER + r"(?:#(?:8b5cf6|a855f7|7c3aed|6d28d9|6366f1|4f46e5|c084fc|d946ef|"
    r"3b82f6|2563eb)\b|\b(?:purple|violet|blueviolet|mediumpurple)\b))"
    r"(?=" + _GINNER + r"(?:#(?:ec4899|f472b6|db2777|e879f9|ff00ff|a855f7|8b5cf6)\b"
    r"|\b(?:pink|hotpink|deeppink|magenta|fuchsia|violet)\b))"
    + _GINNER + r"\)",
    _I,
)

# Hero title: gradient paint clipped to glyphs.
_GRADIENT_TEXT = re.compile(
    r"\bbg-clip-text\b[^\"'`\n]{0,80}\btext-transparent\b"
    r"|\btext-transparent\b[^\"'`\n]{0,80}\bbg-clip-text\b"
)

# ----------------------------------------------------------- social proof
_AUDIENCE = (
    r"(?:developers?|companies|teams?|users?|customers?|businesses|"
    r"creators|professionals|brands|founders|engineers)"
)
_SOCIAL_PROOF = re.compile(
    r"\b(?:(?:trusted|used|loved)\s+by|join(?:ed\s+by)?)\s+(?:over\s+)?"
    r"\d[\d,.]*\s*[km]?\+?\s+(?:happy\s+|satisfied\s+)?" + _AUDIENCE + r"\b",
    _I,
)
# "4.9/5 from 2,000+ reviews" / "★ 4.8 · 10k reviews"
_REVIEW_STAT = re.compile(
    r"\b[1-5](?:\.\d)?\s*/\s*5\b[^.\n]{0,40}?\b\d[\d,.]*\s*[km]?\+?\s*"
    r"(?:reviews?|ratings?|customers?)\b"
    r"|\b\d[\d,.]*\s*[km]?\+?\s*(?:reviews?|ratings?)\b[^.\n]{0,30}?"
    r"\b[1-5](?:\.\d)?\s*(?:/\s*5|stars?)?\b",
    _I,
)

# Curated decorative set — the emojis models reach for as UI ornament.
_UI_EMOJI = re.compile(
    "([\U0001f680✨\U0001f3af\U0001f4a1⚡\U0001f525\U0001f389"
    "\U0001f31f⭐\U0001f4aa\U0001f6e0\U0001f512\U0001f4c8\U0001f4ca"
    "\U0001f3a8\U0001f916\U0001f449\U0001f4bb\U0001f308\U0001f9e0✅❤]"
    "(?:️)?[ \t]?)"
)
_EMOJI_COUNT_GATE = 3

# ----------------------------------------------------------- fake assets
_FAKE_AVATAR = re.compile(
    r"https?://(?:i\.)?pravatar\.cc/[^\s\"'`)]*"
    r"|https?://ui-avatars\.com/api/[^\s\"'`)]*"
    r"|https?://api\.dicebear\.com/[^\s\"'`)]*"
    r"|https?://(?:www\.)?randomuser\.me/[^\s\"'`)]*",
    _I,
)
_STOCK_ILLUSTRATION = re.compile(
    r"https?://(?:[a-z0-9.-]+\.)?undraw\.co/[^\s\"'`)]*"
    r"|https?://(?:storyset\.com|cdn\.storyset\.com)/[^\s\"'`)]*"
    r"|https?://illustrations\.popsy\.co/[^\s\"'`)]*"
    r"|https?://(?:openpeeps|blush)\.design/[^\s\"'`)]*",
    _I,
)

# ----------------------------------------------------------- glassmorphism
_GLASS = re.compile(
    r"\bbackdrop-blur(?:-(?:sm|md|lg|xl|2xl|3xl))?\b"
)
_GLASS_SURFACE = re.compile(
    r"\bbg-(?:white|black|slate|zinc|neutral|gray)/(?:5|10|20|25|30|40)\b"
    r"|\bborder-(?:white|black)/(?:5|10|20|25|30)\b"
    r"|background(?:-color)?:\s*rgba?\([^)]{0,40},\s*0?\.\d+\s*\)",
    _I,
)

# ----------------------------------------------------------- landing kit signals
# Each family contributes at most one hit toward the ≥3 threshold.
_KIT_INTER = re.compile(
    r"fonts\.googleapis\.com/css2?\?[^\"'\s>]*family=Inter\b"
    r"|font-family:\s*['\"]?Inter\b"
    r"|\bInter\s*\(\s*\{"
    r"|from\s+['\"]next/font/google['\"][^;]{0,200}\bInter\b"
    r"|\bimport\s*\{[^}]*\bInter\b[^}]*\}\s*from\s*['\"]next/font/google['\"]",
    _I,
)
_KIT_PURPLE_ACCENT = re.compile(
    r"\b(?:bg|text|border|ring|from|to|via|fill|stroke)"
    r"-(?:purple|violet|indigo|fuchsia)-\d{2,3}\b"
)
_KIT_SOFT_RADIUS = re.compile(r"\brounded-(?:2xl|3xl)\b")
_KIT_SOFT_SHADOW = re.compile(r"\bshadow-(?:xl|2xl)\b")
_KIT_FEATURE_GRID = re.compile(
    r"\b(?:sm:|md:|lg:|xl:)?grid-cols-3\b"
)
_KIT_DUAL_CTA = re.compile(
    r"\b(?:get\s+started(?:\s+free)?|start\s+(?:for\s+free|free\s+trial)|"
    r"try\s+(?:it\s+)?free|sign\s+up\s+free)\b",
    _I,
)
_KIT_SECONDARY_CTA = re.compile(
    r"\b(?:learn\s+more|book\s+a\s+demo|see\s+how\s+it\s+works|"
    r"watch\s+(?:the\s+)?demo|contact\s+sales)\b",
    _I,
)
_KIT_HOW_IT_WORKS = re.compile(r"\bhow\s+it\s+works\b", _I)
_KIT_LOGO_CLOUD = re.compile(
    r"\b(?:as\s+(?:seen|featured)\s+in|trusted\s+by\s+(?:industry\s+)?"
    r"leaders|companies\s+(?:that\s+)?trust\s+us)\b",
    _I,
)
# "✨ Announcing …" / "Introducing …" pill above the hero headline. Anchored to
# a text-node start (after '>' or line start) so attribute values never match.
_KIT_BADGE = re.compile(
    r"(?:^|>)\s*(?:[✨🎉🚀]\s*)?(?:announcing|introducing)\b", _I | re.M
)

_LANDING_KIT_MIN = 3   # distinct signal families required
_KIT_STAT_MIN = 2      # metric hits before the stat strip counts as a family
_KIT_SECTION_MIN = 2   # distinct scaffold comments before they count

# Weak families are everyday human Tailwind/marketing (soft radii, shadows,
# CTAs, a 3-col grid, "How it works", Inter); strong ones correlate with AI
# authorship on their own. The kit needs ≥1 strong family in the mix so a
# generic human marketing page never trips it on weak signals alone.
_KIT_STRONG = frozenset({
    "purple_accent", "badge_pill", "glass", "stat_strip",
    "pricing", "section_comments", "logo_cloud",
})


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
            regex=_TW_BLUE_PURPLE,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Blue→purple gradient — the stock AI hero aesthetic",
            suggested_fix="Pick colors from the project's actual brand palette",
            kinds=frozenset({"html", "jsx"}),
        ),
        Pattern(
            id="design.gradient_cliche",
            regex=_TW_ARBITRARY_GRADIENT,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Arbitrary purple-family gradient — stock AI hero aesthetic",
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
            id="design.gradient_text",
            regex=_GRADIENT_TEXT,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Gradient-clipped text — stock AI hero title treatment",
            suggested_fix="Use a solid brand color for headings, or a real brand gradient",
            kinds=frozenset({"html", "jsx"}),
        ),
        Pattern(
            id="design.fake_social_proof",
            regex=_SOCIAL_PROOF,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Invented social-proof stat — default AI filler claim",
            suggested_fix="Use a real, verifiable number or drop the claim",
            kinds=frozenset({"html", "jsx", "md"}),
        ),
        Pattern(
            id="design.fake_social_proof",
            regex=_REVIEW_STAT,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Invented review/rating stat — default AI filler claim",
            suggested_fix="Use a real, verifiable rating or drop the claim",
            kinds=frozenset({"html", "jsx", "md"}),
        ),
        Pattern(
            id="design.fake_avatar",
            regex=_FAKE_AVATAR,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Placeholder avatar host — stock AI testimonial face",
            suggested_fix="Use real customer photos or drop the avatar row",
            kinds=frozenset({"html", "jsx", "code"}),
        ),
        Pattern(
            id="design.stock_illustration",
            regex=_STOCK_ILLUSTRATION,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Stock illustration CDN — default AI empty-state art",
            suggested_fix="Commission brand art or use a real product screenshot",
            kinds=frozenset({"html", "jsx", "code", "md"}),
        ),
    ]

    def scan(self, sf: SourceFile) -> list[Finding]:
        out = super().scan(sf)
        kind = file_kind(sf.rel_path)
        if kind in ("html", "jsx"):
            out.extend(self._emoji_ui(sf, kind))
            out.extend(self._glassmorphism(sf))
            out.extend(self._landing_kit(sf))
        elif kind == "code" and sf.rel_path.lower().endswith(".css"):
            out.extend(self._landing_kit(sf))
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

    def _glassmorphism(self, sf: SourceFile) -> list[Finding]:
        """backdrop-blur + translucent surface — glassmorphism cliché."""
        blurs = list(_GLASS.finditer(sf.text))
        if not blurs:
            return []
        surfaces = list(_GLASS_SURFACE.finditer(sf.text))
        if not surfaces:
            return []
        # Require both families present; report the first blur as the anchor.
        m = blurs[0]
        return [
            build_finding(
                sf,
                rule_id="design.glassmorphism",
                category=self.category,
                severity=Severity.INFO,
                message="Glassmorphism (blur + translucent surface) — stock AI chrome",
                start=m.start(),
                end=m.end(),
                fixability=Fixability.MANUAL,
                suggested_fix="Use solid surfaces or a brand-specific material language",
            )
        ]

    def _landing_kit(self, sf: SourceFile) -> list[Finding]:
        """Composite AI-landing kit — ≥3 families, at least one strong."""
        text = sf.text
        signals: list[tuple[str, tuple[int, int]]] = []

        def add(name: str, rx: re.Pattern) -> None:
            m = rx.search(text)
            if m is not None:
                signals.append((name, m.span()))

        add("inter_font", _KIT_INTER)
        add("purple_accent", _KIT_PURPLE_ACCENT)
        # Density gates for radius/shadow — a single utility is normal UI.
        radius_hits = list(_KIT_SOFT_RADIUS.finditer(text))
        if len(radius_hits) >= 2:
            signals.append(("soft_radius", radius_hits[0].span()))
        shadow_hits = list(_KIT_SOFT_SHADOW.finditer(text))
        if len(shadow_hits) >= 2:
            signals.append(("soft_shadow", shadow_hits[0].span()))
        add("feature_grid", _KIT_FEATURE_GRID)
        add("how_it_works", _KIT_HOW_IT_WORKS)
        add("logo_cloud", _KIT_LOGO_CLOUD)
        add("badge_pill", _KIT_BADGE)
        if _GLASS.search(text) and _GLASS_SURFACE.search(text):
            m = _GLASS.search(text)
            assert m is not None
            signals.append(("glass", m.span()))
        # Dual CTA: primary + secondary both present.
        cta1 = _KIT_DUAL_CTA.search(text)
        cta2 = _KIT_SECONDARY_CTA.search(text)
        if cta1 and cta2:
            signals.append(("dual_cta", cta1.span()))
        # Recipe families shared with landing_tells (which owns the stricter
        # standalone rules); looser thresholds here since the kit needs ≥3.
        stats = metric_spans(text)
        if len(stats) >= _KIT_STAT_MIN:
            signals.append(("stat_strip", stats[0]))
        badge = PRICE_BADGE.search(text)
        if badge is not None and PER_MONTH.search(text) is not None:
            signals.append(("pricing", badge.span()))
        sections = section_comments(text)
        if len({n for n, _ in sections}) >= _KIT_SECTION_MIN:
            signals.append(("section_comments", sections[0][1]))

        if len(signals) < _LANDING_KIT_MIN:
            return []
        if not any(name in _KIT_STRONG for name, _ in signals):
            return []

        names = [n for n, _ in signals]
        # Anchor on the earliest match so the tree points at real source.
        anchor = min((span for _, span in signals), key=lambda s: s[0])
        return [
            build_finding(
                sf,
                rule_id="design.landing_kit",
                category=self.category,
                severity=Severity.WARNING,
                message=(
                    f"AI landing-page kit ({len(signals)} tells: "
                    f"{', '.join(names)})"
                ),
                start=anchor[0],
                end=anchor[1],
                fixability=Fixability.MANUAL,
                suggested_fix=(
                    "Replace the stock kit: real brand font/colors, unique "
                    "layout, verified claims — not the default AI landing template"
                ),
            )
        ]
