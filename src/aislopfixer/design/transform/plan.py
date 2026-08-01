"""Turn a report and a derived system into a concrete list of edits.

Planning is separated from applying so the TUI can show the whole diff before a
single byte is written, and so the same plan can be re-derived after an undo.
Nothing here touches the filesystem.

Two rules constrain every edit produced:

* it rewrites the *value of a class attribute* and nothing else, so the file's
  structure is untouched and the result always parses;
* it is skipped when the class attribute is an expression (``className={cn(…)}``)
  rather than a plain string. Rewriting inside an expression would mean editing
  code, and a transform that can break a build is not one anybody will run
  twice. Those elements are counted and reported rather than silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..metrics.sections import classify
from ..models import Axis, DesignReport, Document, Element
from ..parse.expr import conditional_regions, is_conditional, rewritable
from ..system.derive import DesignSystem
from . import classmap
from .classmap import Context, rewrite, rewrite_tokens, spans_for

_GRID_MIN_CHILDREN = 2
_GRID_MAX_CHILDREN = 6


@dataclass
class Edit:
    """One class-attribute rewrite."""

    file: str
    abs_path: str
    start: int
    end: int
    old: str
    new: str
    line: int
    kind: str            # "token" | "rhythm" | "layout" | "type" | "material"
    note: str = ""
    # True only for the one documented exception to "class lists and nothing
    # else": the `<link>` / `@import` that makes the project load the emitted
    # token file. `transform.verify` excludes these rather than tolerating them
    # — an invariant with a carve-out inside it proves nothing.
    wiring: bool = False

    @property
    def key(self) -> str:
        return f"{self.file}:{self.start}"


@dataclass
class Plan:
    """Everything an apply run needs, plus what it deliberately left alone."""

    edits: list[Edit] = field(default_factory=list)
    skipped_expressions: int = 0
    # Classes welded to an interpolation (`py-${n}`). Not editable, and not
    # silently dropped either — the preview says how many there were.
    glued_tokens: int = 0
    files: set[str] = field(default_factory=set)

    def by_file(self) -> dict[str, list[Edit]]:
        out: dict[str, list[Edit]] = {}
        for e in self.edits:
            out.setdefault(e.abs_path, []).append(e)
        for group in out.values():
            group.sort(key=lambda e: e.start)
        return out

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.edits:
            out[e.kind] = out.get(e.kind, 0) + 1
        return out


def build(docs: list[Document], report: DesignReport,
          system: DesignSystem, *, axes: set[Axis] | None = None) -> Plan:
    """Plan the rewrite of every markup document."""
    plan = Plan()
    for doc in docs:
        if doc.kind != "markup" or not doc.elements:
            continue
        _plan_document(doc, system, plan, axes)
    return plan


def _plan_document(doc: Document, system: DesignSystem, plan: Plan,
                   axes: set[Axis] | None) -> None:
    contexts = _contexts(doc, system)
    for i, el in enumerate(doc.elements):
        ctx = contexts.get(i)
        if ctx is None:
            continue
        if el.class_span is None:
            if ctx.span or ctx.full_bleed:
                plan.skipped_expressions += 1
            continue
        raw = doc.text[el.class_span[0]:el.class_span[1]]
        if raw.lstrip().startswith(("{", "[")):
            _plan_expression(doc, el, ctx, system, plan, axes, raw)
            continue
        # Only what this attribute itself says. A Svelte `class:active={on}`
        # contributes to the measurement but must not be copied into the static
        # list, or the rewrite would turn a conditional class into a permanent
        # one — a change to behaviour, from a transform that promises not to.
        new_classes = rewrite(el.attr_classes, ctx, system)
        new_value = " ".join(new_classes)
        if new_value == raw.strip():
            continue
        kind, note = _describe(el, ctx, el.attr_classes, new_classes)
        if axes is not None and _AXIS_OF[kind] not in axes:
            continue
        plan.edits.append(Edit(
            file=doc.rel_path, abs_path=doc.abs_path,
            start=el.class_span[0], end=el.class_span[1],
            old=raw, new=new_value, line=el.line, kind=kind, note=note,
        ))
        plan.files.add(doc.rel_path)


def _plan_expression(doc: Document, el: Element, ctx: Context,
                     system: DesignSystem, plan: Plan,
                     axes: set[Axis] | None, raw: str) -> None:
    """Rewrite the class *literals* inside a ``className={…}`` expression.

    The expression's structure is never touched: each edit replaces a run of
    plain class text that already sits in the file, so the result parses for
    exactly the reason it did before. Two things make it safe to do at all:

    * a token glued to an interpolation is not offered as a span, so no
      ``py-${n}`` is ever half-rewritten;
    * classes the element *gains* only go into a span that always renders. If
      every literal is inside a branch, the element is left alone and counted —
      putting a layout fix behind ``open &&`` would fix one state of the UI and
      quietly break the rest.
    """
    base = el.class_span[0]
    found = rewritable(raw)
    spans = found.spans
    plan.glued_tokens += found.glued
    if not spans:
        plan.skipped_expressions += 1
        return

    groups = [raw[a:b].split() for a, b in spans]
    old_classes = [token for group in groups for token in group]
    mapped, extras = rewrite_tokens(old_classes, ctx, system)

    regions = conditional_regions(raw)
    host = next((i for i, (a, b) in enumerate(spans)
                 if not is_conditional(a, b, regions)), -1)
    if extras and host < 0:
        plan.skipped_expressions += 1
        return

    # The same resolution ``rewrite`` applies to a plain attribute, applied
    # across *every* literal of the expression: a `dark:` in one branch and its
    # base in another still reach the same element, so a duplicate or a variant
    # that overrides nothing is no less nonsense for being written twice.
    per_span: list[list[str]] = []
    seen: set[str] = set()
    cursor = 0
    for i in range(len(spans)):
        tokens: list[str] = []
        for _ in groups[i]:
            for token in mapped[cursor]:
                if token not in seen:
                    seen.add(token)
                    tokens.append(token)
            cursor += 1
        if i == host:
            for extra in extras:
                if extra not in seen:
                    seen.add(extra)
                    tokens.append(extra)
        per_span.append(tokens)
    # Two branches of the same ternary never reach the element together:
    # `cn(reverse ? "lg:order-2" : "lg:order-1")` is one decision written twice,
    # not a fight, and resolving them against each other emptied one branch. So
    # a conditional span is resolved against the *unconditional* text only.
    installed = classmap.installed(old_classes, mapped, extras)
    conditional = [is_conditional(a, b, regions) for a, b in spans]
    always = [t for i, tokens in enumerate(per_span) if not conditional[i]
              for t in tokens]
    kept_always = set(classmap.resolve(always, installed))

    edits: list[Edit] = []
    new_classes: list[str] = []
    for i, (a, b) in enumerate(spans):
        kept = (set(classmap.resolve(always + per_span[i], installed))
                if conditional[i] else kept_always)
        tokens = [t for t in per_span[i] if t in kept]
        new_classes.extend(tokens)
        new_value = " ".join(tokens)
        if new_value == raw[a:b]:
            continue
        edits.append(Edit(
            file=doc.rel_path, abs_path=doc.abs_path,
            start=base + a, end=base + b, old=raw[a:b], new=new_value,
            line=el.line, kind="token", note="",
        ))
    if not edits:
        return

    kind, note = _describe(el, ctx, old_classes, new_classes)
    if axes is not None and _AXIS_OF[kind] not in axes:
        return
    for edit in edits:
        edit.kind, edit.note = kind, note
    plan.edits.extend(edits)
    plan.files.add(doc.rel_path)


_AXIS_OF = {
    "token": Axis.COLOR,
    "type": Axis.TYPE,
    "rhythm": Axis.SPACE,
    "layout": Axis.LAYOUT,
    "material": Axis.MATERIAL,
}


def _describe(el: Element, ctx: Context, old: list[str],
              new: list[str]) -> tuple[str, str]:
    """Classify an edit by the most consequential thing it changed."""
    gone, came = set(old) - set(new), set(new) - set(old)
    if ctx.full_bleed or ctx.span or ctx.grid_children or "text-center" in gone:
        return "layout", "Yerleşim: simetri/hizalama kırıldı"
    if any(c.startswith(("py-band", "pt-band", "pb-band", "max-w-")) for c in came):
        return "rhythm", "Ritim: bölüm rolüne göre bant ve ölçü"
    if any(c.startswith(("text-display", "text-section", "text-title",
                         "text-lead", "text-body", "text-meta")) for c in came):
        return "type", "Tipografi: rol tabanlı ölçek, ayarlanmış display"
    if any(c.startswith(("shadow-", "rounded-")) for c in came) or \
            any(c.startswith("shadow-") for c in gone):
        return "material", "Malzeme: yükseklik ve biçim dili"
    return "token", "Renk: sistem rolleri"


def _contexts(doc: Document, system: DesignSystem) -> dict[int, Context]:
    """Build a :class:`Context` for every element worth rewriting."""
    out: dict[int, Context] = {}
    section_of = _section_membership(doc)
    roles = {idx: classify(doc, idx) for idx in doc.sections}
    hero = next((i for i, r in roles.items() if r == "hero"), -1)

    bands = {_band_element(doc, idx) for idx in doc.sections}
    containers = {i for i, el in enumerate(doc.elements) if _is_container(el)}
    grids = _grids(doc)
    spans: dict[int, int] = {}
    grid_children: dict[int, int] = {}
    for order, (gi, children) in enumerate(grids):
        pattern = spans_for(len(children), order)
        grid_children[gi] = len(children)
        for child, width in zip(children, pattern):
            spans[child] = width

    bleed = _bleed_candidate(doc, section_of, roles)

    for i, el in enumerate(doc.elements):
        if not el.classes and i not in spans and i != bleed:
            continue
        sec = section_of.get(i, -1)
        out[i] = Context(
            tag=el.tag,
            section_role=roles.get(sec, ""),
            is_band=i in bands,
            is_container=i in containers,
            is_hero=sec == hero,
            grid_children=grid_children.get(i, 0),
            grid_index=next((o for o, (gi, _) in enumerate(grids) if gi == i), 0),
            span=spans.get(i, 0),
            full_bleed=i == bleed,
            on_accent=_on_accent(el),
        )
    return out


def _section_membership(doc: Document) -> dict[int, int]:
    """``{element index: index of the section it lives in}``."""
    out: dict[int, int] = {}
    for idx in doc.sections:
        stack = [idx]
        while stack:
            i = stack.pop()
            out.setdefault(i, idx)
            stack.extend(doc.elements[i].children)
    return out


# Only a block-level wrapper can be a band. A nav's `<a class="px-4 py-2">` sits
# exactly where the search would otherwise stop, and turning a button's padding
# into a section rhythm token is a visible bug in the output, not a near miss.
_BAND_TAGS = frozenset({
    "section", "div", "header", "footer", "main", "article", "aside", "nav",
})


def _band_element(doc: Document, idx: int) -> int:
    """The element inside a section that actually carries the band padding."""
    frontier = [(idx, 0)]
    while frontier:
        i, depth = frontier.pop(0)
        el = doc.elements[i]
        if el.tag in _BAND_TAGS and any(
                d.axis is Axis.SPACE and not d.variant and
                d.prop in ("padding-y", "padding", "padding-top", "padding-bottom")
                for d in el.decls):
            return i
        if depth < 3:
            frontier.extend((c, depth + 1) for c in el.children[:2])
    return idx


def _is_container(el: Element) -> bool:
    has_measure = any(d.axis is Axis.LAYOUT and d.prop == "max-width"
                      for d in el.decls)
    centred = any(d.prop == "margin-x" and d.value == "auto" for d in el.decls)
    return has_measure and centred


def _grids(doc: Document) -> list[tuple[int, list[int]]]:
    """Symmetric grids and their element children, in document order.

    Only *symmetric* grids are collected: a grid whose children already carry
    different spans was laid out deliberately, and rewriting it would replace a
    decision with a default — the exact move this tool exists to undo.
    """
    out: list[tuple[int, list[int]]] = []
    for i, el in enumerate(doc.elements):
        cols = [d for d in el.decls if d.axis is Axis.LAYOUT and d.prop == "grid-cols"]
        if not cols:
            continue
        children = [c for c in el.children]
        if not (_GRID_MIN_CHILDREN <= len(children) <= _GRID_MAX_CHILDREN):
            continue
        if any(any(d.prop in ("col-span", "col-start") for d in doc.elements[c].decls)
               for c in children):
            continue
        out.append((i, children))
    return out


def _bleed_candidate(doc: Document, section_of: dict[int, int],
                     roles: dict[int, str]) -> int:
    """The one element per page promoted to a full-width break.

    A page needs the break to have any rhythm at all, but it needs exactly one:
    two full-bleed bands in a row is not a break, it is a new uniformity. The
    pick is the first full-width image inside a content section, because that
    is the element whose meaning improves most by escaping the measure.

    "Exactly one" has to be checked against the page as it *is*, not only
    within one run. The candidate is found by its ``w-full``, and the rewrite
    drops that ``w-full`` because it fights the ``w-screen`` it installs — so a
    second pass walked to the *next* full-width element and broke that one too.
    Each run bled one more band, which is a page that gets worse every time the
    tool is run on it.

    A band that is *already* broken stays the answer rather than becoming no
    answer: it is still the page's one break, and forgetting that turned its
    ``max-w-none`` back into a measure on the next pass and its measure back
    into ``max-w-none`` on the one after.
    """
    already = next((i for i, el in enumerate(doc.elements)
                    if _already_bleeding(el)), -1)
    if already >= 0:
        return already
    for i, el in enumerate(doc.elements):
        if el.tag not in ("img", "figure", "video", "picture"):
            continue
        if not any(d.prop == "width" and d.value == "full" for d in el.decls):
            continue
        sec = section_of.get(i, -1)
        if roles.get(sec) in ("nav", "footer"):
            continue
        return i
    return -1


_BLEED_MARKS = ("w-screen", "-translate-x-1/2")


def _already_bleeding(el: Element) -> bool:
    """True for an element the transform has already let out to full width."""
    return all(mark in el.classes for mark in _BLEED_MARKS)


def _on_accent(el: Element) -> bool:
    """True when this element paints an accent surface under its own text."""
    for d in el.decls:
        if d.axis is not Axis.COLOR or d.prop != "background":
            continue
        family = d.value.split("/")[0].rsplit("-", 1)[0]
        if family in classmap.ACCENT_FAMILIES or d.value.startswith("accent"):
            return True
    return False
