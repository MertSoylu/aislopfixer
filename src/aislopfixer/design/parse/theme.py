"""Project theme config → the framework keys the project redefined.

The decision/default split in :mod:`.classes` reads Tailwind's *shipped* scales:
``text-lg`` is a default because ``lg`` is a key the framework already chose.
That is true of a stock install and false of a project that wrote its own
``fontSize`` scale — and such a project was being told it had no typography
decisions precisely *because* it named its steps after the ones it replaced.
The tool was hardest on the projects that took the most care.

So the config is read and the *keys it touches* are recorded. Key by key: if
``fontSize.lg`` is redefined then ``text-lg`` is a decision, while ``text-4xl``
still is not. Both dialects are handled — a v3 ``theme.extend`` object and a v4
``@theme { --text-lg: … }`` block — because a project should not have to be on
the version the tool guessed.

Nothing here guesses. A key that cannot be read is simply absent, which
under-credits the project rather than inventing a decision for it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..models import Axis

__all__ = ["ThemeIndex", "load_theme", "parse_theme"]

# ------------------------------------------------------------------- groupings
# A theme scale covers many utilities: one ``spacing`` scale feeds every padding,
# margin and gap utility there is. Keys are therefore recorded against a *group*
# rather than a single normalized prop.
_PROP_GROUP: dict[str, str] = {
    "font-size": "font-size",
    "font-weight": "font-weight",
    "font-family": "font-family",
    "line-height": "line-height",
    "letter-spacing": "letter-spacing",
    "max-width": "max-width",
    "duration": "duration",
    "delay": "duration",
    "easing": "easing",
    "animation": "animation",
    "blur": "blur",
    "backdrop-blur": "blur",
    "opacity": "opacity",
    "z-index": "z-index",
    "grid-cols": "grid-cols",
    "shadow": "shadow",
    "drop-shadow": "shadow",
}


def group_for(axis: Axis, prop: str) -> str | None:
    """Which theme scale a decoded ``(axis, prop)`` draws its keys from."""
    hit = _PROP_GROUP.get(prop)
    if hit is not None:
        return hit
    if prop.startswith("radius"):
        return "radius"
    if prop.startswith("border") or prop.startswith("divide") or prop.startswith("ring"):
        return "border"
    if axis is Axis.COLOR:
        return "color"
    if axis is Axis.SPACE:
        return "spacing"
    return None


@dataclass(frozen=True)
class ThemeIndex:
    """The scale keys a project redefined, plus where they were read from.

    Frozen and hashable on purpose: :func:`~.classes.decode_class` caches on it,
    and a mutable index would let two projects inherit each other's decisions.
    """

    pairs: frozenset[tuple[str, str]] = field(default_factory=frozenset)
    sources: tuple[str, ...] = ()
    # Font-size keys the config declares *with* a line-height or letter-spacing
    # beside them. A tuned ramp leaves no trace on the element — the decision was
    # made once, in the config, which is the better place to make it — so a
    # display-type tell that reads only elements accuses the careful project.
    tuned: frozenset[str] = field(default_factory=frozenset)

    def __bool__(self) -> bool:
        return bool(self.pairs)

    def tunes(self, value: str) -> bool:
        """True when this font-size key carries its own leading/tracking."""
        return value.split("/", 1)[0] in self.tuned

    def redefines(self, axis: Axis, prop: str, value: str) -> bool:
        """True when the project's own config supplies this utility's value."""
        if not self.pairs:
            return False
        group = group_for(axis, prop)
        if group is None:
            return False
        base = value.split("/", 1)[0].lstrip("-") or "DEFAULT"
        if (group, base) in self.pairs:
            return True
        if group == "color":
            # ``bg-brand-500`` is served by a redefined ``colors.brand``.
            family = base.rpartition("-")[0]
            if family and (group, family) in self.pairs:
                return True
        return False

    @property
    def groups(self) -> set[str]:
        return {g for g, _ in self.pairs}


EMPTY = ThemeIndex()


# ------------------------------------------------------------------ v3 configs
# ``theme`` / ``theme.extend`` keys → the group whose utilities they feed. Keys
# outside this table are real Tailwind scales the engine has no axis for
# (``screens``, ``keyframes``); recording them would credit a decision no
# utility can express.
_V3_SCALE: dict[str, str] = {
    "fontsize": "font-size",
    "fontweight": "font-weight",
    "fontfamily": "font-family",
    "lineheight": "line-height",
    "letterspacing": "letter-spacing",
    "colors": "color",
    "textcolor": "color",
    "backgroundcolor": "color",
    "bordercolor": "color",
    "ringcolor": "color",
    "accentcolor": "color",
    "fill": "color",
    "stroke": "color",
    "spacing": "spacing",
    "padding": "spacing",
    "margin": "spacing",
    "gap": "spacing",
    "space": "spacing",
    "borderradius": "radius",
    "borderwidth": "border",
    "ringwidth": "border",
    "boxshadow": "shadow",
    "dropshadow": "shadow",
    "maxwidth": "max-width",
    "transitionduration": "duration",
    "transitiontimingfunction": "easing",
    "animation": "animation",
    "blur": "blur",
    "backdropblur": "blur",
    "opacity": "opacity",
    "zindex": "z-index",
    "gridtemplatecolumns": "grid-cols",
}

_CONFIG_NAME = re.compile(r"^tailwind\.config\.(?:js|cjs|mjs|ts|mts|cts)$", re.I)
_THEME_KEY = re.compile(r"""["']?theme["']?\s*:\s*\{""")
_EXTEND_KEY = re.compile(r"""["']?extend["']?\s*:\s*\{""")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _decomment(text: str) -> str:
    """Blank out comments, preserving offsets so brace matching stays honest."""
    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))
    return _LINE_COMMENT.sub(blank, _BLOCK_COMMENT.sub(blank, text))


