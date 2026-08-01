"""Rewrite one element's class list onto the derived system.

The hard constraint on this whole module: **only class lists change.** The
element tree is never touched — no tags added, removed, wrapped or reordered.
That is what makes the transform safe to run unattended on a real codebase: a
class list is a string, so the output always parses and always compiles, and
the worst possible failure is a page that looks wrong rather than a build that
does not run. Every layout change below is therefore expressed in classes an
existing element can carry, including the full-bleed break and the asymmetric
grid.

Rewrites fall into four groups:

* **token remap** — stock palette shades, radii and shadows become the system's
  named roles. Mechanical and lossless.
* **type roles** — the framework's size ramp becomes display/section/title/
  lead/body/meta, and display sizes pick up the leading and tracking the ramp
  never had.
* **rhythm** — a section's band padding is chosen by what the section *is*, so
  the one repeated value becomes four that mean something.
* **doctrine** — the archetype's position on alignment, symmetry and depth,
  applied: centred headings released, one grid broken, one band let out to full
  width.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Axis
from ..parse.classes import (FONT_SIZE, SHADOW, TW_COLOR_FAMILIES,
                             split_variants)
from ..system.derive import DesignSystem

# Palette families a generated page reaches for as its accent. Mapped onto the
# system's accent role; every other chromatic family is left alone, because a
# project that used amber for warnings meant it.
ACCENT_FAMILIES = frozenset({"blue", "indigo", "violet", "purple", "sky",
                             "fuchsia", "cyan", "teal"})
NEUTRAL_FAMILIES = frozenset({"slate", "gray", "zinc", "neutral", "stone"})

# Neutral shade → system role. Split at the points where a shade stops being a
# surface and starts being text.
_SURFACE_SHADES = {"50": "shell", "100": "shell", "200": "sink"}
_RULE_SHADES = {"100", "200", "300"}
_TEXT_STRONG = {"800", "900", "950"}
_TEXT_MUTED = {"500", "600", "700"}
_TEXT_FAINT = {"300", "400"}

# Framework size → system type role.
_SIZE_ROLE = {
    "9xl": "display", "8xl": "display", "7xl": "display", "6xl": "display",
    "5xl": "display", "4xl": "section", "3xl": "section",
    "2xl": "title", "xl": "title",
    "lg": "lead", "base": "body", "sm": "meta", "xs": "meta",
}
_DISPLAY_ROLES = {"display", "section"}

# Section role → band token. Four bands where the template had one, chosen by
# what the band is for rather than by position, so the rhythm still reads as a
# system rather than as noise.
BAND_FOR_ROLE = {
    "hero": "open", "cta": "open",
    "features": "narrative", "how": "narrative", "testimonials": "narrative",
    "content": "narrative",
    "pricing": "dense", "faq": "dense", "stats": "dense", "logos": "dense",
    "nav": "close", "footer": "close",
    # The structural roles (`metrics.sections.STRUCTURAL`). A band the
    # classifier can only name by shape still has a rhythm that belongs to that
    # shape: a plate of images wants air, an index wants none of it.
    "gallery": "open", "statement": "open",
    "list": "narrative", "prose": "narrative", "contact": "dense",
}
MEASURE_FOR_ROLE = {
    "hero": "content", "cta": "content", "features": "content",
    "pricing": "content", "logos": "content", "stats": "content",
    "how": "narrow", "testimonials": "narrow", "content": "narrow",
    "faq": "narrow", "nav": "content", "footer": "content",
    "gallery": "content", "list": "content",
    "statement": "read", "prose": "read", "contact": "narrow",
}

# Asymmetric column patterns over a 12-column base, keyed by child count. Each
# grid on a page takes the next pattern in its list, so two three-card rows do
# not end up with the same split — repeating one asymmetry is still a template.
ASYMMETRIC: dict[int, list[list[int]]] = {
    2: [[7, 5], [5, 7]],
    3: [[5, 4, 3], [4, 5, 3], [3, 5, 4]],
    4: [[7, 5, 5, 7], [5, 7, 7, 5]],
    6: [[4, 4, 4, 4, 4, 4], [5, 4, 3, 3, 4, 5]],
}

_CONTROL_TAGS = frozenset({"a", "button", "input", "select", "textarea", "label"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SHADE = re.compile(r"^([a-z]+)-(\d{2,3})$")


@dataclass
class Context:
    """Everything the rewriter needs to know about one element."""

    tag: str
    section_role: str = ""          # role of the section this element belongs to
    is_band: bool = False           # the element carrying the section's padding
    is_container: bool = False      # the element carrying the content measure
    is_hero: bool = False
    grid_children: int = 0          # >0 when this element is a symmetric grid
    grid_index: int = 0             # which grid on the page, for pattern choice
    span: int = 0                   # column span assigned to this grid child
    full_bleed: bool = False        # promote this element to a full-width break
    on_accent: bool = False         # sits on an accent surface, so text flips
    notes: list[str] = field(default_factory=list)


def rewrite_tokens(classes: list[str], ctx: Context,
                   system: DesignSystem) -> tuple[list[list[str]], list[str]]:
    """``(replacement per input class, classes the element gains)``.

    Kept separate from :func:`rewrite` because a class list is not always one
    string. When it is spread across the literals of a ``className={…}``
    expression, each literal has to be rewritten where it stands, and only the
    caller knows which of them is safe to grow.
    """
    added: list[str] = []
    mapped: list[list[str]] = []
    for cls in classes:
        variants, util = split_variants(cls)
        prefix = "".join(f"{v}:" for v in variants)
        result = _map_util(util, ctx, system, added)
        if result is None:
            mapped.append([])             # dropped on purpose (e.g. no shadows)
            continue
        mapped.append([f"{prefix}{piece}" for piece in result if piece])
    return mapped, added + _additions(ctx, system)


def rewrite(classes: list[str], ctx: Context, system: DesignSystem) -> list[str]:
    """Return the element's new class list. Order and duplicates are cleaned."""
    mapped, extras = rewrite_tokens(classes, ctx, system)
    out: list[str] = []
    seen: set[str] = set()
    for group in mapped:
        for token in group:
            if token not in seen:
                seen.add(token)
                out.append(token)
    for extra in extras:
        if extra not in seen:
            seen.add(extra)
            out.append(extra)
    return resolve(out, installed(classes, mapped, extras))


