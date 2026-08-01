"""Check the transform's *output*, not just that it ran.

Two things were already proven about a rewrite: the patch is ``git apply``-clean
and a second pass produces zero edits. Neither says the output is any good.
"a broken build was not produced" and "the page looks better" are different
claims, and the tool's entire argument rests on the second one.

So this module verifies the two claims a class-only transform can actually be
held to at repository scale:

* :func:`class_only` — **byte level**. Everything outside the class-attribute
  values is identical before and after: the element tree, the text, the
  whitespace, the line endings. The constraint is written into
  :mod:`.classmap`'s docstring and was never checked on anything larger than a
  fixture. ``daisyui`` takes 1741 edits in one run; a single mis-anchored span
  there would corrupt hundreds of elements and no test would see it.
* :func:`nonsense` — **semantic**. A class list can be structurally perfect and
  still say nothing: the same class twice, a variant that repeats the base it
  overrides, two ``max-w-`` fighting on one element. None of these break a
  build, which is exactly why nothing else catches them.

Neither function decides anything. They report, and the caller — a test, or
``bench.field`` — decides what a violation means.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..models import Document
from ..parse.expr import rewritable
from ..parse.markup import JS_EXTS, MARKUP_EXTS, parse_markup
from .apply import apply_edits
from .classmap import keyed as _keyed
from .plan import Plan

_MASK = "\x00"


def _class_spans(text: str, ext: str) -> list[tuple[int, int]]:
    """Every run of plain class text in ``text``, in order and non-overlapping.

    An expression attribute contributes its *literal runs* rather than the whole
    ``{…}``: masking the expression itself would hide a change to its structure,
    which is the one edit this module exists to catch.
    """
    spans: list[tuple[int, int]] = []
    for el in parse_markup(text, ext):
        if el.class_span is None:
            continue
        a, b = el.class_span
        raw = text[a:b]
        if raw.lstrip().startswith(("{", "[")):
            spans += [(a + x, a + y) for x, y in rewritable(raw).spans]
        else:
            spans.append((a, b))
    spans.sort()
    out: list[tuple[int, int]] = []
    for a, b in spans:
        if out and a < out[-1][1]:
            continue                      # nested/overlapping: keep the outer
        out.append((a, b))
    return out


def skeleton(text: str, ext: str) -> str:
    """``text`` with every class value replaced by one mask byte.

    Two files with the same skeleton differ **only** in what their class
    attributes say. Everything else — tags, attributes, text nodes, blank lines,
    indentation — compares byte for byte.
    """
    out: list[str] = []
    cursor = 0
    for a, b in _class_spans(text, ext):
        out.append(text[cursor:a])
        out.append(_MASK)
        cursor = b
    out.append(text[cursor:])
    return "".join(out)


@dataclass
class Violation:
    """One place the output failed a claim the tool makes about itself."""

    file: str
    kind: str            # "structure" | "duplicate" | "redundant" | "conflict"
    detail: str


@dataclass
class Verification:
    """What the checks found, and how much they looked at."""

    files: int = 0
    edits: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.violations

    def of(self, kind: str) -> list[Violation]:
        return [v for v in self.violations if v.kind == kind]

    @property
    def summary(self) -> str:
        if self.clean:
            return f"{self.files} dosya, {self.edits} düzenleme — temiz"
        counts = {}
        for v in self.violations:
            counts[v.kind] = counts.get(v.kind, 0) + 1
        return f"{self.files} dosya, {self.edits} düzenleme — " + ", ".join(
            f"{n} {kind}" for kind, n in sorted(counts.items()))


def class_only(docs: list[Document], plan: Plan) -> Verification:
    """Apply ``plan`` in memory and prove nothing but class lists moved.

    Wiring edits are excluded rather than tolerated: a ``<link>`` inserted
    before ``</head>`` really does change the tree, it is the one documented
    exception, and folding it into this check would make the check meaningless.
    """
    by_path = {d.abs_path: d for d in docs}
    out = Verification()
    for abs_path, edits in plan.by_file().items():
        doc = by_path.get(abs_path)
        if doc is None:
            continue
        rewrites = [e for e in edits if not e.wiring]
        if not rewrites:
            continue
        out.files += 1
        out.edits += len(rewrites)
        ext = os.path.splitext(doc.rel_path)[1].lower()
        if ext not in MARKUP_EXTS and ext not in JS_EXTS:
            out.violations.append(Violation(
                doc.rel_path, "structure",
                f"sınıf düzenlemesi işaretleme olmayan bir dosyada ({ext})"))
            continue
        after = apply_edits(doc.text, rewrites)
        before_skel, after_skel = skeleton(doc.text, ext), skeleton(after, ext)
        if before_skel != after_skel:
            out.violations.append(Violation(
                doc.rel_path, "structure",
                _first_difference(before_skel, after_skel)))
    return out


def _first_difference(a: str, b: str) -> str:
    """Where two skeletons stop agreeing, quoted — a diff nobody has to run."""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    line = 1 + a.count("\n", 0, i)
    return (f"{line}. satırda sınıf listesi dışında bir fark: "
            f"{a[i:i + 40]!r} → {b[i:i + 40]!r}")


def nonsense(docs: list[Document], plan: Plan) -> Verification:
    """Class lists the transform produced that say nothing, or two things.

    Read off the *rewritten* text rather than off the plan, so a list assembled
    from several edits in one expression is judged the way the browser will
    read it.
    """
    by_path = {d.abs_path: d for d in docs}
    out = Verification()
    for abs_path, edits in plan.by_file().items():
        doc = by_path.get(abs_path)
        if doc is None:
            continue
        rewrites = [e for e in edits if not e.wiring]
        if not rewrites:
            continue
        out.files += 1
        out.edits += len(rewrites)
        ext = os.path.splitext(doc.rel_path)[1].lower()
        if ext not in MARKUP_EXTS and ext not in JS_EXTS:
            continue
        after = apply_edits(doc.text, rewrites)
        for el in parse_markup(after, ext):
            for kind, detail in _judge(el.attr_classes):
                out.violations.append(
                    Violation(f"{doc.rel_path}:{el.line}", kind, detail))
    return out


def _judge(classes: list[str]) -> list[tuple[str, str]]:
    """The three ways one class list can be nonsense, in the browser's reading."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for cls in classes:
        if cls in seen:
            found.append(("duplicate", f"`{cls}` iki kez"))
        seen.add(cls)

    # `(variant, prop) → values`. Two values on one property at one breakpoint
    # is a fight the later class wins silently; the same `prop=value` written
    # both plain and behind a variant is a variant that overrides nothing.
    at: dict[tuple[str, str], set[str]] = {}
    for cls in dict.fromkeys(classes):
        keyed = _keyed(cls)
        if keyed is not None:
            at.setdefault(keyed[:2], set()).add(keyed[2])
    for (variant, prop), values in sorted(at.items()):
        if len(values) > 1:
            found.append(("conflict", f"{variant + ':' if variant else ''}{prop}"
                                      f": " + " / ".join(sorted(values))))
        if variant and values <= at.get(("", prop), set()):
            found.append(("redundant", f"{variant}:{prop} tabanla aynı değerde "
                                       f"({next(iter(values))})"))
    return found


def check(docs: list[Document], plan: Plan) -> Verification:
    """Both checks over one plan, as a single result."""
    structure = class_only(docs, plan)
    meaning = nonsense(docs, plan)
    return Verification(files=structure.files, edits=structure.edits,
                        violations=structure.violations + meaning.violations)


__all__ = ["Verification", "Violation", "check", "class_only", "nonsense",
           "skeleton"]
