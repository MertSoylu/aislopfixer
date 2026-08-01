"""Apply a derived system to a project's source, reversibly.

Split three ways on purpose: :mod:`classmap` decides what one class list should
become, :mod:`plan` walks the project and turns that into a reviewable list of
edits, and :mod:`apply` is the only place that writes. Nothing outside
:mod:`apply` touches the filesystem, so a plan can be built, shown, filtered by
axis and thrown away at no cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Axis, DesignReport, Document
from ..system.derive import DesignSystem
from ..system.emit import write_system
from .apply import ApplyResult, apply_plan, diff_for, plan_diff, undo
from .plan import Edit, Plan, build
from .verify import Verification, Violation, check
from .wire import plan_wiring

__all__ = [
    "Edit", "Plan", "ApplyResult", "TransformResult", "Verification",
    "Violation",
    "build", "plan_all", "apply_plan", "diff_for", "plan_diff", "undo", "run",
    "preview", "check",
]


@dataclass
class TransformResult:
    """The outcome of a full transform run, including its undo state."""

    plan: Plan
    applied: ApplyResult
    system_files: list[str] = field(default_factory=list)


def plan_all(root: str, docs: list[Document], report: DesignReport,
             system: DesignSystem, *, axes: set[Axis] | None = None) -> Plan:
    """The class rewrites plus the wiring edits, as one plan."""
    plan = build(docs, report, system, axes=axes)
    wiring = plan_wiring(root, docs)
    plan.edits.extend(wiring.edits)
    plan.files |= wiring.files
    return plan


def preview(root: str, docs: list[Document], report: DesignReport,
            system: DesignSystem, *,
            axes: set[Axis] | None = None) -> DesignReport:
    """Measure what this transform *would* produce, without writing anything.

    Not a model of the transform — the transform itself, run in memory. The same
    :func:`plan_all` builds the same edits, the same :func:`apply_edits` produces
    the text each file would hold, and the whole thing goes back through the same
    parse-and-measure pipeline.

    The emitted token file is deliberately **not** counted. It lands under
    ``.aislopfixer/``, which the scanner skips like every other dot directory, so
    the re-scan after ``a`` does not see it either — and a preview that counted
    it would promise a score the next run cannot produce.

    There is nothing here that can drift from what :func:`run` does, because it
    *is* what :func:`run` does minus the write. That matters: the projection in
    ``analyze.priorities`` answers a different question — what a person closing
    one observation gets — and ``bench/impact.md`` measured it coming in at half
    the drop the transform actually produces. A number the tool shows next to its
    own ``a`` key has to be the tool's own arithmetic, not a forecast of it.
    """
    from pathlib import Path

    from ..analyze import analyze
    from ..parse import (load_theme, parse_document, resolve_components,
                         resolve_stylesheets)
    from ..parse.styles import resolve_styles
    from .apply import apply_edits, read_text

    plan = plan_all(root, docs, report, system, axes=axes)
    rewritten: dict[str, str] = {}
    for abs_path, edits in plan.by_file().items():
        try:
            text, _newline, _bom = read_text(Path(abs_path))
        except (OSError, UnicodeDecodeError):
            continue
        rewritten[abs_path] = apply_edits(text, edits)

    sources = [
        _Source(d.rel_path, d.abs_path, rewritten.get(d.abs_path, d.text))
        for d in docs
    ]
    theme = load_theme(sources)
    fresh = [parse_document(s.rel_path, s.abs_path, s.text, theme)
             for s in sources]
    # Same order as `project.load_documents`. A step missing here is a preview
    # that promises a score the next scan cannot produce, which is the one
    # thing this function exists not to do — `bench/impact.md` caught the
    # stylesheet step missing as a 0.7-point drift on `clean_css`.
    resolve_styles(fresh)
    resolve_stylesheets(fresh)
    resolve_components(fresh)
    return analyze(root, fresh)


@dataclass(frozen=True)
class _Source:
    """The shape :func:`load_theme` and :func:`parse_document` both accept."""

    rel_path: str
    abs_path: str
    text: str


def run(root: str, docs: list[Document], report: DesignReport,
        system: DesignSystem, *, axes: set[Axis] | None = None,
        write_tokens: bool = True) -> TransformResult:
    """Emit the system, rewrite the source, and return everything undo needs."""
    plan = plan_all(root, docs, report, system, axes=axes)
    written = write_system(root, system) if write_tokens else []
    applied = apply_plan(plan)
    applied.written.extend(written)
    return TransformResult(plan=plan, applied=applied, system_files=written)
