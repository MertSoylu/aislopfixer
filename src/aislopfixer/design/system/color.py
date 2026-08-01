"""Colour maths for building a project-specific ramp.

Everything here is deterministic: the same hue in gives the same eleven-step
ramp out, every run, on every machine. That matters because the transformer
rewrites source files with these values — a palette that drifted between runs
would produce a different diff each time and be impossible to review.

The ramps are built in HSL with a lightness curve rather than by interpolating
between two hexes, because a straight interpolation collapses the mid-tones and
produces the muddy 400-600 band that makes generated palettes look alike.
"""

from __future__ import annotations

import colorsys

# Lightness stops, dark→light, matching the familiar 950…50 ordering. The curve
# is steeper at the ends so the extremes stay usable as text and page colours.
RAMP_STEPS = (950, 900, 800, 700, 600, 500, 400, 300, 200, 100, 50)
_LIGHTNESS = (0.09, 0.16, 0.24, 0.33, 0.43, 0.53, 0.63, 0.74, 0.84, 0.92, 0.965)
# Targets are *chroma*, not saturation. HSL saturation means less and less as
# lightness approaches either end — S=0.05 at L=0.965 is indistinguishable from
# white — so a ramp specified in saturation loses its hue exactly where the
# largest areas of a page live. Specifying chroma and solving for S keeps the
# tint visible from the page background all the way down to the ink.
_CHROMA = (0.16, 0.28, 0.42, 0.56, 0.68, 0.72, 0.62, 0.46, 0.30, 0.16, 0.075)
_MIN_SPAN = 0.10   # floor on (1 − |2L − 1|) so the ends stay solvable


def hex_of(h: float, s: float, ll: float) -> str:
    """HSL (hue in degrees, s/l in 0..1) → ``#rrggbb``."""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, max(0.0, min(1.0, ll)),
                                  max(0.0, min(1.0, s)))
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def hsl_of(value: str) -> tuple[float, float, float] | None:
    """``#rrggbb`` → ``(hue°, saturation, lightness)``; ``None`` if unparsable."""
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) < 6:
        return None
    try:
        r, g, b = (int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    h, ll, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s, ll


def _saturation_for(chroma: float, lightness: float) -> float:
    """The HSL saturation that yields ``chroma`` at this lightness."""
    span = max(_MIN_SPAN, 1.0 - abs(2.0 * lightness - 1.0))
    return max(0.0, min(1.0, chroma / span))


def ramp(hue: float, chroma: float = 1.0) -> dict[int, str]:
    """An eleven-step ramp at one hue. ``chroma`` scales the whole curve."""
    return {
        step: hex_of(hue, _saturation_for(_CHROMA[i] * chroma, _LIGHTNESS[i]),
                     _LIGHTNESS[i])
        for i, step in enumerate(RAMP_STEPS)
    }


def neutral_ramp(hue: float, tint: float) -> dict[int, str]:
    """A neutral ramp pulled toward ``hue``.

    ``tint`` is the target chroma, held roughly constant across the ramp: 0.0
    is a true achromatic grey (which is what the shipped palettes give you, and
    what makes them read as unauthored), while 0.05–0.12 is the range where a
    neutral starts to belong to a brand without announcing itself.
    """
    return {
        step: hex_of(hue, _saturation_for(tint, _LIGHTNESS[i]), _LIGHTNESS[i])
        for i, step in enumerate(RAMP_STEPS)
    }


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast between two hex colours, for verifying a derived pair."""
    def lum(value: str) -> float:
        v = value.strip().lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        parts = []
        for i in (0, 2, 4):
            c = int(v[i:i + 2], 16) / 255
            parts.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(background: str, candidates: list[str], target: float = 4.5) -> str:
    """The first candidate that clears ``target`` against ``background``.

    Falls back to whichever candidate has the highest contrast, so a derived
    palette always produces *something* legible rather than failing shut.
    """
    best, best_ratio = candidates[0], 0.0
    for value in candidates:
        ratio = contrast_ratio(background, value)
        if ratio >= target:
            return value
        if ratio > best_ratio:
            best, best_ratio = value, ratio
    return best
