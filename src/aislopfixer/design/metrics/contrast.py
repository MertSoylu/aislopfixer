"""Contrast as a design measure, not a lint rule.

The old engine asked "does this ``<img>`` have an ``alt``?", which is a
question ESLint answers better. This one asks something only a design tool can:
**which text/background pairs does this project actually put on screen, and how
many of them are readable?** A page whose muted text is ``gray-400`` on white
has made a design decision — it chose a grey — and the decision is wrong for a
reason that is measurable.

Two ways of measuring, and never a third:

* **Authored colours** — hex literals and custom properties the project defined
  — are compared exactly, with the same WCAG maths the derived system is held
  to in :mod:`aislopfixer.design.system.color`.
* **Neutral framework shades** are compared through the ramp's own relative
  luminance, which is a published constant of the scale rather than a guess.
  It is restricted to the neutral families on purpose: those are calibrated to
  one curve, while a chromatic ``500`` swings from ``amber`` to ``indigo`` by
  more than the whole AA margin, and one table for all of them would invent
  failures.

Anything else is **skipped** — a pair with one authored colour and one
framework shade, a chromatic pair, an element with nothing declared underneath
it. An unverifiable accessibility claim is worse than none, so the measure only
speaks where it can be checked.
"""

from __future__ import annotations

import re

from ..models import Axis, Document, Element, Observation
from ..system.color import contrast_ratio
from .util import cap_evidence, evidence_for

_SHADE = re.compile(r"^(.*)-(\d{2,3})$")
_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")
# `text-[var(--ink)]`, Tailwind v4's `text-(--ink)`, and a raw `var(--ink)` in a
# stylesheet all name the same custom property.
_VAR = re.compile(r"^(?:var)?\(\s*(?:[a-z]+:)?(--[\w-]+)\s*\)$")
_BRACKETS = re.compile(r"^\[(.*)\]$", re.S)

_AA = 4.5
_AA_LARGE = 3.0               # ≥24px, or bold ≥18.66px
# A pair within this much of the threshold is left alone: the ramp table is one
# curve for five neutral families, and the difference between them is smaller
# than this margin but not zero.
_MARGIN = 0.95

# Relative luminance of each step of the neutral ramp — the same curve every
# neutral family is built on. `0` stands for white and `1000` for black.
_RAMP: dict[int, float] = {
    0: 1.0, 50: 0.961, 100: 0.905, 200: 0.800, 300: 0.647, 400: 0.364,
    500: 0.167, 600: 0.087, 700: 0.048, 800: 0.022, 900: 0.010, 950: 0.002,
    1000: 0.0,
}
_NEUTRALS = frozenset({"slate", "gray", "zinc", "neutral", "stone"})

_LARGE_SIZES = frozenset({"2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl", "9xl"})
_HEADINGS = frozenset({"h1", "h2"})
_BG_REACH = 6                 # ancestors searched for the surface underneath
_MIN_PAIRS = 4


def _luminance(value: str) -> float | None:
    """Relative luminance of a neutral framework colour, else ``None``."""
    base = value.split("/", 1)[0]
    if base == "white":
        return _RAMP[0]
    if base == "black":
        return _RAMP[1000]
    m = _SHADE.match(base)
    if m is None or m.group(1) not in _NEUTRALS:
        return None
    return _RAMP.get(int(m.group(2)))


def _ratio(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _authored(value: str, props: dict[str, str]) -> str | None:
    """A colour the project defined, resolved to a hex literal."""
    value = value.strip()
    inner = _BRACKETS.match(value)
    if inner is not None:
        value = inner.group(1).strip()
    for _ in range(8):                    # `--a: var(--b)` chains do happen
        if _HEX.match(value):
            return value
        m = _VAR.match(value)
        if m is None:
            return None
        value = props.get(m.group(1), "").strip()
    return None


def _color_on(el: Element, prop: str) -> str:
    for d in el.decls:
        if d.axis is Axis.COLOR and d.prop == prop and not d.variant:
            return d.value
    return ""


def _surface_under(doc: Document, idx: int) -> str:
    """The background an element sits on, searched up its ancestors."""
    i, hops = idx, 0
    while i >= 0 and hops <= _BG_REACH:
        found = _color_on(doc.elements[i], "background")
        if found and found != "transparent":
            return found
        i = doc.elements[i].parent
        hops += 1
    return ""


def _is_large(el: Element) -> bool:
    if el.tag in _HEADINGS:
        return True
    for d in el.decls:
        if d.axis is Axis.TYPE and d.prop == "font-size" and d.value in _LARGE_SIZES:
            return True
    return False


def analyze(docs: list[Document], all_docs: list[Document]) -> list[Observation]:
    """The ``color.low_contrast`` observation, or nothing."""
    props: dict[str, str] = {}
    for doc in all_docs:
        props.update(doc.custom_props)

    pairs = 0
    failures: list[tuple[Document, Element, str]] = []
    for doc in docs:
        for i, el in enumerate(doc.elements):
            ink = _color_on(el, "color")
            if not ink or not el.own_text:
                continue
            paper = _surface_under(doc, i)
            if not paper:
                continue          # nothing declared underneath — do not assume

            large = _is_large(el)
            ink_hex, paper_hex = _authored(ink, props), _authored(paper, props)
            if ink_hex and paper_hex:
                pairs += 1
                ratio = contrast_ratio(ink_hex, paper_hex)
                if ratio < (_AA_LARGE if large else _AA):
                    failures.append((doc, el, f"{ratio:.1f}:1 · {ink} / {paper}"))
                continue

            a, b = _luminance(ink), _luminance(paper)
            if a is None or b is None:
                continue          # chromatic, or mixed with an authored colour
            pairs += 1
            ratio = _ratio(a, b)
            if ratio < (_AA_LARGE if large else _AA) * _MARGIN:
                failures.append((doc, el, f"~{ratio:.1f}:1 · {ink} / {paper}"))

    if pairs < _MIN_PAIRS or not failures:
        return []
    share = len(failures) / pairs
    return [Observation(
        axis=Axis.COLOR,
        id="color.low_contrast",
        title="Okunmayan metin/zemin çiftleri",
        detail=(
            f"Sayfada ölçülebilen {pairs} metin/zemin çiftinin {len(failures)}'i "
            f"WCAG AA eşiğinin altında kalıyor. Bunlar bir erişilebilirlik "
            f"eksiği olmadan önce bir tasarım kararı: “ikincil metin daha açık "
            f"olsun” dendi ve ne kadar açık olacağına bakılmadı. Kontrast, "
            f"hiyerarşiyi kuran şeydir — okunmayan gri, hiyerarşi değil kayıptır."
        ),
        severity=round(min(1.0, 0.35 + share), 3),
        stat=f"{len(failures)}/{pairs} çift AA altı",
        evidence=cap_evidence([evidence_for(d, e, note) for d, e, note in failures]),
        prescription=(
            "Metin rollerini kontrast hedefiyle tanımla: gövde ≥ 4.5:1, ikincil "
            "≥ 4.5:1, yalnızca dekoratif/devre dışı olan altına inebilir. "
            "İkincil metni bir ton daha koyu al; “soluk” hissi rengi açmakla "
            "değil, boyut ve ağırlıkla verilir."
        ),
    )]