def installed(classes: list[str], mapped: list[list[str]],
              extras: list[str]) -> set[str]:
    """The tokens this rewrite *put there*, as opposed to left alone.

    Read off the mapping rather than off a table of names: a class that came
    back unchanged is the project's, and everything else is the system's. That
    is what :func:`resolve` needs in order to know which side of a fight to
    keep, and deriving it here means no list of emitted names can go stale.
    """
    out = set(extras)
    for original, group in zip(classes, mapped):
        out.update(token for token in group if token != original)
    return out


def resolve(tokens: list[str], installed: set[str]) -> list[str]:
    """Drop the two ways a rewritten class list can contradict itself.

    * **A fight.** The transform adds ``tracking-display`` to a heading that
      already said ``tracking-tight``; both reach the browser and the last one
      in the stylesheet wins, silently. What the transform installed is the
      decision, and the value it replaced is exactly what it came to replace,
      so the installed token keeps the property and the other is dropped.
    * **A variant that overrides nothing.** ``text-blue-600 dark:text-blue-400``
      both map to the accent role, so the ``dark:`` class becomes a no-op —
      23 of them on `landwind` in one run. Same for ``py-16 lg:py-20`` once both
      are the same band token.

    Neither is a broken build, which is why nothing else caught them: they are
    output that says nothing, and ``bench.field`` counts what is left.
    """
    keys = {t: keyed(t) for t in tokens}
    base: dict[str, set[str]] = {}
    for token in tokens:
        k = keys[token]
        if k is not None and not k[0]:
            base.setdefault(k[1], set()).add(k[2])

    winners: dict[tuple[str, str], str] = {}
    for token in tokens:
        k = keys[token]
        if k is None:
            continue
        at = (k[0], k[1])
        if at not in winners or (token in installed and winners[at] not in installed):
            winners[at] = token

    out: list[str] = []
    for token in tokens:
        k = keys[token]
        if k is None:
            out.append(token)
            continue
        variant, prop, value = k
        if winners[(variant, prop)] != token:
            continue                       # lost the property to what we installed
        if variant and value in base.get(prop, ()):
            continue                       # a variant that repeats its own base
        out.append(token)
    return out


