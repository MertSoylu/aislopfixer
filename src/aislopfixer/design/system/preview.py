"""Draw the derived system, so choosing between archetypes is not abstract.

The system screen used to answer "what will this change?" with a token list and
a diff. Both are exact and neither is *visible*: reading that ``--band-open``
became ``7.5rem`` does not tell anyone whether the page will breathe, and
cycling six archetypes by reading six lists is not choosing, it is guessing.

So this module renders the system as the terminal can show it — bars, swatches
and glyphs at true relative proportion. It is not a mockup of the page and does
not pretend to be one; it is the *system's* own numbers drawn to scale, which
is exactly the thing that differs between archetypes:

* the palette, as blocks of the real colours;
* the type scale, as bars whose length is each role's actual size;
* the band rhythm, as the vertical space each section role gets;
* the shape and depth language, as a drawn panel with the archetype's corners
  and elevation;
* the alignment doctrine, as where a section heading sits.

Everything here is presentation. Nothing in the measurement or the transform
reads it, so a wrong glyph is a cosmetic bug and never a wrong number.
"""

from __future__ import annotations

import re

from rich.text import Text

from ...theme import ACCENT, DIM, FAINT, TEXT
from .derive import DesignSystem

_REM = re.compile(r"^(-?\d*\.?\d+)\s*(rem|px|ch|em)?$")
_BAR = "█"
_TRACK = "─"

# Rounded corners exist in a terminal only as two glyph sets. The threshold is
# where a radius stops reading as "sharp" at normal display sizes.
_SHARP = ("┌", "┐", "└", "┘")
_ROUND = ("╭", "╮", "╰", "╯")
_ROUND_AT_PX = 6.0

# Bars are drawn against a *fixed* reference, not against the archetype's own
# largest value. Normalising per archetype would make every display size fill
# the row and every hero band look identical — which is the one thing the
# preview exists to tell apart.
_TYPE_REF_PX = 5.0 * 16      # a 5rem display fills the row
_BAND_REF_PX = 10.0 * 16     # a 10rem hero band fills the row

_SWATCHES = (
    ("paper", "kâğıt"), ("shell", "kabuk"), ("rule", "çizgi"),
    ("ink-muted", "soluk"), ("ink", "mürekkep"),
    ("accent-soft", "aksan·açık"), ("accent", "aksan"),
    ("support", "destek"),
)
_ROLES = ("display", "section", "title", "lead", "body", "meta")
_BANDS = (("open", "hero"), ("narrative", "anlatı"),
          ("dense", "yoğun"), ("close", "kapanış"))


def _px(value: str, root: float = 16.0) -> float:
    """A CSS length in px, or ``0`` when it is not a plain length."""
    m = _REM.match(value.strip())
    if m is None:
        return 0.0
    n = float(m.group(1))
    unit = m.group(2) or ""
    return n * root if unit in ("rem", "em", "") else n * (8.0 if unit == "ch" else 1.0)


def _bar(value: float, largest: float, width: int) -> str:
    if largest <= 0:
        return ""
    return _BAR * max(1, round(width * value / largest))


def _elevation(shadow: str) -> int:
    """0..3 — how far off the surface this shadow lifts something."""
    blur = max((float(n) for n in re.findall(r"(\d+(?:\.\d+)?)px", shadow)), default=0.0)
    if shadow.strip() in ("none", ""):
        return 0
    return 1 if blur <= 4 else (2 if blur <= 16 else 3)


def render(system: DesignSystem, width: int = 44) -> Text:
    """The system drawn to scale, as one block of terminal text."""
    c = system.colors
    bar_w = max(10, width - 18)
    t = Text()

    # ---------------------------------------------------------------- palette
    t.append("PALET\n", style=f"bold {DIM}")
    line = Text("  ")
    for key, _label in _SWATCHES:
        value = c.get(key)
        if value:
            line.append("███", style=f"{value} on {value}")
            line.append(" ")
    t.append(line)
    t.append("\n  ")
    t.append(f"{c['paper']} → {c['ink']}", style=FAINT)
    t.append(f"   aksan {c['accent']}\n\n", style=FAINT)

    # ------------------------------------------------------------- type scale
    t.append("TİP ÖLÇEĞİ", style=f"bold {DIM}")
    t.append(f"  {system.archetype.ratio}×  "
             f"{_first(system.families['display'])} / "
             f"{_first(system.families['body'])}\n", style=FAINT)
    for role in _ROLES:
        size = _px(system.sizes[role])
        t.append(f"  {role:<8}", style=DIM)
        t.append(_bar(size, _TYPE_REF_PX, bar_w), style=c["ink"])
        t.append(f" {system.sizes[role]}\n", style=FAINT)
    t.append("  tracking ", style=DIM)
    t.append(f"{system.tracking['display']}", style=TEXT)
    t.append("   leading ", style=DIM)
    t.append(f"{system.leading['display']}\n\n", style=TEXT)

    # ----------------------------------------------------------------- rhythm
    t.append("BANT RİTMİ\n", style=f"bold {DIM}")
    for key, label in _BANDS:
        t.append(f"  {label:<8}", style=DIM)
        t.append(_bar(_px(system.bands[key]), _BAND_REF_PX, bar_w), style=ACCENT)
        t.append(f" {system.bands[key]}\n", style=FAINT)
    t.append("  ölçüler ", style=DIM)
    t.append(" · ".join(system.measures[k] for k in ("read", "narrow", "content")),
             style=TEXT)
    t.append("\n\n")

    # ------------------------------------------------------- shape and depth
    t.append("BİÇİM & DERİNLİK\n", style=f"bold {DIM}")
    for role, shadow_key in (("panel", "float"), ("control", "lift")):
        radius = _px(system.radii[role])
        tl, tr, bl, br = _ROUND if radius >= _ROUND_AT_PX else _SHARP
        depth = _elevation(system.shadows.get(shadow_key, "none"))
        t.append(f"  {role:<8}", style=DIM)
        t.append(f"{tl}{'─' * 8}{tr}  ", style=c["rule"])
        t.append("▁" * (depth * 3) if depth else "—", style=c["ink-faint"])
        t.append(f"  r={system.radii[role]}  h{depth}\n", style=FAINT)
        t.append(f"  {'':<8}{bl}{'─' * 8}{br}\n", style=c["rule"])
    t.append("\n")

    # -------------------------------------------------------------- alignment
    t.append("HİZA & IZGARA\n", style=f"bold {DIM}")
    head = "Bölüm başlığı"
    pad = 0 if system.archetype.align == "left" else max(0, (bar_w - len(head)) // 2)
    t.append("  ")
    t.append(" " * pad + head, style=c["ink"])
    t.append(f"\n  {_TRACK * bar_w}\n", style=c["rule"])
    t.append(f"  {system.archetype.align} · {system.archetype.grid} · "
             f"gap {system.archetype.gap[0]}/{system.archetype.gap[1]}\n",
             style=FAINT)
    return t


def _first(stack: str) -> str:
    return stack.split(",")[0].strip().strip('"')
