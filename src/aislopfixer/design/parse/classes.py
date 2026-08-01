"""Tailwind utility class → normalized design declaration.

This module is where "is this a decision?" gets answered, so its default tables
matter more than its regexes. ``py-20`` and ``py-[4.5rem]`` express the same
*property*; only the second one required anyone to look at the screen. The
first is :class:`~aislopfixer.design.models.Origin.DEFAULT` — a value the
framework already picked — and a page built entirely from those has a decision
count near zero no matter how many classes it carries. That distinction is the
whole measurement.

Three origins come out of here:

* ``DEFAULT`` — the value is a key in Tailwind's shipped scale (``py-20``,
  ``text-xl``, ``rounded-2xl``, ``bg-gray-100``, ``duration-300``).
* ``ARBITRARY`` — an escape-hatch value (``text-[2.75rem]``, ``py-[68px]``,
  ``bg-(--brand)``). Someone typed a number.
* ``TOKEN`` — a name that is not in the default scale, so it must come from the
  project's own theme (``bg-surface``, ``rounded-card``, ``text-display-2``).
  The strongest evidence of design work: a *system*, not a one-off.

Unknown utilities are dropped rather than guessed at. A wrong axis is worse
than a missing one — it moves a score for a reason nobody can verify.
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache

from ..models import Axis, Decl, Origin
from .theme import ThemeIndex

# ---------------------------------------------------------------- default scales
# Tailwind's shipped spacing keys. Anything outside this set on a spacing prop
# came from the project (theme extension) or from an arbitrary value.
SPACING = frozenset(
    ["0", "px", "0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "5", "6", "7",
     "8", "9", "10", "11", "12", "14", "16", "20", "24", "28", "32", "36",
     "40", "44", "48", "52", "56", "60", "64", "72", "80", "96", "auto"]
)
SIZE_KEYWORDS = frozenset(
    ["auto", "full", "screen", "min", "max", "fit", "svh", "lvh", "dvh", "px",
     "prose", "none"]
)
FRACTIONS = re.compile(r"^\d{1,2}/\d{1,2}$")

FONT_SIZE = frozenset(
    ["xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl", "7xl",
     "8xl", "9xl"]
)
FONT_WEIGHT = frozenset(
    ["thin", "extralight", "light", "normal", "medium", "semibold", "bold",
     "extrabold", "black"]
)
FONT_FAMILY = frozenset(["sans", "serif", "mono"])
LEADING = frozenset(
    ["none", "tight", "snug", "normal", "relaxed", "loose",
     "3", "4", "5", "6", "7", "8", "9", "10"]
)
TRACKING = frozenset(["tighter", "tight", "normal", "wide", "wider", "widest"])
RADIUS = frozenset(["", "none", "sm", "md", "lg", "xl", "2xl", "3xl", "full"])
SHADOW = frozenset(["", "sm", "md", "lg", "xl", "2xl", "inner", "none"])
BLUR = frozenset(["", "none", "sm", "md", "lg", "xl", "2xl", "3xl"])
BORDER_WIDTH = frozenset(["", "0", "2", "4", "8"])
MAX_WIDTH = frozenset(
    ["0", "none", "xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl", "5xl",
     "6xl", "7xl", "full", "min", "max", "fit", "prose",
     "screen-sm", "screen-md", "screen-lg", "screen-xl", "screen-2xl"]
)
DURATION = frozenset(["0", "75", "100", "150", "200", "300", "500", "700", "1000"])
EASING = frozenset(["linear", "in", "out", "in-out", "initial"])
OPACITY = frozenset([str(v) for v in range(0, 101, 5)])
GRID_COUNT = frozenset([str(v) for v in range(1, 13)] + ["none", "subgrid"])
Z_INDEX = frozenset(["0", "10", "20", "30", "40", "50", "auto"])
ANIMATION = frozenset(["none", "spin", "ping", "pulse", "bounce"])
SCALE_PCT = frozenset(["0", "50", "75", "90", "95", "100", "105", "110", "125", "150"])
ROTATE = frozenset(["0", "1", "2", "3", "6", "12", "45", "90", "180"])

TW_COLOR_FAMILIES = frozenset(
    ["slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber",
     "yellow", "lime", "green", "emerald", "teal", "cyan", "sky", "blue",
     "indigo", "violet", "purple", "fuchsia", "pink", "rose"]
)
TW_COLOR_KEYWORDS = frozenset(
    ["white", "black", "transparent", "current", "inherit", "none", "auto"]
)
_SHADE = re.compile(r"^(?:50|9[05]0|[1-8]00)$")

# Shipped palette values, spelled as hex. `background: #4f46e5` is `bg-indigo-600`
# written the long way, and until both landed on the same name a project scored
# a full decision per colour for using CSS instead of a utility.
#
# **Deliberately partial.** It covers the neutral ramps and the shades generated
# code actually reaches for; a colour outside it stays an authored literal. That
# is the safe direction — a miss under-credits the framework, while a wrong
# entry would accuse a project of using a value it did not.
STOCK_HEX: dict[str, str] = {}


def _ramp(family: str, **shades: str) -> None:
    for shade, hexval in shades.items():
        STOCK_HEX[hexval] = f"{family}-{shade[1:]}"


_ramp("slate", s50="#f8fafc", s100="#f1f5f9", s200="#e2e8f0", s300="#cbd5e1",
      s400="#94a3b8", s500="#64748b", s600="#475569", s700="#334155",
      s800="#1e293b", s900="#0f172a", s950="#020617")
_ramp("gray", s50="#f9fafb", s100="#f3f4f6", s200="#e5e7eb", s300="#d1d5db",
      s400="#9ca3af", s500="#6b7280", s600="#4b5563", s700="#374151",
      s800="#1f2937", s900="#111827", s950="#030712")
_ramp("zinc", s50="#fafafa", s100="#f4f4f5", s200="#e4e4e7", s300="#d4d4d8",
      s400="#a1a1aa", s500="#71717a", s600="#52525b", s700="#3f3f46",
      s800="#27272a", s900="#18181b", s950="#09090b")
_ramp("neutral", s100="#f5f5f5", s200="#e5e5e5", s300="#d4d4d4", s400="#a3a3a3",
      s500="#737373", s600="#525252", s700="#404040", s800="#262626",
      s900="#171717", s950="#0a0a0a")
_ramp("stone", s50="#fafaf9", s100="#f5f5f4", s200="#e7e5e4", s300="#d6d3d1",
      s400="#a8a29e", s500="#78716c", s600="#57534e", s700="#44403c",
      s800="#292524", s900="#1c1917", s950="#0c0a09")
_ramp("blue", s50="#eff6ff", s100="#dbeafe", s400="#60a5fa", s500="#3b82f6",
      s600="#2563eb", s700="#1d4ed8", s800="#1e40af", s900="#1e3a8a")
_ramp("indigo", s50="#eef2ff", s100="#e0e7ff", s400="#818cf8", s500="#6366f1",
      s600="#4f46e5", s700="#4338ca", s800="#3730a3", s900="#312e81")
_ramp("violet", s400="#a78bfa", s500="#8b5cf6", s600="#7c3aed", s700="#6d28d9")
_ramp("purple", s500="#a855f7", s600="#9333ea", s700="#7e22ce")
_ramp("sky", s500="#0ea5e9", s600="#0284c7")
_ramp("cyan", s500="#06b6d4")
_ramp("teal", s500="#14b8a6", s600="#0d9488")
_ramp("emerald", s500="#10b981", s600="#059669")
_ramp("green", s500="#22c55e", s600="#16a34a")
_ramp("lime", s500="#84cc16")
_ramp("yellow", s500="#eab308")
_ramp("amber", s500="#f59e0b", s600="#d97706")
_ramp("orange", s500="#f97316", s600="#ea580c")
_ramp("red", s50="#fef2f2", s100="#fee2e2", s400="#f87171", s500="#ef4444",
      s600="#dc2626", s700="#b91c1c")
_ramp("pink", s500="#ec4899", s600="#db2777")
_ramp("rose", s500="#f43f5e", s600="#e11d48")
_ramp("fuchsia", s500="#d946ef")
STOCK_HEX["#ffffff"] = "white"
STOCK_HEX["#fff"] = "white"
STOCK_HEX["#000000"] = "black"
STOCK_HEX["#000"] = "black"

# Utilities whose whole name is the value — no argument to classify.
STATIC: dict[str, tuple[Axis, str, str]] = {}


def _static(axis: Axis, prop: str, *names: str) -> None:
    for name in names:
        STATIC[name] = (axis, prop, name)


_static(Axis.LAYOUT, "display", "block", "inline-block", "inline", "flex",
        "inline-flex", "grid", "inline-grid", "table", "inline-table",
        "flow-root", "contents", "hidden", "list-item")
_static(Axis.LAYOUT, "position", "static", "fixed", "absolute", "relative", "sticky")
_static(Axis.LAYOUT, "text-align", "text-left", "text-center", "text-right",
        "text-justify", "text-start", "text-end")
_static(Axis.LAYOUT, "float", "float-right", "float-left", "float-none", "clear-both")
_static(Axis.LAYOUT, "container", "container")
_static(Axis.LAYOUT, "isolation", "isolate")
_static(Axis.LAYOUT, "flex-direction", "flex-row", "flex-row-reverse",
        "flex-col", "flex-col-reverse")
_static(Axis.LAYOUT, "flex-wrap", "flex-wrap", "flex-wrap-reverse", "flex-nowrap")
_static(Axis.LAYOUT, "grid-flow", "grid-flow-row", "grid-flow-col",
        "grid-flow-dense", "grid-flow-row-dense", "grid-flow-col-dense")
_static(Axis.TYPE, "font-style", "italic", "not-italic")
_static(Axis.TYPE, "text-transform", "uppercase", "lowercase", "capitalize",
        "normal-case")
_static(Axis.TYPE, "text-decoration", "underline", "overline", "line-through",
        "no-underline")
_static(Axis.TYPE, "text-overflow", "truncate", "text-ellipsis", "text-clip")
_static(Axis.TYPE, "text-wrap", "text-wrap", "text-nowrap", "text-balance",
        "text-pretty")
_static(Axis.TYPE, "font-smoothing", "antialiased", "subpixel-antialiased")
_static(Axis.TYPE, "font-variant-numeric", "ordinal", "slashed-zero",
        "lining-nums", "oldstyle-nums", "proportional-nums", "tabular-nums",
        "diagonal-fractions", "stacked-fractions")
_static(Axis.MATERIAL, "background-clip", "bg-clip-text", "bg-clip-border",
        "bg-clip-padding", "bg-clip-content")
_static(Axis.MATERIAL, "background-size", "bg-cover", "bg-contain", "bg-auto")
_static(Axis.MATERIAL, "background-repeat", "bg-repeat", "bg-no-repeat",
        "bg-repeat-x", "bg-repeat-y")
_static(Axis.MATERIAL, "background-attachment", "bg-fixed", "bg-local", "bg-scroll")
_static(Axis.SHAPE, "border-style", "border-solid", "border-dashed",
        "border-dotted", "border-double", "border-hidden", "border-none")
_static(Axis.SHAPE, "outline-style", "outline-none", "outline-dashed",
        "outline-dotted", "outline-double")
_static(Axis.MOTION, "transform", "transform", "transform-gpu", "transform-none")
_static(Axis.MOTION, "transition", "transition", "transition-all",
        "transition-none", "transition-colors", "transition-opacity",
        "transition-shadow", "transition-transform")
_static(Axis.COLOR, "color", "text-transparent", "text-current", "text-inherit")

# ------------------------------------------------------------------ prefix table
# (prefix, axis, prop, scale) — longest prefix wins. ``scale`` names the default
# set the value is checked against; ``None`` means "any value is authored".
_PREFIXES: list[tuple[str, Axis, str, frozenset | None]] = [
    # spacing — the rhythm axis
    ("p-", Axis.SPACE, "padding", SPACING),
    ("px-", Axis.SPACE, "padding-x", SPACING),
    ("py-", Axis.SPACE, "padding-y", SPACING),
    ("pt-", Axis.SPACE, "padding-top", SPACING),
    ("pr-", Axis.SPACE, "padding-right", SPACING),
    ("pb-", Axis.SPACE, "padding-bottom", SPACING),
    ("pl-", Axis.SPACE, "padding-left", SPACING),
    ("ps-", Axis.SPACE, "padding-start", SPACING),
    ("pe-", Axis.SPACE, "padding-end", SPACING),
    ("m-", Axis.SPACE, "margin", SPACING),
    ("mx-", Axis.SPACE, "margin-x", SPACING),
    ("my-", Axis.SPACE, "margin-y", SPACING),
    ("mt-", Axis.SPACE, "margin-top", SPACING),
    ("mr-", Axis.SPACE, "margin-right", SPACING),
    ("mb-", Axis.SPACE, "margin-bottom", SPACING),
    ("ml-", Axis.SPACE, "margin-left", SPACING),
    ("gap-x-", Axis.SPACE, "gap-x", SPACING),
    ("gap-y-", Axis.SPACE, "gap-y", SPACING),
    ("gap-", Axis.SPACE, "gap", SPACING),
    ("space-x-", Axis.SPACE, "space-x", SPACING),
    ("space-y-", Axis.SPACE, "space-y", SPACING),
    # typography
    ("leading-", Axis.TYPE, "line-height", LEADING),
    ("tracking-", Axis.TYPE, "letter-spacing", TRACKING),
    ("line-clamp-", Axis.TYPE, "line-clamp", None),
    ("indent-", Axis.TYPE, "text-indent", SPACING),
    ("align-", Axis.TYPE, "vertical-align", None),
    ("underline-offset-", Axis.TYPE, "underline-offset", None),
    ("decoration-", Axis.TYPE, "text-decoration-style", None),
    # shape
    ("rounded-", Axis.SHAPE, "radius", RADIUS),
    ("border-", Axis.SHAPE, "border", BORDER_WIDTH),
    ("divide-", Axis.SHAPE, "divide", BORDER_WIDTH),
    ("outline-offset-", Axis.SHAPE, "outline-offset", None),
    ("outline-", Axis.SHAPE, "outline-width", BORDER_WIDTH),
    ("ring-offset-", Axis.SHAPE, "ring-offset", None),
    ("ring-", Axis.SHAPE, "ring", BORDER_WIDTH),
    # material / depth
    ("shadow-", Axis.MATERIAL, "shadow", SHADOW),
    ("drop-shadow-", Axis.MATERIAL, "drop-shadow", SHADOW),
    ("opacity-", Axis.MATERIAL, "opacity", OPACITY),
    ("backdrop-blur-", Axis.MATERIAL, "backdrop-blur", BLUR),
    ("backdrop-", Axis.MATERIAL, "backdrop-filter", None),
    ("blur-", Axis.MATERIAL, "blur", BLUR),
    ("brightness-", Axis.MATERIAL, "brightness", None),
    ("contrast-", Axis.MATERIAL, "contrast", None),
    ("saturate-", Axis.MATERIAL, "saturate", None),
    ("mix-blend-", Axis.MATERIAL, "mix-blend", None),
    ("bg-blend-", Axis.MATERIAL, "bg-blend", None),
    ("bg-gradient-", Axis.MATERIAL, "gradient-direction", None),
    ("bg-linear-", Axis.MATERIAL, "gradient-direction", None),
    ("bg-radial", Axis.MATERIAL, "gradient-direction", None),
    ("bg-conic", Axis.MATERIAL, "gradient-direction", None),
    # motion
    ("duration-", Axis.MOTION, "duration", DURATION),
    ("delay-", Axis.MOTION, "delay", DURATION),
    ("ease-", Axis.MOTION, "easing", EASING),
    ("animate-", Axis.MOTION, "animation", ANIMATION),
    ("scale-x-", Axis.MOTION, "scale-x", SCALE_PCT),
    ("scale-y-", Axis.MOTION, "scale-y", SCALE_PCT),
    ("scale-", Axis.MOTION, "scale", SCALE_PCT),
    ("rotate-", Axis.MOTION, "rotate", ROTATE),
    ("translate-x-", Axis.MOTION, "translate-x", SPACING),
    ("translate-y-", Axis.MOTION, "translate-y", SPACING),
    ("skew-x-", Axis.MOTION, "skew-x", ROTATE),
    ("skew-y-", Axis.MOTION, "skew-y", ROTATE),
    ("origin-", Axis.MOTION, "transform-origin", None),
    ("will-change-", Axis.MOTION, "will-change", None),
    # layout
    ("grid-cols-", Axis.LAYOUT, "grid-cols", GRID_COUNT),
    ("grid-rows-", Axis.LAYOUT, "grid-rows", GRID_COUNT),
    ("col-span-", Axis.LAYOUT, "col-span", GRID_COUNT),
    ("row-span-", Axis.LAYOUT, "row-span", GRID_COUNT),
    ("col-start-", Axis.LAYOUT, "col-start", GRID_COUNT),
    ("col-end-", Axis.LAYOUT, "col-end", GRID_COUNT),
    ("auto-cols-", Axis.LAYOUT, "auto-cols", None),
    ("auto-rows-", Axis.LAYOUT, "auto-rows", None),
    ("items-", Axis.LAYOUT, "align-items", None),
    ("justify-items-", Axis.LAYOUT, "justify-items", None),
    ("justify-self-", Axis.LAYOUT, "justify-self", None),
    ("justify-", Axis.LAYOUT, "justify-content", None),
    ("content-", Axis.LAYOUT, "align-content", None),
    ("self-", Axis.LAYOUT, "align-self", None),
    ("place-", Axis.LAYOUT, "place", None),
    ("order-", Axis.LAYOUT, "order", None),
    ("basis-", Axis.LAYOUT, "flex-basis", SPACING),
    ("grow-", Axis.LAYOUT, "flex-grow", frozenset(["0", "1"])),
    ("shrink-", Axis.LAYOUT, "flex-shrink", frozenset(["0", "1"])),
    ("flex-", Axis.LAYOUT, "flex", None),
    ("max-w-", Axis.LAYOUT, "max-width", MAX_WIDTH),
    ("max-h-", Axis.LAYOUT, "max-height", SPACING | SIZE_KEYWORDS),
    ("min-w-", Axis.LAYOUT, "min-width", SPACING | SIZE_KEYWORDS),
    ("min-h-", Axis.LAYOUT, "min-height", SPACING | SIZE_KEYWORDS),
    ("w-", Axis.LAYOUT, "width", SPACING | SIZE_KEYWORDS),
    ("h-", Axis.LAYOUT, "height", SPACING | SIZE_KEYWORDS),
    ("size-", Axis.LAYOUT, "size", SPACING | SIZE_KEYWORDS),
    ("aspect-", Axis.LAYOUT, "aspect", None),
    ("columns-", Axis.LAYOUT, "columns", None),
    ("overflow-", Axis.LAYOUT, "overflow", None),
    ("object-", Axis.LAYOUT, "object", None),
    ("inset-", Axis.LAYOUT, "inset", SPACING),
    ("top-", Axis.LAYOUT, "top", SPACING),
    ("right-", Axis.LAYOUT, "right", SPACING),
    ("bottom-", Axis.LAYOUT, "bottom", SPACING),
    ("left-", Axis.LAYOUT, "left", SPACING),
    ("z-", Axis.LAYOUT, "z-index", Z_INDEX),
]
# Corner-scoped radii (`rounded-t-lg`, `rounded-tl-3xl`). Registered as their
# own prefixes so the corner selector is part of the property name and the
# scale check still sees a bare `lg` — otherwise the value reads as `t-lg`,
# which is in no default table and would be credited as a project token.
for _c in ("t", "r", "b", "l", "s", "e", "tl", "tr", "br", "bl", "ss", "se", "ee", "es"):
    _PREFIXES.append((f"rounded-{_c}-", Axis.SHAPE, f"radius-{_c}", RADIUS))
_PREFIXES.sort(key=lambda t: -len(t[0]))

# Color-bearing prefixes, resolved separately because their value decides the
# axis: `border-2` is shape, `border-slate-200` is color, from the same prefix.
_COLOR_PREFIXES: dict[str, str] = {
    "bg-": "background",
    "text-": "color",
    "border-": "border-color",
    "border-t-": "border-color",
    "border-r-": "border-color",
    "border-b-": "border-color",
    "border-l-": "border-color",
    "border-x-": "border-color",
    "border-y-": "border-color",
    "divide-": "divide-color",
    "ring-": "ring-color",
    "ring-offset-": "ring-offset-color",
    "outline-": "outline-color",
    "shadow-": "shadow-color",
    "from-": "gradient-from",
    "via-": "gradient-via",
    "to-": "gradient-to",
    "fill-": "fill",
    "stroke-": "stroke",
    "accent-": "accent-color",
    "caret-": "caret-color",
    "placeholder-": "placeholder-color",
    "decoration-": "decoration-color",
}
_SIDE_WIDTH = {
    "border-t-": "border-top", "border-r-": "border-right",
    "border-b-": "border-bottom", "border-l-": "border-left",
    "border-x-": "border-x", "border-y-": "border-y",
}

# Bare utilities that carry the scale's DEFAULT value (``rounded`` is
# ``rounded-DEFAULT``). Without these the most common radius/border/shadow
# classes in every real codebase would decode to nothing.
BARE: dict[str, tuple[Axis, str]] = {
    "rounded": (Axis.SHAPE, "radius"),
    "border": (Axis.SHAPE, "border"),
    "divide-x": (Axis.SHAPE, "divide-x"),
    "divide-y": (Axis.SHAPE, "divide-y"),
    "outline": (Axis.SHAPE, "outline-width"),
    "ring": (Axis.SHAPE, "ring"),
    "shadow": (Axis.MATERIAL, "shadow"),
    "drop-shadow": (Axis.MATERIAL, "drop-shadow"),
    "blur": (Axis.MATERIAL, "blur"),
    "backdrop-blur": (Axis.MATERIAL, "backdrop-blur"),
    "grayscale": (Axis.MATERIAL, "grayscale"),
    "invert": (Axis.MATERIAL, "invert"),
    "grow": (Axis.LAYOUT, "flex-grow"),
    "shrink": (Axis.LAYOUT, "flex-shrink"),
    "underline": (Axis.TYPE, "text-decoration"),
}
# Side/corner selectors are part of the utility *name*, not its value. Without
# these, `border-b` decoded as border-width "b" — an unrecognised value, and so
# a project TOKEN, which credited every page that draws a hairline with having
# built a design system.
for _side in ("t", "r", "b", "l", "x", "y", "s", "e"):
    BARE[f"border-{_side}"] = (Axis.SHAPE, f"border-{_side}")
for _corner in ("t", "r", "b", "l", "s", "e", "tl", "tr", "br", "bl", "ss", "se", "ee", "es"):
    BARE[f"rounded-{_corner}"] = (Axis.SHAPE, f"radius-{_corner}")

_ARBITRARY = re.compile(r"^\[(.*)\]$", re.S)
_CSS_VAR = re.compile(r"^\((?:[a-z]+:)?--[\w-]+\)$")
_LENGTH = re.compile(r"^-?\d*\.?\d+(?:px|rem|em|%|vh|vw|ch|ex|pt|svh|dvh|lvh)?$")


def split_variants(cls: str) -> tuple[list[str], str]:
    """``("md:hover:px-4")`` → ``(["md", "hover"], "px-4")``.

    Splits on ``:`` only at bracket depth 0 so ``lg:[&>*]:mt-4`` and
    ``bg-[url(a:b)]`` survive intact.
    """
    parts: list[str] = []
    depth = 0
    last = 0
    for i, ch in enumerate(cls):
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        elif ch == ":" and depth == 0:
            parts.append(cls[last:i])
            last = i + 1
    return parts, cls[last:]


def is_color_value(value: str) -> bool:
    """True when ``value`` reads as a color rather than a size/width."""
    if value in TW_COLOR_KEYWORDS:
        return True
    if "/" in value:                      # bg-white/10, text-slate-900/60
        value = value.split("/", 1)[0]
    if value in TW_COLOR_KEYWORDS:
        return True
    m = _ARBITRARY.match(value)
    if m:
        inner = m.group(1).lower()
        return inner.startswith(("#", "rgb", "hsl", "oklch", "lab", "color(",
                                 "var(")) or inner in TW_COLOR_KEYWORDS
    family, _, shade = value.rpartition("-")
    if family and _SHADE.match(shade):
        return True
    return False


def _origin(value: str, scale: frozenset | None) -> Origin:
    """Classify a decoded value — the decision/default split."""
    if _ARBITRARY.match(value) or _CSS_VAR.match(value):
        return Origin.ARBITRARY
    base = value.split("/", 1)[0]
    if scale is not None and base in scale:
        return Origin.DEFAULT
    if scale is not None and FRACTIONS.match(base):
        return Origin.DEFAULT
    if scale is None:
        # No table to check against (``justify-``, ``object-``): treat the
        # shipped keyword vocabulary as default. Anything else is authored.
        return Origin.DEFAULT if base.replace("-", "").isalpha() else Origin.ARBITRARY
    return Origin.TOKEN


def _color_origin(value: str) -> Origin:
    if _ARBITRARY.match(value) or _CSS_VAR.match(value):
        return Origin.ARBITRARY
    base = value.split("/", 1)[0]
    if base in TW_COLOR_KEYWORDS:
        return Origin.DEFAULT
    family, _, shade = base.rpartition("-")
    if family in TW_COLOR_FAMILIES and _SHADE.match(shade):
        return Origin.DEFAULT
    return Origin.TOKEN


def _decode_text(value: str) -> tuple[Axis, str, frozenset | None] | None:
    """``text-*`` is three utilities wearing one prefix — pick the right one."""
    if value in FONT_SIZE:
        return Axis.TYPE, "font-size", FONT_SIZE
    m = _ARBITRARY.match(value)
    if m and _LENGTH.match(m.group(1).strip()):
        return Axis.TYPE, "font-size", FONT_SIZE
    if is_color_value(value):
        return Axis.COLOR, "color", None
    if _CSS_VAR.match(value):
        return Axis.COLOR, "color", None
    # A bare custom name (``text-display``, ``text-ink``) is far more often a
    # colour token than a size token in real themes; call it colour and say so.
    return Axis.COLOR, "color", None


# A real project draws thousands of class *uses* from a few hundred distinct
# class *names*, and decoding is pure: same string, same Decl, and `Decl` is
# frozen so the shared instance cannot be mutated by a caller. Caching it turns
# the hottest loop in the parser into a dict lookup.
@lru_cache(maxsize=16384)
def _decode(cls: str) -> Decl | None:
    """Decode against Tailwind's *shipped* scales, with no project config."""
    if not cls or cls.startswith(("--", "@")):
        return None
    variants, util = split_variants(cls)
    variant = ":".join(variants)
    util = util.lstrip("!")
    negative = util.startswith("-")
    if negative:
        util = util[1:]
    if not util:
        return None

    hit = STATIC.get(util)
    if hit is not None:
        axis, prop, value = hit
        return Decl(axis=axis, prop=prop, value=value, origin=Origin.DEFAULT,
                    variant=variant, raw=cls)

    bare = BARE.get(util)
    if bare is not None:
        return Decl(bare[0], bare[1], "", Origin.DEFAULT, variant, cls)

    if util.startswith("text-"):
        value = util[5:]
        picked = _decode_text(value)
        if picked is not None:
            axis, prop, scale = picked
            origin = _color_origin(value) if axis is Axis.COLOR else _origin(value, scale)
            return Decl(axis=axis, prop=prop, value=value, origin=origin,
                        variant=variant, raw=cls)

    if util.startswith("font-"):
        value = util[5:]
        if value in FONT_WEIGHT:
            return Decl(Axis.TYPE, "font-weight", value, Origin.DEFAULT, variant, cls)
        if value in FONT_FAMILY:
            return Decl(Axis.TYPE, "font-family", value, Origin.DEFAULT, variant, cls)
        return Decl(Axis.TYPE, "font-family", value, _origin(value, frozenset()),
                    variant, cls)

    # Two prefix tables overlap: `border-2` is shape, `border-slate-200` is
    # colour, and `bg-gradient-to-r` is material while `bg-surface` is colour.
    # Longest prefix wins first (so `bg-gradient-` beats `bg-`); only when both
    # tables match at the *same* length does the value decide.
    scale_hit = next(
        ((p, a, pr, sc) for p, a, pr, sc in _PREFIXES if util.startswith(p)),
        None,
    )
    color_hit = next(
        ((p, pr) for p, pr in sorted(_COLOR_PREFIXES.items(), key=lambda kv: -len(kv[0]))
         if util.startswith(p) and len(util) > len(p)),
        None,
    )
    if scale_hit and color_hit and len(color_hit[0]) > len(scale_hit[0]):
        scale_hit = None
    if scale_hit and color_hit and len(scale_hit[0]) > len(color_hit[0]):
        color_hit = None

    if color_hit is not None:
        pref, prop = color_hit
        value = util[len(pref):]
        if is_color_value(value) or _CSS_VAR.match(value):
            return Decl(Axis.COLOR, prop, value, _color_origin(value), variant, cls)
        if pref in _SIDE_WIDTH:
            # `border-t-2` is a width on one side, not a colour. Checked before
            # the token fallback below, which would otherwise read the width as
            # a project colour name.
            return Decl(Axis.SHAPE, _SIDE_WIDTH[pref], value,
                        _origin(value, BORDER_WIDTH), variant, cls)
        if scale_hit is None and not _ARBITRARY.match(value):
            # A bare custom name on a colour-only prefix (`bg-surface`,
            # `fill-brand`) is a theme colour token — the strongest signal the
            # engine reads. Sending it to background-image instead would erase
            # exactly the projects that built a palette.
            return Decl(Axis.COLOR, prop, value, Origin.TOKEN, variant, cls)

    if scale_hit is not None:
        pref, axis, prop, scale = scale_hit
        value = util[len(pref):]
        if not value:
            return Decl(axis, prop, "", Origin.DEFAULT, variant, cls)
        return Decl(axis, prop, ("-" if negative else "") + value,
                    _origin(value, scale), variant, cls)

    # Bare side-borders (`border-t`) and bare radius corners (`rounded-l`).
    if util in {"border-t", "border-r", "border-b", "border-l", "border-x", "border-y"}:
        return Decl(Axis.SHAPE, util, "", Origin.DEFAULT, variant, cls)
    if util.startswith("bg-"):
        # Whatever is left after colour and the gradient/size/repeat statics is
        # a background *image* — `bg-[url(...)]`, `bg-hero`.
        value = util[3:]
        return Decl(Axis.MATERIAL, "background-image", value,
                    _origin(value, frozenset()), variant, cls)
    return None


