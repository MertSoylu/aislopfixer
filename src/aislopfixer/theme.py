"""Shared colors, icons and the shimmer gradient used across the TUI."""

from __future__ import annotations

import colorsys

from .engine.models import Category, Severity

CATEGORY_COLORS: dict[Category, str] = {
    Category.AI_LEAK: "#ff5fd2",
    Category.PLACEHOLDER: "#fbbf24",
    Category.BUZZWORD: "#a78bfa",
    Category.DUPLICATE: "#36e2e6",
    Category.ACCESSIBILITY: "#4ade80",
    Category.CODE_SLOP: "#f59e0b",
}

CATEGORY_ICON: dict[Category, str] = {
    Category.AI_LEAK: "◈",
    Category.PLACEHOLDER: "▢",
    Category.BUZZWORD: "✦",
    Category.DUPLICATE: "⧉",
    Category.ACCESSIBILITY: "⊙",
    Category.CODE_SLOP: "⌁",
}

SEVERITY_COLORS: dict[Severity, str] = {
    Severity.ERROR: "#f87171",
    Severity.WARNING: "#fbbf24",
    Severity.INFO: "#7dd3fc",
}

SEVERITY_ICON: dict[Severity, str] = {
    Severity.ERROR: "●",
    Severity.WARNING: "▲",
    Severity.INFO: "■",
}

FIX_ICON: dict[str, str] = {"auto": "⚡", "prompt": "✎", "manual": "⚑"}
FIX_COLOR: dict[str, str] = {"auto": "#4ade80", "prompt": "#7dd3fc", "manual": "#7b8496"}

DIM = "#7b8496"
ACCENT = "#36e2e6"
OK = "#4ade80"
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
