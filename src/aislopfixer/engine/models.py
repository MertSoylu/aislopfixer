"""Core data models for the detection engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def rank(self) -> int:
        return {"info": 0, "warning": 1, "error": 2}[self.value]


class Category(Enum):
    SECURITY = "Security"
    AI_LEAK = "AI Leak"
    PLACEHOLDER = "Placeholder"
    BUZZWORD = "Buzzword"
    DUPLICATE = "Duplicate"
    ACCESSIBILITY = "Accessibility"
    CODE_SLOP = "Code Slop"
    DESIGN = "Design"


class Fixability(Enum):
    AUTO = "auto"      # safe to delete/replace without user input
    PROMPT = "prompt"  # needs a user-supplied value
    MANUAL = "manual"  # flag only, cannot be auto-fixed


class Impact(Enum):
    """What *kind of work* a finding is, independent of how it is fixed.

    ``Fixability`` says *how* (auto / ask for a value / by hand); ``Impact``
    says *what is at stake*. Both an SQL injection and the word "seamless" are
    ``MANUAL``, and treating them alike is what buries the real defects among
    the nits. ``BROKEN`` + ``RISKY`` are the "application problems" a coding
    agent should be pointed at; ``POLISH`` is the simple-warning tail.

    Assigned centrally from a ``rule_id`` prefix table — see
    :data:`engine.scoring.IMPACT_OVERRIDE`. Rules never set it themselves.
    """

    BROKEN = "broken"  # the code does not work / is incomplete — a ship blocker
    RISKY = "risky"    # it runs, but ships a real hazard (security, fake data)
    POLISH = "polish"  # taste: voice, aesthetics, tidiness — a simple warning

    @property
    def rank(self) -> int:
        return {"polish": 0, "risky": 1, "broken": 2}[self.value]

    @property
    def is_application(self) -> bool:
        """True for the findings worth a coding agent's attention."""
        return self is not Impact.POLISH


class Status(Enum):
    OPEN = "open"
    FIXED = "fixed"
    SKIPPED = "skipped"
    ANNOTATED = "annotated"
    IGNORED = "ignored"   # user marked as not-slop; suppressed now and in future scans


@dataclass
class SourceFile:
    """A text source file fed to the rules."""

    abs_path: str
    rel_path: str
    text: str


@dataclass
class Finding:
    """A single detected issue in a source file."""

    rule_id: str
    category: Category
    severity: Severity
    message: str
    file: str          # relative path
    abs_path: str
    line: int          # 1-based
    col: int           # 1-based
    start: int         # absolute char offset (inclusive)
    end: int           # absolute char offset (exclusive)
    snippet: str
    matched_text: str
    fixability: Fixability = Fixability.MANUAL
    suggested_fix: str = ""
    replacement: str = ""               # AUTO: text to put in place of the span
    replace_template: str | None = None  # PROMPT: "href=\"{value}\"" style template
    prompt_label: str | None = None
    status: Status = Status.OPEN
    confidence: float = 0.0  # 0..1, backfilled by the runner via engine.scoring
    pinned: bool = False     # rule fixed the confidence itself; scoring won't touch it

    @property
    def key(self) -> str:
        """Stable identifier for UI node keys."""
        return f"{self.file}:{self.start}:{self.rule_id}"

    @property
    def impact(self) -> Impact:
        """What kind of work this finding is — see :class:`Impact`.

        Derived, not stored: unlike ``confidence`` (which rules may pin and
        which scoring corroborates and demotes), impact is a fixed property of
        the rule itself and nothing ever adjusts it per finding. Computing it
        on read means it can never be stale or forgotten on a hand-built
        Finding. Imported lazily — ``scoring`` imports this module.
        """
        from .scoring import impact_of

        return impact_of(self.rule_id)
