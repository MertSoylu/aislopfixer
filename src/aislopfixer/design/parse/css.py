"""Stylesheet scanner: CSS text → rules, custom properties, and declarations.

A project that writes real CSS is doing design work the Tailwind decoder would
never see, so every raw declaration is normalized onto the same axes and props
as a utility class. ``padding: 5rem 0`` and ``py-20`` both land on
``space/padding-y`` — otherwise a hand-written stylesheet would score as
"no decisions" purely because it did not use utilities.

Origin here is :class:`~aislopfixer.design.models.Origin.LITERAL` (an authored
value) unless the value reads a custom property, which makes it ``TOKEN`` — the
same distinction the class decoder draws between ``py-[68px]`` and ``py-band``.

Tolerant by construction: unbalanced braces, unknown at-rules and CSS-in-JS
fragments must degrade to fewer rules, never to an exception.
"""

from __future__ import annotations

import re

from ..models import Axis, CssRule, Decl, Origin
from .classes import STOCK_HEX

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_VAR_REF = re.compile(r"var\(\s*--[\w-]+")
_CUSTOM_PROP = re.compile(r"(--[\w-]+)\s*:\s*([^;}]+)")

# CSS property → axis + normalized prop. Shorthands that carry several axes at
# once (``border``, ``font``, ``background``) are expanded below.
_PROP_MAP: dict[str, tuple[Axis, str]] = {
    "padding": (Axis.SPACE, "padding"),
    "padding-top": (Axis.SPACE, "padding-top"),
    "padding-right": (Axis.SPACE, "padding-right"),
    "padding-bottom": (Axis.SPACE, "padding-bottom"),
    "padding-left": (Axis.SPACE, "padding-left"),
    "padding-block": (Axis.SPACE, "padding-y"),
    "padding-inline": (Axis.SPACE, "padding-x"),
    "margin": (Axis.SPACE, "margin"),
    "margin-top": (Axis.SPACE, "margin-top"),
    "margin-right": (Axis.SPACE, "margin-right"),
    "margin-bottom": (Axis.SPACE, "margin-bottom"),
    "margin-left": (Axis.SPACE, "margin-left"),
    "margin-block": (Axis.SPACE, "margin-y"),
    "margin-inline": (Axis.SPACE, "margin-x"),
    "gap": (Axis.SPACE, "gap"),
    "row-gap": (Axis.SPACE, "gap-y"),
    "column-gap": (Axis.SPACE, "gap-x"),

    "font-size": (Axis.TYPE, "font-size"),
    "font-weight": (Axis.TYPE, "font-weight"),
    "font-family": (Axis.TYPE, "font-family"),
    "line-height": (Axis.TYPE, "line-height"),
    "letter-spacing": (Axis.TYPE, "letter-spacing"),
    "text-transform": (Axis.TYPE, "text-transform"),
    "text-decoration": (Axis.TYPE, "text-decoration"),
    "font-variant-numeric": (Axis.TYPE, "font-variant-numeric"),
    "font-feature-settings": (Axis.TYPE, "font-features"),
    "font-optical-sizing": (Axis.TYPE, "optical-sizing"),
    "text-wrap": (Axis.TYPE, "text-wrap"),
    "hyphens": (Axis.TYPE, "hyphens"),

    "color": (Axis.COLOR, "color"),
    "background-color": (Axis.COLOR, "background"),
    "border-color": (Axis.COLOR, "border-color"),
    "outline-color": (Axis.COLOR, "outline-color"),
    "fill": (Axis.COLOR, "fill"),
    "stroke": (Axis.COLOR, "stroke"),
    "accent-color": (Axis.COLOR, "accent-color"),
    "caret-color": (Axis.COLOR, "caret-color"),

    "border-radius": (Axis.SHAPE, "radius"),
    "border-width": (Axis.SHAPE, "border"),
    "border-style": (Axis.SHAPE, "border-style"),
    "border-top": (Axis.SHAPE, "border-top"),
    "border-bottom": (Axis.SHAPE, "border-bottom"),
    # The logical spellings, which are also where `_AXIS_PAIRS` folds a
    # symmetric longhand pair to — `border-y` is what the utility says.
    "border-block": (Axis.SHAPE, "border-y"),
    "border-inline": (Axis.SHAPE, "border-x"),
    "border-block-width": (Axis.SHAPE, "border-y"),
    "border-inline-width": (Axis.SHAPE, "border-x"),
    "outline-width": (Axis.SHAPE, "outline-width"),
    "outline-offset": (Axis.SHAPE, "outline-offset"),

    "box-shadow": (Axis.MATERIAL, "shadow"),
    "opacity": (Axis.MATERIAL, "opacity"),
    "filter": (Axis.MATERIAL, "filter"),
    "backdrop-filter": (Axis.MATERIAL, "backdrop-filter"),
    "mix-blend-mode": (Axis.MATERIAL, "mix-blend"),
    "background-image": (Axis.MATERIAL, "background-image"),
    "background-blend-mode": (Axis.MATERIAL, "bg-blend"),

    "display": (Axis.LAYOUT, "display"),
    "position": (Axis.LAYOUT, "position"),
    "grid-template-columns": (Axis.LAYOUT, "grid-cols"),
    "grid-template-rows": (Axis.LAYOUT, "grid-rows"),
    "grid-column": (Axis.LAYOUT, "col-span"),
    "grid-area": (Axis.LAYOUT, "grid-area"),
    "flex-direction": (Axis.LAYOUT, "flex-direction"),
    "flex-wrap": (Axis.LAYOUT, "flex-wrap"),
    "align-items": (Axis.LAYOUT, "align-items"),
    "justify-content": (Axis.LAYOUT, "justify-content"),
    "align-self": (Axis.LAYOUT, "align-self"),
    "place-items": (Axis.LAYOUT, "place"),
    "text-align": (Axis.LAYOUT, "text-align"),
    "width": (Axis.LAYOUT, "width"),
    "max-width": (Axis.LAYOUT, "max-width"),
    "min-width": (Axis.LAYOUT, "min-width"),
    "height": (Axis.LAYOUT, "height"),
    "min-height": (Axis.LAYOUT, "min-height"),
    "aspect-ratio": (Axis.LAYOUT, "aspect"),
    "z-index": (Axis.LAYOUT, "z-index"),
    "overflow": (Axis.LAYOUT, "overflow"),
    "columns": (Axis.LAYOUT, "columns"),

    "transition": (Axis.MOTION, "transition"),
    "transition-duration": (Axis.MOTION, "duration"),
    "transition-timing-function": (Axis.MOTION, "easing"),
    "transition-delay": (Axis.MOTION, "delay"),
    "animation": (Axis.MOTION, "animation"),
    "animation-duration": (Axis.MOTION, "duration"),
    "transform": (Axis.MOTION, "transform"),
    "transform-origin": (Axis.MOTION, "transform-origin"),
    "will-change": (Axis.MOTION, "will-change"),
    "scroll-behavior": (Axis.MOTION, "scroll-behavior"),
}