def keyed(cls: str) -> tuple[str, str, str] | None:
    """``(variant, prop, value)`` for one class in this system's vocabulary.

    Two overrides sit ahead of the shared decoder, and both exist because that
    decoder is project-blind while this module is reading *its own* output.
    ``text-display`` is a size here and a colour in most real themes — the
    decoder documents choosing colour on purpose — and ``border-rule`` is a
    colour, not the width that a bare ``border`` sets on the same element.
    """
    from ..parse.classes import decode_class

    variants, util = split_variants(cls)
    variant = ":".join(variants)
    if util.startswith("text-") and util[5:] in TYPE_ROLES:
        return variant, "font-size", util[5:]
    for pref in _EDGE_PREFIXES:
        if util.startswith(pref) and util[len(pref):] in COLOR_ROLES:
            return variant, f"{pref[:-1]}-color", util[len(pref):]
    decl = decode_class(cls)
    return (decl.variant, decl.prop, decl.value) if decl is not None else None


# The role names the emitted system uses, kept next to the code that writes
# them. `transform.verify` reads the same two sets.
TYPE_ROLES = frozenset({"display", "section", "title", "lead", "body", "meta"})
COLOR_ROLES = frozenset({
    "paper", "shell", "sink", "rule", "ink", "ink-muted", "ink-faint",
    "accent", "accent-soft", "accent-strong", "on-accent", "support",
})
_EDGE_PREFIXES = ("border-", "ring-", "outline-", "divide-")


def _map_util(util: str, ctx: Context, system: DesignSystem,
              added: list[str]) -> list[str] | None:
    """One utility → its replacement(s); ``None`` drops it."""
    for handler in (_map_color, _map_type, _map_space, _map_shape,
                    _map_material, _map_motion, _map_layout):
        result = handler(util, ctx, system, added)
        if result is not None:
            return result
    return [util]


# ------------------------------------------------------------------- colour
_COLOR_PREFIXES = ("bg-", "text-", "border-", "ring-", "fill-", "stroke-",
                   "divide-", "from-", "via-", "to-", "shadow-", "outline-",
                   "placeholder-", "accent-", "caret-")


def _map_color(util: str, ctx: Context, system: DesignSystem,
               added: list[str]) -> list[str] | None:
    for pref in sorted(_COLOR_PREFIXES, key=len, reverse=True):
        if not util.startswith(pref):
            continue
        value = util[len(pref):]
        base, _, alpha = value.partition("/")
        role = _color_role(base, pref, ctx)
        if role is None:
            # Not a stock colour on this prefix. Returning ``None`` rather than
            # the utility is essential: `text-` is both a colour prefix and the
            # size prefix, so claiming `text-4xl` here would stop the type
            # mapping from ever seeing it.
            return None
        return [f"{pref}{role}" + (f"/{alpha}" if alpha else "")]
    return None


def _color_role(base: str, pref: str, ctx: Context) -> str | None:
    """The system role a stock colour value maps onto, or ``None`` to keep it."""
    if base == "white":
        return "on-accent" if ctx.on_accent and pref == "text-" else (
            "paper" if pref == "bg-" else None)
    if base == "black":
        return "ink" if pref in ("text-", "fill-", "stroke-") else "ink"
    m = _SHADE.match(base)
    if m is None:
        return None
    family, shade = m.group(1), m.group(2)

    if family in NEUTRAL_FAMILIES:
        if pref == "bg-":
            return _SURFACE_SHADES.get(shade, "ink" if shade in _TEXT_STRONG else "shell")
        if pref in ("border-", "divide-", "ring-", "outline-"):
            return "rule" if shade in _RULE_SHADES else "ink"
        if shade in _TEXT_STRONG:
            return "ink"
        if shade in _TEXT_MUTED:
            return "ink-muted"
        if shade in _TEXT_FAINT:
            return "ink-faint"
        return "ink-muted"

    if family in ACCENT_FAMILIES:
        if shade in ("50", "100"):
            return "accent-soft"
        if shade in ("700", "800", "900", "950"):
            return "accent-strong"
        return "accent"
    return None            # amber for warnings, red for errors — left alone


# --------------------------------------------------------------------- type
def _map_type(util: str, ctx: Context, system: DesignSystem,
              added: list[str]) -> list[str] | None:
    if util.startswith("text-"):
        value = util[5:]
        if value not in FONT_SIZE:
            return None
        role = _SIZE_ROLE.get(value, "body")
        pieces = [f"text-{role}"]
        if role in _DISPLAY_ROLES and ctx.tag in _HEADING_TAGS:
            # The default ramp ships body leading and no tracking; at display
            # sizes that is the single most visible untuned thing on a page.
            pieces += ["font-display", "leading-display", "tracking-display"]
        return pieces
    if util.startswith("font-") and util[5:] in ("sans", "serif", "mono"):
        return ["font-body" if util[5:] != "mono" else "font-mono"]
    return None


