"""Palette analysis: which colours, how many hues, and whose choice they were.

Colour is where the default is hardest to see, because a stock Tailwind palette
looks *fine*. ``bg-white text-gray-900 border-gray-200 bg-indigo-600`` is a
competent, accessible, entirely unauthored palette — and it is the one nearly
every generated page arrives with.

Two things are measured. First, provenance: what share of the colours in the
project are shipped palette values rather than tokens or authored hexes.
Second, structure: how many chromatic hues exist at all, and whether the accent
sits in the blue→violet band that current models reach for by default.
"""

from __future__ import annotations

import re
from collections import Counter

from ..models import Axis, Document, Evidence, Observation, Origin
from .util import cap_evidence, evidence_for, styled_decls

# Approximate HSL hue of each Tailwind family — near-constant across shades, so
# one number per family is enough to count distinct hues.
FAMILY_HUE: dict[str, int] = {
    "slate": 215, "gray": 220, "zinc": 240, "neutral": 0, "stone": 33,
    "red": 0, "orange": 25, "amber": 38, "yellow": 48, "lime": 84,
    "green": 142, "emerald": 160, "teal": 173, "cyan": 189, "sky": 199,
    "blue": 217, "indigo": 239, "violet": 258, "purple": 271,
    "fuchsia": 292, "pink": 330, "rose": 350,
}
NEUTRAL_FAMILIES = frozenset({"slate", "gray", "zinc", "neutral", "stone"})
# The band current models default to for accents. Not wrong — just not chosen.
DEFAULT_ACCENT_BAND = frozenset({"blue", "indigo", "violet", "purple", "sky", "fuchsia"})

_HEX = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_SHADE = re.compile(r"^(.*)-(50|9[05]0|[1-8]00)$")
_STOCK_AT = 0.9
_MIN_COLORS = 6


def _family(value: str) -> str:
    """The palette family a colour value belongs to, or ``""``."""
    base = value.split("/", 1)[0]
    m = _SHADE.match(base)
    if m and m.group(1) in FAMILY_HUE:
        return m.group(1)
    if base in FAMILY_HUE:
        return base
    return ""


def hue_of_hex(value: str) -> int | None:
    """Hue angle of a ``#rrggbb`` literal, or ``None`` if achromatic/invalid."""
    m = _HEX.match(value.strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) < 6:
        return None
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 0.04:
        return None
    d = mx - mn
    if mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    return int(hue * 60) % 360


def collect(docs: list[Document]) -> tuple[list[tuple[str, Origin]], list[Evidence]]:
    """Every colour value in the project, with where it came from."""
    values: list[tuple[str, Origin]] = []
    evidence: list[Evidence] = []
    for doc in docs:
        for el in doc.elements:
            for d in el.decls:
                if d.axis is not Axis.COLOR:
                    continue
                values.append((d.value, d.origin))
                evidence.append(evidence_for(doc, el, d.raw or d.value))
        for d, ev in styled_decls(doc):
            if d.axis is Axis.COLOR:
                values.append((d.value, d.origin))
                evidence.append(ev)
        if doc.kind == "style":
            from ..parse.css import decl_from_css
            for rule in doc.css_rules:
                for prop, value in rule.decls.items():
                    for d in decl_from_css(prop, value):
                        if d.axis is Axis.COLOR:
                            values.append((d.value, d.origin))
    return values, evidence


def summarize(values: list[tuple[str, Origin]]) -> dict[str, list[str]]:
    """Grouped palette for the report: neutrals, accents, authored values."""
    neutrals: list[str] = []
    accents: list[str] = []
    authored: list[str] = []
    for value, origin in values:
        fam = _family(value)
        if origin in (Origin.TOKEN, Origin.ARBITRARY, Origin.LITERAL):
            authored.append(value)
        elif fam in NEUTRAL_FAMILIES:
            neutrals.append(value)
        elif fam:
            accents.append(value)
    def top(items: list[str]) -> list[str]:
        return [v for v, _ in Counter(items).most_common(10)]
    return {"neutral": top(neutrals), "accent": top(accents), "authored": top(authored)}