def _shipped(d: Decl | None) -> Decl | None:
    """Normalise an escape-hatch value that lands exactly on a shipped step.

    ``py-[2.5rem]`` is ``py-10``. :mod:`.css` has always converted the raw-CSS
    spelling of a shipped value to its key and its ``DEFAULT`` origin — "only
    exact matches convert" — and the utility spelling was never put through the
    same table, so the *same* value read as a default in a stylesheet and as a
    decision in a class list. The clean-side twin pair is what caught it: the
    two halves of one design were 8 points apart, all of it here.

    What survives is what the escape hatch is actually for. ``text-[2.75rem]``
    is a value someone measured against the screen because no shipped step
    fits, and it stays ``ARBITRARY``; ``gap-[3.5rem]`` is ``gap-14`` written
    the long way, and it is not a decision in either dialect.

    Uses the same :func:`.css.stock_key` as the stylesheet path — a second copy
    of that table would drift, and then the asymmetry would come back somewhere
    else. Imported lazily because :mod:`.css` reads ``STOCK_HEX`` from here.
    """
    if d is None or d.origin is not Origin.ARBITRARY:
        return d
    m = _ARBITRARY.match(d.value)
    if m is None:
        return d                      # `bg-(--brand)`: a var, not a length
    from .css import stock_key

    key = stock_key(d.axis, d.prop, m.group(1).replace("_", " "))
    if key is None:
        return d
    return replace(d, value=key, origin=Origin.DEFAULT)