# Shorthands that must fan out so the axes stay honest: ``border: 1px solid
# #e5e7eb`` is a shape decision *and* a colour decision.
_SHORTHAND_FANOUT = {
    "border": ((Axis.SHAPE, "border"), (Axis.COLOR, "border-color")),
    "background": ((Axis.COLOR, "background"), (Axis.MATERIAL, "background-image")),
    "font": ((Axis.TYPE, "font-size"), (Axis.TYPE, "font-family")),
}

_COLOR_TOKEN = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color-mix)\("
)

# ------------------------------------------------- shipped values, spelled out
# The reverse of the utility scales in :mod:`.classes`. A raw CSS value that
# lands exactly on one of Tailwind's shipped steps is the framework's choice
# however it is written, so it decodes to the same key and the same
# ``DEFAULT`` origin. Only *exact* matches convert: 1200px is not 80rem, and a
# project that typed it gets the credit for having typed it.
_LEN = re.compile(r"^(-?\d*\.?\d+)(px|rem|em|%|ms|s)?$")


def _px(value: str) -> float | None:
    """A length in px, or ``None`` when the value is not a plain length."""
    m = _LEN.match(value.strip())
    if m is None:
        return None
    n = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("px", ""):
        return n
    if unit == "rem" or unit == "em":
        return n * 16.0
    return None


