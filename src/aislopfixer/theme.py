"""Shared colors, icons and the shimmer gradient used across the TUI.

Every screen pulls its palette from here so the tool's own interface does not
commit the offence it reports — one accent, one radius, one spacing value.
"""

from __future__ import annotations

import colorsys

from .design.models import Axis

# One hue per axis, spaced around the wheel so eight bars read apart at a
# glance. Deliberately not a gradient: these are categories, not a scale.
AXIS_COLORS: dict[Axis, str] = {
    Axis.TYPE: "#f4a261",
    Axis.COLOR: "#e879a6",
    Axis.SPACE: "#36e2e6",
    Axis.SHAPE: "#9fd356",
    Axis.LAYOUT: "#a78bfa",
    Axis.MATERIAL: "#7dd3fc",
    Axis.MOTION: "#fbbf24",
    Axis.COPY: "#5eead4",
}

AXIS_ICON: dict[Axis, str] = {
    Axis.TYPE: "Aa",
    Axis.COLOR: "◐",
    Axis.SPACE: "↕",
    Axis.SHAPE: "▢",
    Axis.LAYOUT: "▦",
    Axis.MATERIAL: "◧",
    Axis.MOTION: "≈",
    Axis.COPY: "¶",
}


def severity_color(value: float) -> str:
    """An observation's severity, banded.

    Severity is continuous, but a continuous colour ramp is unreadable in a
    list — three bands is what a reader can actually act on.
    """
    if value >= 0.75:
        return "#f87171"
    if value >= 0.45:
        return "#fbbf24"
    return "#7dd3fc"


def score_color(value: float) -> str:
    """Colour for a 0-100 template score: low is good, high is the template."""
    if value >= 70:
        return "#f87171"
    if value >= 50:
        return "#fb923c"
    if value >= 30:
        return "#fbbf24"
    return "#4ade80"


def meter(value: float, width: int = 24, filled: str = "█", empty: str = "░") -> str:
    """A 0-100 value as a fixed-width bar."""
    n = max(0, min(width, round(width * value / 100.0)))
    return filled * n + empty * (width - n)


_SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """A run of 0-100 scores as one line.

    The scale is fixed to 0–100 rather than to the series' own range: a project
    that moved from 84 to 81 should look flat, and auto-scaling would draw it
    as a cliff. The shape has to mean the same thing in every project.
    """
    return "".join(
        _SPARK[max(0, min(len(_SPARK) - 1, int(v / 100.0 * len(_SPARK))))]
        for v in values
    )


# Core design tokens — every screen/widget should pull colors from here so the
# palette stays coherent (screens must not re-declare their own hex constants).
BG = "#0b0e14"        # app background
PANEL = "#11151f"     # raised card/panel surface
PANEL_ALT = "#0d111a" # sunken surface (inputs, footer, list/detail panes)
BORDER = "#232a38"    # idle border / hairline
BORDER_MID = "#2a2f3a"
TEXT = "#cdd6f4"      # primary text
DIM = "#7b8496"       # secondary text
FAINT = "#727c94"     # tertiary text / hints (WCAG AA ≥4.5:1 on BG)
SOURCE = "#8a94a6"    # source-code excerpt text
MUTED = "#9aa4b8"     # de-emphasized body text (between TEXT and DIM)
ACCENT = "#36e2e6"    # brand teal
ACCENT_ALT = "#a78bfa" # violet secondary accent
OK = "#4ade80"
WARN = "#fbbf24"
BAD = "#f87171"


def _shimmer(n: int = 30, lo: float = 0.45, hi: float = 0.88) -> list[str]:
    """Teal↔magenta ping-pong gradient for the animated banner."""
    seq: list[str] = []
    for i in range(n):
        t = i / (n - 1)
        tri = 1 - abs(2 * t - 1)  # triangle wave 0..1..0
        h = lo + (hi - lo) * tri
        r, g, b = colorsys.hsv_to_rgb(h, 0.7, 1.0)
        seq.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
    return seq


SHIMMER = _shimmer()