@lru_cache(maxsize=16384)
def decode_class(cls: str, theme: ThemeIndex | None = None) -> Decl | None:
    """One Tailwind class → one :class:`Decl`, or ``None`` if unrecognized.

    ``theme`` is the project's own config (see :mod:`.theme`). A value that
    Tailwind ships *and* the project redefined is a decision, not a default:
    ``text-lg`` in a project that wrote its own ``fontSize.lg`` is a step in
    that project's scale. Only the redefined key moves — ``text-4xl`` beside it
    stays a default — so the credit is exactly as wide as the config is.

    Cached on ``(cls, theme)`` rather than on ``cls`` alone: the mapping is no
    longer a property of the string, and a project-blind cache would hand one
    project's decisions to the next one scanned in the same process.
    """
    d = _shipped(_decode(cls))
    if d is None or not theme:
        return d
    if d.axis is Axis.COLOR and d.prop == "color" and d.origin is Origin.TOKEN:
        # `text-display` is a colour token *unless* the project declared a font
        # size by that name — the one case where the config resolves the
        # ambiguity `_decode_text` has to guess at.
        if theme.redefines(Axis.TYPE, "font-size", d.value):
            return Decl(Axis.TYPE, "font-size", d.value, Origin.TOKEN,
                        d.variant, d.raw)
        return d
    if d.origin is Origin.DEFAULT and theme.redefines(d.axis, d.prop, d.value):
        return replace(d, origin=Origin.TOKEN)
    return d


def decode_classes(classes: list[str],
                   theme: ThemeIndex | None = None) -> list[Decl]:
    """Decode a class list, dropping what we cannot classify."""
    out: list[Decl] = []
    for cls in classes:
        d = decode_class(cls, theme)
        if d is not None:
            out.append(d)
    return out