def _ms(value: str) -> float | None:
    m = _LEN.match(value.strip())
    if m is None:
        return None
    n, unit = float(m.group(1)), m.group(2) or ""
    if unit == "ms":
        return n
    if unit == "s":
        return n * 1000.0
    return None


# px → key, for the scales whose steps are a fixed table rather than a formula.
_FONT_SIZE_PX = {12: "xs", 14: "sm", 16: "base", 18: "lg", 20: "xl", 24: "2xl",
                 30: "3xl", 36: "4xl", 48: "5xl", 60: "6xl", 72: "7xl",
                 96: "8xl", 128: "9xl"}
_RADIUS_PX = {0: "none", 2: "sm", 4: "", 6: "md", 8: "lg", 12: "xl", 16: "2xl",
              24: "3xl"}
_BORDER_PX = {0: "0", 1: "", 2: "2", 4: "4", 8: "8"}
_MAX_WIDTH_PX = {384: "sm", 448: "md", 512: "lg", 576: "xl", 672: "2xl",
                 768: "3xl", 896: "4xl", 1024: "5xl", 1152: "6xl", 1280: "7xl",
                 320: "xs"}
_WEIGHT = {"100": "thin", "200": "extralight", "300": "light", "400": "normal",
           "500": "medium", "600": "semibold", "700": "bold",
           "800": "extrabold", "900": "black"}
_LEADING = {"1": "none", "1.25": "tight", "1.375": "snug", "1.5": "normal",
            "1.625": "relaxed", "2": "loose"}
_TRACKING = {"-0.05em": "tighter", "-0.025em": "tight", "0": "normal",
             "0em": "normal", "0.025em": "wide", "0.05em": "wider",
             "0.1em": "widest"}
_DURATIONS = frozenset({0, 75, 100, 150, 200, 300, 500, 700, 1000})
_SPACING_KEYS = frozenset(
    ["0", "0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "5", "6", "7", "8",
     "9", "10", "11", "12", "14", "16", "20", "24", "28", "32", "36", "40",
     "44", "48", "52", "56", "60", "64", "72", "80", "96"]
)
# Props whose values live on the spacing scale (one step = 0.25rem = 4px).
_SPACING_PROPS = frozenset(
    ["padding", "padding-x", "padding-y", "padding-top", "padding-right",
     "padding-bottom", "padding-left", "margin", "margin-x", "margin-y",
     "margin-top", "margin-right", "margin-bottom", "margin-left",
     "gap", "gap-x", "gap-y"]
)
_ALIGN = {"left": "text-left", "center": "text-center", "right": "text-right",
          "justify": "text-justify", "start": "text-start", "end": "text-end"}
_SIZE_KEYWORD = {"100vw": "screen", "100vh": "screen", "100%": "full",
                 "auto": "auto", "fit-content": "fit", "min-content": "min",
                 "max-content": "max"}
_TRACKS = re.compile(r"^repeat\(\s*(\d{1,2})\s*,\s*(?:minmax\([^)]*\)|[^,)]+)\)$")
# Properties whose whole vocabulary is CSS keywords. There is no authored
# alternative to ``display: flex``, so the keyword is the framework's choice
# however it is spelled — the same reading `classes._origin` gives `justify-`
# and `object-`, which have no scale to check against either.
_KEYWORD_PROPS = frozenset({
    "display", "position", "flex-direction", "flex-wrap", "justify-content",
    "align-items", "align-content", "align-self", "justify-items",
    "text-transform", "text-decoration", "font-style", "white-space",
    "overflow", "overflow-x", "overflow-y", "object-fit", "border-style",
    "cursor", "visibility", "text-overflow", "list-style-type", "float",
    "flex-shrink", "flex-grow", "box-sizing", "vertical-align",
    # `transition: all` and `ease` are keywords too; a curve someone typed
    # (`cubic-bezier(…)`) is not bare and stays authored.
    "transition", "easing", "scroll-behavior", "will-change",
})
_BARE_KEYWORD = re.compile(r"^[a-z]+(?:-[a-z]+)*$")


