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
    AI_LEAK = "AI Leak"
    PLACEHOLDER = "Placeholder"
    BUZZWORD = "Buzzword"
    DUPLICATE = "Duplicate"
    ACCESSIBILITY = "Accessibility"
    CODE_SLOP = "Code Slop"


class Fixability(Enum):
    AUTO = "auto"      # safe to delete/replace without user input
    PROMPT = "prompt"  # needs a user-supplied value
    MANUAL = "manual"  # flag only, cannot be auto-fixed


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

    @property
    def key(self) -> str:
        """Stable identifier for UI node keys."""
        return f"{self.file}:{self.start}:{self.rule_id}"