def _match_brace(src: str, i: int) -> int:
    """Index of the ``}`` closing the ``{`` at ``i``; strings are skipped."""
    depth = 0
    n = len(src)
    quote = ""
    while i < n:
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "{[(":
            if ch == "{":
                depth += 1
        elif ch in "}])":
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return n


_KEY_AT = re.compile(r"""(?:(["'])([^"'\n]+)\1|([A-Za-z_$][\w$-]*)|(\d+(?:\.\d+)?))\s*:""")


def _top_keys(body: str) -> list[tuple[str, int]]:
    """``(key, offset just past its colon)`` for the object body's own keys.

    Only depth-0 keys are returned, so ``colors: { brand: { 500: … } }`` yields
    ``colors`` and not ``500``.
    """
    out: list[tuple[str, int]] = []
    depth = 0
    quote = ""
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch in "{[(":
            depth += 1
            i += 1
            continue
        if ch in "}])":
            depth -= 1
            i += 1
            continue
        if depth == 0:
            m = _KEY_AT.match(body, i)
            if m is not None:
                out.append((m.group(2) or m.group(3) or m.group(4), m.end()))
                i = m.end()
                continue
        i += 1
    return out


def _object_after(src: str, at: int) -> str:
    """Body of the object literal starting at or after ``at``; ``""`` if none."""
    j = at
    n = len(src)
    while j < n and src[j].isspace():
        j += 1
    if j >= n or src[j] != "{":
        return ""
    return src[j + 1:_match_brace(src, j)]


_TUPLE_TUNING = re.compile(r"lineHeight|letterSpacing|line-height|letter-spacing")


def _scan_v3(text: str) -> tuple[set[tuple[str, str]], set[str]]:
    """Keys a Tailwind v3-style config object redefines, and the tuned sizes."""
    src = _decomment(text)
    pairs: set[tuple[str, str]] = set()
    tuned: set[str] = set()
    for tm in _THEME_KEY.finditer(src):
        body = _object_after(src, tm.end() - 1)
        if not body:
            continue
        bodies = [body]
        for em in _EXTEND_KEY.finditer(body):
            inner = _object_after(body, em.end() - 1)
            if inner:
                bodies.append(inner)
        for scope in bodies:
            for key, after in _top_keys(scope):
                group = _V3_SCALE.get(key.replace("-", "").replace("_", "").lower())
                if group is None:
                    continue
                scale = _object_after(scope, after)
                if not scale:
                    continue
                entries = _top_keys(scale)
                for i, (name, value_at) in enumerate(entries):
                    pairs.add((group, str(name)))
                    if group != "font-size":
                        continue
                    end = entries[i + 1][1] if i + 1 < len(entries) else len(scale)
                    if _TUPLE_TUNING.search(scale[value_at:end]):
                        tuned.add(str(name))
    return pairs, tuned