def _spacing_key(px: float) -> str | None:
    step = px / 4.0
    if px == 1:
        return "px"
    if abs(step - round(step, 1)) > 1e-6:
        return None
    key = f"{step:g}"
    return key if key in _SPACING_KEYS else None


def stock_key(axis: Axis, prop: str, value: str) -> str | None:
    """The utility key a raw CSS value equals, or ``None`` if it equals none."""
    low = value.strip().lower()
    if prop in _SPACING_PROPS:
        if low == "auto":
            return "auto"
        px = _px(low)
        return None if px is None or px < 0 else _spacing_key(px)
    if prop == "font-size":
        px = _px(low)
        return _FONT_SIZE_PX.get(int(px)) if px is not None and px == int(px) else None
    if prop == "font-weight":
        return _WEIGHT.get(low)
    if prop == "line-height":
        return _LEADING.get(low)
    if prop == "letter-spacing":
        return _TRACKING.get(low)
    if prop.startswith("radius"):
        if low in ("9999px", "50%"):
            return "full"
        px = _px(low)
        return _RADIUS_PX.get(int(px)) if px is not None and px == int(px) else None
    if prop.startswith("border") and prop not in ("border-style", "border-color"):
        # ``border: 1px solid #e5e7eb`` is a width, a style and a colour. The
        # colour is split off by the fan-out and the style is a keyword; what is
        # left for the shape axis is the length in it. Reading the whole
        # shorthand matched no shipped width, so every CSS page that draws a
        # hairline was credited with having chosen one.
        px = _px(low)
        if px is None:
            px = next((p for p in (_px(part) for part in low.split())
                       if p is not None), None)
        return _BORDER_PX.get(int(px)) if px is not None and px == int(px) else None
    if prop == "max-width":
        px = _px(low)
        return _MAX_WIDTH_PX.get(int(px)) if px is not None and px == int(px) else None
    if prop in ("duration", "delay"):
        ms = _ms(low)
        return f"{int(ms)}" if ms is not None and ms in _DURATIONS else None
    if prop in ("width", "height", "min-height", "max-height"):
        # `w-screen` is `100vw` and `w-full` is `100%`. The layout metric reads
        # these names to decide whether anything escapes the centred column, so
        # a full-bleed band written in CSS has to arrive under the same name.
        return _SIZE_KEYWORD.get(low)
    if prop == "text-align":
        return _ALIGN.get(low)
    if prop in _KEYWORD_PROPS and _BARE_KEYWORD.match(low):
        # ``display: grid`` is not an authored value — ``grid`` is the only way
        # to say it, and the utility ``grid`` decodes as DEFAULT for exactly
        # that reason. Treating the CSS spelling as a decision gave a page
        # transcribed out of Tailwind more decisions than the Tailwind it came
        # from. Mirrors ``classes._origin``'s rule for prefixes with no scale.
        return low
    if axis is Axis.COLOR:
        return STOCK_HEX.get(low)
    if prop == "grid-cols":
        m = _TRACKS.match(low)
        if m is not None:
            return m.group(1)
        tracks = low.split()
        if len(tracks) > 1 and len(set(tracks)) == 1 and len(tracks) <= 12:
            return str(len(tracks))
        return None
    return None


# `padding: 5rem 0` is two decisions on two props, and reading it as one value
# on the prop `padding` meant no CSS page could ever be compared with a utility
# one — `py-20` lands on padding-y and nothing lands there from CSS.
_BOX_SHORTHAND = {"padding": "padding", "margin": "margin"}