def analyze(docs: list[Document]) -> tuple[list[Observation], float, dict[str, list[str]]]:
    """Palette observations, the COLOR repetition score, and the palette map."""
    values, evidence = collect(docs)
    palette = summarize(values)
    if len(values) < _MIN_COLORS:
        return [], 0.0, palette

    out: list[Observation] = []
    shares: list[float] = []

    # Provenance is *not* repetition. Using the shipped palette already costs
    # the project on decision density; counting it again here made a plain,
    # hand-written page with a single neutral ramp score as repetitive as a
    # generated one, which is the wrong statement about a page whose structure
    # varies. Repetition on this axis means hue collapse, and only that.
    stock = sum(1 for _, o in values if o is Origin.DEFAULT)
    stock_share = stock / len(values)
    if stock_share >= _STOCK_AT:
        fams = Counter(f for f, _ in ((_family(v), o) for v, o in values) if f)
        listing = ", ".join(f"{f}" for f, _ in fams.most_common(4))
        out.append(Observation(
            axis=Axis.COLOR,
            id="color.stock_palette",
            title="Palet tamamen hazır rampadan",
            detail=(
                f"{len(values)} renk kullanımının %{stock_share * 100:.0f}'i "
                f"Tailwind'in hazır paletinden ({listing}). Projeye ait tek bir "
                f"renk tokenı yok. Hazır palet yanlış değil — ama seçilmemiş: "
                f"aynı rampayı bugün üretilen her sayfa kullanıyor, dolayısıyla "
                f"site kimseye benzemiyor değil, herkese benziyor."
            ),
            severity=round(min(1.0, stock_share), 3),
            stat=f"%{stock_share * 100:.0f} hazır",
            evidence=cap_evidence(evidence),
            prescription=(
                "Kendi rampanı üret: bir aksan hue'su seç, nötrleri o hue'ya "
                "doğru tonla (saf gray bırakma) ve renkleri rolle isimlendir "
                "(surface, ink, ink-muted, accent, rule). Shade numarasıyla "
                "değil rolle çağır."
            ),
        ))

    chroma = Counter(
        f for f in (_family(v) for v, _ in values)
        if f and f not in NEUTRAL_FAMILIES
    )
    if chroma:
        accent, n = chroma.most_common(1)[0]
        if accent in DEFAULT_ACCENT_BAND:
            share = n / sum(chroma.values())
            shares.append(share)
            out.append(Observation(
                axis=Axis.COLOR,
                id="color.default_accent",
                title=f"Aksan rengi varsayılan banttan: {accent}",
                detail=(
                    f"Kromatik renklerin %{share * 100:.0f}'i {accent} ailesinden "
                    f"(hue ≈ {FAMILY_HUE[accent]}°). Mavi–mor bandı, güncel "
                    f"modellerin hiçbir gerekçe olmadan seçtiği aralık; bir "
                    f"marka rengi değil, bir varsayılan."
                ),
                severity=round(min(1.0, 0.4 + share * 0.6), 3),
                stat=f"{accent} %{share * 100:.0f}",
                evidence=cap_evidence(
                    [e for e in evidence if accent in e.value], 6),
                prescription=(
                    "Aksanı markanın kendi hue'sundan seç. Mavi–mor bandı "
                    "kullanacaksan bile doygunluğu ve açıklığı kendin ayarla, "
                    "hazır 600 shade'ini alma."
                ),
            ))
        if len(chroma) == 1:
            shares.append(0.9)
            out.append(Observation(
                axis=Axis.COLOR,
                id="color.single_hue",
                title="Tek kromatik renk",
                detail=(
                    f"Bütün vurgular tek bir aileden ({accent}). Bağlantı, "
                    f"buton, rozet, ikon, odak halkası — hepsi aynı renk. "
                    f"Rolleri ayırt edecek ikinci bir renk yok, dolayısıyla "
                    f"renk hiçbir şey anlatmıyor, sadece süslüyor."
                ),
                severity=0.6,
                stat="1 hue",
                evidence=[],
                prescription=(
                    "Bir destek rengi ekle ve rolleri ayır: birincil eylem, "
                    "ikincil vurgu, bilgi/uyarı. En az iki kromatik hue tut."
                ),
            ))

    repetition = 100.0 * (sum(shares) / len(shares)) if shares else 0.0
    return out, round(repetition, 1), palette
