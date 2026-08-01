"""Score the corpus and report where each case landed against its band."""

from __future__ import annotations

from dataclasses import dataclass

from aislopfixer.design.project import scan_project

from .cases import CASES, Case


@dataclass
class Outcome:
    case: Case
    template: float
    decisions: float
    repetition: float
    fired: set[str]

    @property
    def missing(self) -> list[str]:
        return [o for o in self.case.must_observe if o not in self.fired]

    @property
    def spurious(self) -> list[str]:
        return [o for o in self.case.must_not_observe if o in self.fired]

    @property
    def in_band(self) -> bool:
        lo, hi = self.case.template
        dlo, dhi = self.case.decisions
        return lo <= self.template <= hi and dlo <= self.decisions <= dhi

    @property
    def ok(self) -> bool:
        return self.in_band and not self.missing and not self.spurious


def evaluate(case: Case) -> Outcome:
    report, _ = scan_project(case.path)
    return Outcome(
        case=case,
        template=report.template_score,
        decisions=report.decision_density,
        repetition=report.repetition,
        fired={o.id for o in report.observations},
    )


def run() -> list[Outcome]:
    return [evaluate(c) for c in CASES]


def twin_gaps(outcomes: list[Outcome]) -> list[tuple[str, str, float]]:
    """``(case, twin, template-score gap)`` for every declared twin pair.

    Two cases that are the same design in different stacks must score the same;
    the gap between them measures how much of the score is about the framework
    rather than the design.
    """
    by_name = {o.case.name: o for o in outcomes}
    out: list[tuple[str, str, float]] = []
    for o in outcomes:
        twin = by_name.get(o.case.twin_of)
        if twin is not None:
            out.append((o.case.name, twin.case.name,
                        abs(o.template - twin.template)))
    return out