def _expand_box(prop: str, value: str) -> list[tuple[Axis, str, str]]:
    """``padding: 5rem 0`` → ``[(SPACE, padding-y, 5rem), (SPACE, padding-x, 0)]``."""
    parts = value.split()
    base = _BOX_SHORTHAND[prop]
    if len(parts) == 1:
        return [(Axis.SPACE, base, parts[0])]
    if len(parts) == 2:
        return [(Axis.SPACE, f"{base}-y", parts[0]),
                (Axis.SPACE, f"{base}-x", parts[1])]
    if len(parts) == 3:
        return [(Axis.SPACE, f"{base}-top", parts[0]),
                (Axis.SPACE, f"{base}-x", parts[1]),
                (Axis.SPACE, f"{base}-bottom", parts[2])]
    if len(parts) == 4:
        sides = ("top", "right", "bottom", "left")
        return [(Axis.SPACE, f"{base}-{s}", p) for s, p in zip(sides, parts)]
    return [(Axis.SPACE, base, value)]


# `transition: all 0.3s ease` is three utilities in one string, and the utility
# spelling of it — `transition-all duration-300 ease-*` — decodes as three
# defaults. Read whole, the CSS spelling was one authored value, so the same
# design scored higher for being written in CSS.
_EASINGS = frozenset({"linear", "ease", "ease-in", "ease-out", "ease-in-out",
                      "step-start", "step-end"})


def _expand_transition(value: str) -> list[tuple[str, str]]:
    """``all 0.3s ease`` → ``[(transition, all), (duration, 0.3s), (easing, ease)]``.

    Only the first comma-separated segment is read: a list of transitions is a
    real decision and stays on ``transition`` whole.
    """
    if "," in value or "(" in value:
        return [("transition", value)]
    out: list[tuple[str, str]] = []
    seen_time = False
    for part in value.split():
        low = part.lower()
        if _ms(low) is not None:
            out.append(("duration" if not seen_time else "delay", low))
            seen_time = True
        elif low in _EASINGS:
            out.append(("easing", low))
        else:
            out.append(("transition", low))
    return out or [("transition", value)]


def _strip_comments(text: str) -> str:
    return _COMMENT.sub(lambda m: " " * (m.end() - m.start()), text)


def _split_decls(body: str) -> list[tuple[str, str]]:
    """``"a: 1; b: 2"`` → ``[("a", "1"), ("b", "2")]`` — nested parens survive."""
    out: list[tuple[str, str]] = []
    depth = 0
    part = []
    for ch in body:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == ";" and depth == 0:
            out.append("".join(part))
            part = []
            continue
        part.append(ch)
    out.append("".join(part))
    decls: list[tuple[str, str]] = []
    for chunk in out:
        if ":" not in chunk:
            continue
        k, _, v = chunk.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k and v:
            decls.append((k, v))
    return decls


def parse_css(text: str, offset: int = 0) -> tuple[list[CssRule], dict[str, str]]:
    """Scan a stylesheet into flat rules plus its custom-property table.

    ``offset`` shifts reported positions when the stylesheet was extracted from
    a ``<style>`` block inside a larger file.
    """
    src = _strip_comments(text)
    rules: list[CssRule] = []
    custom: dict[str, str] = {}
    at_stack: list[str] = []
    i = 0
    n = len(src)
    sel_start = 0
    while i < n:
        ch = src[i]
        if ch == "{":
            prelude = src[sel_start:i].strip()
            close = _matching_brace(src, i)
            body = src[i + 1:close]
            if prelude.startswith("@") and "{" in body:
                at_stack.append(_squash(prelude))
                inner, inner_custom = parse_css(body, offset + i + 1)
                for r in inner:
                    r.at = _squash(prelude) if not r.at else f"{_squash(prelude)} {r.at}"
                rules.extend(inner)
                custom.update(inner_custom)
                at_stack.pop()
            else:
                decls = dict(_split_decls(body))
                for k, v in list(decls.items()):
                    if k.startswith("--"):
                        custom[k] = v
                rules.append(CssRule(
                    selector=_squash(prelude),
                    decls=decls,
                    at=at_stack[-1] if at_stack else "",
                    start=offset + sel_start,
                    line=1 + text.count("\n", 0, min(sel_start, len(text))),
                ))
            i = close + 1
            sel_start = i
            continue
        i += 1
    if not rules:
        for m in _CUSTOM_PROP.finditer(src):
            custom.setdefault(m.group(1), m.group(2).strip())
    return rules, custom


