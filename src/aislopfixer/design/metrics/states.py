"""State coverage: the half of the design that only exists in another mode.

A page has more than one state, and a generated one is designed in exactly one.
The classic result is an interface where the hero, the nav and two cards carry
``dark:`` and the rest do not — which is not a dark mode, it is a page that
breaks in the dark. The same happens to focus: a few controls get a ring, the
others keep whatever the browser does, and one of them has had the browser's
outline removed.

Both measures are **coverage of a claim**, never presence. A project with no
``dark:`` anywhere has not failed dark mode, it has declined it, and declining
is a legitimate decision — the same rule that keeps an unused axis out of the
headline scores. Only a project that started is asked to finish.

Both are also skipped when the stylesheet does the work: a ``.dark`` selector or
a ``:focus-visible`` rule covers elements that carry no utility at all, and
counting utilities in that project would measure the authoring style rather
than the design.
"""

from __future__ import annotations

import re

from ..models import Axis, Document, Element, Observation
from .util import cap_evidence, evidence_for

# Props whose value defines a surface or the text on it — the ones a mode swap
# has to answer for. Borders count: an unswapped hairline is the tell that
# survives even when the background was remembered.
_MODE_PROPS = frozenset({"background", "color", "border-color"})
_MIN_SURFACES = 10
_DARK_COVERED_AT = 0.85     # coverage above which the mode is simply done

_INTERACTIVE_TAGS = frozenset({"a", "button", "select", "textarea", "summary"})
_MIN_CONTROLS = 5
_FOCUS_COVERED_AT = 0.6

_CSS_DARK = re.compile(r"prefers-color-scheme\s*:\s*dark|(?:^|\s|,)\.dark\b")
_CSS_FOCUS = re.compile(r":focus")


def _has_variant(el: Element, name: str) -> bool:
    return any(name in d.variant.split(":") for d in el.decls if d.variant)


def _mode_surfaces(docs: list[Document]) -> tuple[list[tuple[Document, Element]],
                                                  list[tuple[Document, Element]]]:
    """``(every element that paints, those that also paint in the dark)``."""
    painted: list[tuple[Document, Element]] = []
    dark: list[tuple[Document, Element]] = []
    for doc in docs:
        for el in doc.elements:
            if not any(d.axis is Axis.COLOR and not d.variant
                       and d.prop in _MODE_PROPS for d in el.decls):
                continue
            painted.append((doc, el))
            if any(d.axis is Axis.COLOR and "dark" in d.variant.split(":")
                   for d in el.decls if d.variant):
                dark.append((doc, el))
    return painted, dark


def _controls(docs: list[Document]) -> tuple[list[tuple[Document, Element]],
                                             list[tuple[Document, Element]]]:
    """``(every control, those with a focus style of their own)``."""
    every: list[tuple[Document, Element]] = []
    focused: list[tuple[Document, Element]] = []
    for doc in docs:
        for el in doc.elements:
            interactive = (
                el.tag in _INTERACTIVE_TAGS or el.tag == "input"
                or el.attrs.get("role") == "button" or "tabindex" in el.attrs)
            if not interactive:
                continue
            every.append((doc, el))
            if _has_variant(el, "focus-visible") or _has_variant(el, "focus"):
                focused.append((doc, el))
    return every, focused


def _stylesheet_handles(docs: list[Document], pattern: re.Pattern) -> bool:
    """True when the project answers this state in CSS rather than utilities."""
    for doc in docs:
        for rule in doc.css_rules:
            if pattern.search(rule.selector) or pattern.search(rule.at):
                return True
    return False


def analyze(docs: list[Document], all_docs: list[Document]) -> list[Observation]:
    """State-coverage observations. ``all_docs`` includes the stylesheets."""
    out: list[Observation] = []

    painted, dark = _mode_surfaces(docs)
    if (len(painted) >= _MIN_SURFACES and dark
            and not _stylesheet_handles(all_docs, _CSS_DARK)):
        share = len(dark) / len(painted)
        if share < _DARK_COVERED_AT:
            missing = [pair for pair in painted if pair not in dark]
            out.append(Observation(
                axis=Axis.COLOR,
                id="color.partial_dark",
                title="Karanlık mod yarıda kalmış",
                detail=(
                    f"Renk taşıyan {len(painted)} elemanın yalnızca "
                    f"{len(dark)}'inde ({share * 100:.0f}%) bir dark: karşılığı "
                    f"var. Kalan {len(missing)} eleman karanlık temada açık "
                    f"renkte kalır: bu bir karanlık mod değil, karanlıkta "
                    f"kırılan bir sayfa. Yarım kapsama, hiç olmamasından daha "
                    f"kötüdür — kullanıcı modu açar ve arayüzün yarısını "
                    f"kaybeder."
                ),
                severity=round(min(1.0, 0.4 + (1.0 - share)), 3),
                stat=f"%{share * 100:.0f} kapsanmış",
                evidence=cap_evidence([evidence_for(d, e, " ".join(e.classes)[:60])
                                       for d, e in missing]),
                prescription=(
                    "Rengi eleman başına değil rol başına tanımla: paper / "
                    "shell / ink / rule tokenlarını iki mod için bir kez yaz, "
                    "sonra her yerde rolü çağır. Tek tek dark: eklemek her yeni "
                    "bileşende aynı boşluğu yeniden açar."
                ),
            ))

    every, focused = _controls(docs)
    if every and not _stylesheet_handles(all_docs, _CSS_FOCUS):
        share = len(focused) / len(every)
        stripped = [(d, e) for d, e in every
                    if any(c.endswith("outline-none") for c in e.classes)]
        # Two different defects, two different gates. Uneven coverage is a
        # distribution and needs a denominator worth dividing by; removing the
        # browser's own ring is a definite loss on the very first control it
        # happens to, so it is never waited out.
        partial = (focused and len(every) >= _MIN_CONTROLS
                   and share < _FOCUS_COVERED_AT)
        if partial or stripped:
            missing = [pair for pair in every if pair not in focused]
            reason = (
                f"{len(stripped)} tanesinde tarayıcının kendi odak halkası "
                f"outline-none ile kaldırılmış ve yerine bir şey konmamış. "
                if stripped else ""
            )
            out.append(Observation(
                axis=Axis.COLOR,
                id="color.partial_focus",
                title="Odak hâli yalnızca bazı kontrollerde var",
                detail=(
                    f"{len(every)} etkileşimli elemanın {len(focused)}'inde "
                    f"görünür bir odak hâli tanımlı. {reason}Klavyeyle gezen "
                    f"biri sayfanın neresinde olduğunu kaybeder; odak, "
                    f"erişilebilirlik eklentisi değil, arayüzün bir hâlidir ve "
                    f"diğerleri gibi tasarlanır."
                ),
                severity=round(min(1.0, 0.5 + (1.0 - share) / 2), 3),
                stat=f"{len(focused)}/{len(every)} odaklı",
                evidence=cap_evidence([evidence_for(d, e, e.tag) for d, e in
                                       (stripped or missing)]),
                prescription=(
                    "Tek bir odak reçetesi yaz (focus-visible:ring-2 "
                    "focus-visible:ring-offset-2 gibi) ve onu her kontrole "
                    "uygula. outline-none kullanacaksan yerine koyduğun şeyi "
                    "aynı sınıf listesinde yaz."
                ),
            ))

    return out