# ------------------------------------------------------------------ v4 @theme
# v4 names a scale by the custom property's namespace. Longest prefix wins:
# ``--font-weight-bold`` is a weight, ``--font-display`` is a family.
_V4_NAMESPACE: tuple[tuple[str, str], ...] = tuple(sorted(
    (
        ("--color-", "color"),
        ("--text-", "font-size"),
        ("--font-weight-", "font-weight"),
        ("--font-", "font-family"),
        ("--leading-", "line-height"),
        ("--tracking-", "letter-spacing"),
        ("--spacing-", "spacing"),
        ("--radius-", "radius"),
        ("--shadow-", "shadow"),
        ("--inset-shadow-", "shadow"),
        ("--drop-shadow-", "shadow"),
        ("--blur-", "blur"),
        ("--container-", "max-width"),
        ("--ease-", "easing"),
        ("--animate-", "animation"),
    ),
    key=lambda kv: -len(kv[0]),
))

_THEME_AT = re.compile(r"@theme\b[^{]*\{")
_DECL = re.compile(r"(--[\w-]+)\s*:")


# v4 states a size's leading and tracking as sub-properties of the size itself:
# ``--text-4xl--line-height: 1.2``. Same decision, different spelling.
_V4_TUNING = re.compile(r"^--text-(.+?)--(?:line-height|letter-spacing)$")


def _scan_v4(text: str) -> tuple[set[tuple[str, str]], set[str]]:
    """Keys a v4 ``@theme`` block declares, and the tuned font sizes."""
    src = _decomment(text)
    pairs: set[tuple[str, str]] = set()
    tuned: set[str] = set()
    for m in _THEME_AT.finditer(src):
        open_at = m.end() - 1
        body = src[open_at + 1:_match_brace(src, open_at)]
        for d in _DECL.finditer(body):
            name = d.group(1)
            hit = _V4_TUNING.match(name)
            if hit is not None:
                tuned.add(hit.group(1))
                continue
            for prefix, group in _V4_NAMESPACE:
                if name.startswith(prefix) and len(name) > len(prefix):
                    pairs.add((group, name[len(prefix):]))
                    break
    return pairs, tuned


def parse_theme(rel_path: str, text: str) -> tuple[set[tuple[str, str]], set[str]]:
    """Theme keys declared by one file, plus the font sizes it tuned."""
    name = os.path.basename(rel_path)
    pairs: set[tuple[str, str]] = set()
    tuned: set[str] = set()
    if "@theme" in text:
        found, tune = _scan_v4(text)
        pairs |= found
        tuned |= tune
    if _CONFIG_NAME.match(name) and "theme" in text:
        found, tune = _scan_v3(text)
        pairs |= found
        tuned |= tune
    return pairs, tuned


def load_theme(sources) -> ThemeIndex:
    """Build the project's :class:`ThemeIndex` from its already-read sources.

    ``sources`` is any iterable of objects carrying ``rel_path`` and ``text``
    (a :class:`~aislopfixer.scanner.SourceFile` or a
    :class:`~aislopfixer.design.models.Document`), so the config is read from
    the same pass that reads everything else rather than costing a second walk.
    """
    pairs: set[tuple[str, str]] = set()
    tuned: set[str] = set()
    files: list[str] = []
    for sf in sources:
        found, tune = parse_theme(sf.rel_path, sf.text)
        if found or tune:
            pairs |= found
            tuned |= tune
            files.append(sf.rel_path)
    if not pairs and not tuned:
        return EMPTY
    return ThemeIndex(pairs=frozenset(pairs), sources=tuple(sorted(files)),
                      tuned=frozenset(tuned))