def _matching_brace(src: str, i: int) -> int:
    depth = 0
    n = len(src)
    while i < n:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def decl_from_css(prop: str, value: str) -> list[Decl]:
    """One CSS declaration → the axis declarations it expresses."""
    prop = prop.strip().lower()
    value = _squash(value)
    if not prop or not value:
        return []
    origin = Origin.TOKEN if _VAR_REF.search(value) else Origin.LITERAL
    if prop.startswith("--"):
        # A custom property *is* the system. Classify by its own name so the
        # theme lands on the right axis: --color-surface, --space-band.
        axis = _axis_for_var(prop)
        return [Decl(axis, prop, value, Origin.TOKEN, "", f"{prop}: {value}")]
    raw = f"{prop}: {value}"
    if prop in _BOX_SHORTHAND and origin is Origin.LITERAL:
        return [_decl(axis, norm, part, origin, raw)
                for axis, norm, part in _expand_box(prop, value)]
    if prop == "transition" and origin is Origin.LITERAL:
        return [_decl(Axis.MOTION, norm, part, origin, raw)
                for norm, part in _expand_transition(value)]
    fan = _SHORTHAND_FANOUT.get(prop)
    if fan is not None:
        out = []
        for axis, norm in fan:
            part = value
            if axis is Axis.COLOR:
                if not _COLOR_TOKEN.search(value) and origin is not Origin.TOKEN:
                    continue
                # `border: 1px solid #e5e7eb` is a width *and* a colour, and the
                # colour is the third word. Handing the whole shorthand to the
                # colour axis put the string "1px solid #e5e7eb" in the palette,
                # where it matched no shipped value and read as authored.
                part = _color_part(value)
            elif axis is Axis.MATERIAL and norm == "background-image" \
                    and "gradient" not in value:
                # `background: #fff` is a colour, not an image. Counting it on
                # the material axis credited every painted band with a surface
                # treatment nobody applied.
                continue
            out.append(_decl(axis, norm, part, origin, raw))
        return out
    hit = _PROP_MAP.get(prop)
    if hit is None:
        return []
    axis, norm = hit
    if axis is Axis.MATERIAL and norm == "background-image" and "gradient" not in value:
        return []
    return [_decl(axis, norm, value, origin, raw)]


_HEX_IN = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FUNC_IN = re.compile(r"\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color-mix|var)\(")


def _color_part(value: str) -> str:
    """The colour inside a shorthand: ``1px solid #e5e7eb`` → ``#e5e7eb``."""
    m = _HEX_IN.search(value)
    if m is not None:
        return m.group(0)
    m = _FUNC_IN.search(value)
    if m is None:
        return value
    depth, i, n = 0, m.end() - 1, len(value)
    while i < n:
        if value[i] == "(":
            depth += 1
        elif value[i] == ")":
            depth -= 1
            if depth == 0:
                return _squash(value[m.start():i + 1])
        i += 1
    return _squash(value[m.start():])


def _decl(axis: Axis, prop: str, value: str, origin: Origin, raw: str) -> Decl:
    """One declaration, with a shipped value recognised as the default it is.

    ``padding: 5rem 0`` and ``py-20`` are the same decision — or rather the same
    *absence* of one — and until both landed on the value ``20`` the tool scored
    a project a full point higher for spelling its defaults in CSS. That is the
    twin rule the corpus enforces across stacks, applied to syntax: the score
    must describe the design, not the dialect.
    """
    if origin is Origin.LITERAL:
        key = stock_key(axis, prop, value)
        if key is not None:
            return Decl(axis, prop, key, Origin.DEFAULT, "", raw)
    return Decl(axis, prop, value, origin, "", raw)


