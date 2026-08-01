"""Shared statistics and evidence helpers for the metric modules.

Every metric in this package answers the same shape of question — "how
concentrated is this distribution?" — so the concentration measures live here
once. :func:`dominant_share` is the workhorse: a design where 18 of 20 sections
carry the same vertical padding is not a design, and that ratio is the number
that says so.
"""

from __future__ import annotations

import math
from collections import Counter

from ..models import Document, Element, Evidence


def dominant_share(values: list[str]) -> tuple[str, float]:
    """``(most common value, its share)``; ``("", 0.0)`` for an empty list."""
    if not values:
        return "", 0.0
    counts = Counter(values)
    value, n = counts.most_common(1)[0]
    return value, n / len(values)


def entropy(values: list[str]) -> float:
    """Shannon entropy in bits — 0 when every value is the same."""
    if len(values) < 2:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def normalized_entropy(values: list[str]) -> float:
    """Entropy scaled to 0..1 against a uniform distribution of the same size."""
    counts = Counter(values)
    if len(counts) < 2:
        return 0.0
    return entropy(values) / math.log2(len(counts))


def coefficient_of_variation(numbers: list[float]) -> float:
    """Std / mean — how much a set of lengths actually varies.

    Used on word counts: generated card copy clusters hard around one length,
    hand-written copy does not, and the ratio is scale-free so a 4-word and a
    40-word family can be compared.
    """
    vals = [n for n in numbers if n > 0]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    if mean == 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return math.sqrt(var) / mean


def snippet_at(text: str, start: int, end: int, width: int = 90) -> str:
    """A single trimmed source line around ``[start, end)``."""
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le == -1 else le
    line = text[ls:le].strip()
    if len(line) <= width:
        return line
    off = max(0, start - ls - width // 3)
    return ("…" if off else "") + line[off:off + width].strip() + "…"


def evidence_for(doc: Document, el: Element, value: str = "") -> Evidence:
    """Point evidence at an element's opening tag."""
    return Evidence(
        file=doc.rel_path,
        line=el.line,
        start=el.start,
        end=el.end,
        snippet=snippet_at(doc.text, el.start, el.end),
        value=value,
    )


def evidence_at(doc: Document, start: int, end: int, value: str = "") -> Evidence:
    line = 1 + doc.text.count("\n", 0, max(0, min(start, len(doc.text))))
    return Evidence(
        file=doc.rel_path,
        line=line,
        start=start,
        end=end,
        snippet=snippet_at(doc.text, start, end),
        value=value,
    )


def styled_decls(doc: Document):
    """``(Decl, Evidence)`` for every CSS-in-JS declaration in a document.

    A ``styled.div`…` `` block is authored design work that lives in neither
    ``el.decls`` nor ``doc.css_rules``: the usages carry it as ``inherited`` and
    the file is markup, not a stylesheet. Every metric that walks "all the
    declarations in the project" has to come through here or it will report a
    CSS-in-JS project as having declared nothing.
    """
    for sd in doc.styled:
        ev = Evidence(
            file=doc.rel_path,
            line=sd.line,
            start=sd.start,
            end=sd.start + len(sd.name),
            snippet=snippet_at(doc.text, sd.start, sd.start + len(sd.name)),
            value="",
        )
        for d in sd.decls:
            yield d, Evidence(ev.file, ev.line, ev.start, ev.end, ev.snippet,
                              d.raw or d.value)


def cap_evidence(items: list[Evidence], limit: int = 8) -> list[Evidence]:
    """Keep the report readable — the first few places are the argument.

    Deliberately not a silent truncation of the *measurement*: the counts in an
    observation's ``stat`` always come from the full set, only the displayed
    locations are capped.
    """
    return items[:limit]


def base_decls(el: Element, axis, prop: str) -> list[str]:
    """Values of an element's unvarianted declarations for one prop.

    Responsive and state variants are excluded on purpose: ``md:py-32`` is a
    different decision than ``py-20``, and mixing them into a rhythm
    distribution would hide a page that is uniform at every breakpoint.
    """
    return [
        d.value for d in el.decls
        if d.axis is axis and d.prop == prop and not d.variant
    ]