# -------------------------------------------------------------------- space
_PAD_Y = re.compile(r"^(py|pt|pb)-(\d+(?:\.\d+)?|px)$")
_MAX_W = re.compile(r"^max-w-(.+)$")
_GAP = re.compile(r"^gap-(\d+(?:\.\d+)?|px)$")


def _map_space(util: str, ctx: Context, system: DesignSystem,
               added: list[str]) -> list[str] | None:
    m = _PAD_Y.match(util)
    if m and ctx.is_band:
        band = BAND_FOR_ROLE.get(ctx.section_role, "narrative")
        return [f"{m.group(1)}-band-{band}"]
    m = _MAX_W.match(util)
    if m and ctx.is_container:
        if ctx.full_bleed:
            return ["max-w-none"]
        return [f"max-w-{MEASURE_FOR_ROLE.get(ctx.section_role, 'content')}"]
    m = _GAP.match(util)
    if m:
        gx, gy = system.archetype.gap
        return [f"gap-x-[{gx}]", f"gap-y-[{gy}]"]
    return None


# -------------------------------------------------------------------- shape
_ROUNDED = re.compile(r"^rounded(?:-(tl|tr|br|bl|t|r|b|l))?(?:-(.+))?$")


def _map_shape(util: str, ctx: Context, system: DesignSystem,
               added: list[str]) -> list[str] | None:
    m = _ROUNDED.match(util)
    if m is None:
        return None
    corner, value = m.group(1), m.group(2)
    if value == "full":
        return [util]                     # avatars and pills keep their circle
    role = "control" if ctx.tag in _CONTROL_TAGS else "panel"
    if system.radii.get(role, "").strip() in ("0", "0px"):
        return []                         # this archetype has no rounded corners
    suffix = f"-{corner}" if corner else ""
    return [f"rounded{suffix}-{role}"]


# ----------------------------------------------------------------- material
def _map_material(util: str, ctx: Context, system: DesignSystem,
                  added: list[str]) -> list[str] | None:
    if not util.startswith("shadow"):
        return None
    value = util[7:] if util.startswith("shadow-") else ""
    if value and value not in SHADOW:
        return None                       # shadow-<colour>, handled elsewhere
    heavy = value in ("xl", "2xl")
    role = "float" if heavy else "lift"
    if system.shadows.get(role, "none").strip() == "none":
        # An archetype that refuses shadows has to actually refuse them, or the
        # "one surface recipe" it was chosen to break survives the transform.
        return []
    return [f"shadow-{role}"]


# -------------------------------------------------------------------- motion
_DURATION = re.compile(r"^duration-\d+$")


def _map_motion(util: str, ctx: Context, system: DesignSystem,
                added: list[str]) -> list[str] | None:
    if util == "transition-all":
        return ["transition-colors"]
    if _DURATION.match(util):
        return ["duration-[var(--duration-tint)]", "ease-enter"]
    return None


# -------------------------------------------------------------------- layout
def _map_layout(util: str, ctx: Context, system: DesignSystem,
                added: list[str]) -> list[str] | None:
    if util == "text-center":
        if ctx.is_hero and system.archetype.align == "center-hero":
            return [util]
        return []                         # release the centred monoculture
    if util.startswith("grid-cols-") and ctx.grid_children:
        # Dropped here and re-added by ``_additions`` rather than replaced in
        # place: the replacement carries its own breakpoint prefix, and the
        # rewriter re-applies the *original* variant to whatever a handler
        # returns — which turned `md:grid-cols-3` into `md:md:grid-cols-12`.
        return []
    return None


def _additions(ctx: Context, system: DesignSystem) -> list[str]:
    """Classes an element gains that it had no equivalent of before."""
    out: list[str] = []
    if ctx.grid_children:
        out += ["grid-cols-1", "md:grid-cols-12"]
    if ctx.span:
        out.append(f"md:col-span-{ctx.span}")
    if ctx.full_bleed:
        # A real full-width break, expressed only in classes: the element keeps
        # its place in the tree and steps outside its container visually.
        out += ["w-screen", "relative", "left-1/2", "-translate-x-1/2"]
    return out


def spans_for(count: int, grid_index: int) -> list[int]:
    """Column spans for a grid's children, varied per grid on the page."""
    patterns = ASYMMETRIC.get(count)
    if not patterns:
        even = max(1, 12 // count)
        return [even] * count
    return patterns[grid_index % len(patterns)]