_VAR_AXIS = (
    ("color", Axis.COLOR), ("bg", Axis.COLOR), ("ink", Axis.COLOR),
    ("surface", Axis.COLOR), ("accent", Axis.COLOR), ("brand", Axis.COLOR),
    ("font", Axis.TYPE), ("text", Axis.TYPE), ("leading", Axis.TYPE),
    ("tracking", Axis.TYPE), ("type", Axis.TYPE),
    ("space", Axis.SPACE), ("gap", Axis.SPACE), ("pad", Axis.SPACE),
    ("rhythm", Axis.SPACE), ("band", Axis.SPACE),
    ("radius", Axis.SHAPE), ("rounded", Axis.SHAPE), ("border", Axis.SHAPE),
    ("shadow", Axis.MATERIAL), ("elevation", Axis.MATERIAL),
    ("blur", Axis.MATERIAL), ("opacity", Axis.MATERIAL),
    ("duration", Axis.MOTION), ("ease", Axis.MOTION), ("transition", Axis.MOTION),
    ("width", Axis.LAYOUT), ("container", Axis.LAYOUT), ("grid", Axis.LAYOUT),
)


def _axis_for_var(name: str) -> Axis:
    """Guess which axis a custom property belongs to from its name."""
    low = name.lower()
    for needle, axis in _VAR_AXIS:
        if needle in low:
            return axis
    return Axis.COLOR


# Longhand pairs a utility spells as one axis. `padding-top: 2.5rem;
# padding-bottom: 2.5rem` is `py-[2.5rem]` — one decision written twice, and
# reading it as two doubled the CSS twin's vocabulary on the space axis while
# halving its score. Folded only when the two values are *equal*: different top
# and bottom padding is two decisions in either dialect.
#
# Deliberately partial, and it says so. Only the pairs whose utility spelling
# actually collapses are here; a longhand this table does not know stays two
# entries, which under-credits a CSS project rather than inventing a decision
# it did not make.
# The joint name is a *CSS property* the map above already knows, never an
# axis prop invented here: `decl_from_css("padding-y", …)` matches nothing and
# silently returns no declaration, which is how the fold's first version
# deleted every symmetric padding in the corpus instead of merging it.
_AXIS_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("padding-top", "padding-bottom", "padding-block"),
    ("padding-left", "padding-right", "padding-inline"),
    ("margin-top", "margin-bottom", "margin-block"),
    ("margin-left", "margin-right", "margin-inline"),
    ("border-top", "border-bottom", "border-block"),
    ("border-left", "border-right", "border-inline"),
    ("border-top-width", "border-bottom-width", "border-block-width"),
    ("border-left-width", "border-right-width", "border-inline-width"),
)


def rule_decls(decls: dict[str, str]) -> list[Decl]:
    """A whole rule's declarations, with longhand pairs folded onto one axis.

    Declaration by declaration is the wrong altitude for the pairs in
    :data:`_AXIS_PAIRS`: a utility says them in one class, so a stylesheet that
    says them in two must still count as one decision or the same design
    measures differently in the two dialects. That is what the clean-side twin
    pair (`clean_utility` / `clean_css`) exists to hold.
    """
    folded: dict[str, str] = dict(decls)
    out: list[Decl] = []
    for a, b, joint in _AXIS_PAIRS:
        first, second = folded.get(a), folded.get(b)
        if first is None or second is None or _squash(first) != _squash(second):
            continue
        del folded[a], folded[b]
        out.extend(decl_from_css(joint, first))
    for prop, value in folded.items():
        out.extend(decl_from_css(prop, value))
    return out


def class_index(rules: list[CssRule]) -> dict[str, list[Decl]]:
    """``{class name: declarations}`` for simple class selectors.

    Only single-class selectors are indexed. Attaching a compound selector to an
    element would need real specificity resolution, and a wrong attachment
    corrupts the rhythm distribution — the one measurement that must be exact.
    """
    out: dict[str, list[Decl]] = {}
    for rule in rules:
        for sel in rule.selector.split(","):
            sel = sel.strip()
            m = re.fullmatch(r"\.([A-Za-z_][\w-]*)", sel)
            if m is None:
                continue
            out.setdefault(m.group(1), []).extend(rule_decls(rule.decls))
    return out
