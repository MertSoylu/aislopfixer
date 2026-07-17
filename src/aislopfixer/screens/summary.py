"""Final summary screen with animated category bars and next-step navigation."""

from __future__ import annotations

from collections import Counter

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static

from .base import AdaptiveScreen
from ..engine.models import Category, Finding, Status
from ..engine.scoring import project_score_from_findings
from ..theme import (
    ACCENT,
    BAD,
    BG,
    BORDER_MID,
    CATEGORY_COLORS,
    CATEGORY_ICON,
    DIM,
    FAINT,
    OK,
    TEXT,
    WARN,
)
from ..widgets import CountUp

_BAR_WIDTH = 28
_WARN = WARN


class CatBar(Static):
    """A category row whose bar fills up on mount."""

    DEFAULT_CSS = "CatBar { height: 1; }"

    frac: reactive[float] = reactive(0.0)

    def __init__(self, cat: Category, found: int, fixed: int, max_found: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cat = cat
        self._found = found
        self._fixed = fixed
        self._target = (found / max_found) if max_found else 0.0

    def on_mount(self) -> None:
        self.animate("frac", self._target, duration=0.8, easing="out_cubic")

    def watch_frac(self) -> None:
        self.refresh()

    def render(self) -> Text:
        color = CATEGORY_COLORS[self._cat]
        filled = int(self.frac * _BAR_WIDTH)
        t = Text()
        t.append(f"{CATEGORY_ICON[self._cat]} ", style=color)
        t.append(f"{self._cat.value:<14}", style=color)
        t.append("█" * filled, style=color)
        t.append("░" * (_BAR_WIDTH - filled), style=BORDER_MID)
        t.append(f"  {self._fixed}/{self._found}", style=DIM)
        return t


class SummaryScreen(AdaptiveScreen):
    MIN_WIDTH = 72
    MIN_HEIGHT = 21

    BINDINGS = [
        ("b", "back", "Back to findings"),
        ("r", "rescan", "Scan again"),
        ("n", "new_folder", "New folder"),
        ("q", "quit", "Quit"),
        ("escape", "quit", "Quit"),
    ]

    def __init__(self, findings: list[Finding]) -> None:
        super().__init__()
        self._findings = findings

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        found = len(self._findings)
        fixed = sum(1 for f in self._findings if f.status in (Status.FIXED, Status.ANNOTATED))
        skipped = sum(1 for f in self._findings if f.status in (Status.SKIPPED, Status.IGNORED))
        remaining = found - fixed - skipped

        per_found = Counter(f.category for f in self._findings)
        per_fixed = Counter(
            f.category for f in self._findings
            if f.status in (Status.FIXED, Status.ANNOTATED)
        )
        max_found = max(per_found.values(), default=0)

        self._slop = round(project_score_from_findings(self._findings) * 100)

        with Vertical(id="summary-box"):
            yield Static("✦  SCAN SUMMARY", id="summary-title")
            yield Static(self._target_line(), id="summary-target")
            yield Static(self._slop_line(self._slop), id="summary-slop")
            yield Static(self._impact_line(), id="summary-sev")
            with Horizontal(id="summary-counters"):
                yield CountUp("Found", ACCENT, id="s-found", classes="rc")
                yield CountUp("Fixed", OK, id="s-fixed", classes="rc")
                yield CountUp("Skipped", DIM, id="s-skip", classes="rc")
                yield CountUp("Remaining", _WARN, id="s-left", classes="rc")
            yield Static("BY CATEGORY", id="summary-cat-title")
            with Vertical(id="summary-bars"):
                for cat in Category:
                    if per_found.get(cat):
                        yield CatBar(cat, per_found[cat], per_fixed.get(cat, 0), max_found)
            yield Static(self._status_line(remaining), id="summary-status")
            yield Static(self._tip_line(remaining), id="summary-tip")
            yield Static(self._menu_line(), id="summary-menu")

        self._totals = (found, fixed, skipped, remaining)

    def _target_line(self) -> Text:
        t = Text(justify="center", no_wrap=True, overflow="ellipsis")
        target = getattr(self.app, "target_path", None)
        if target:
            t.append(str(target), style=FAINT)
        return t

    def _impact_line(self) -> Text:
        """The same split the results screen and the fix brief lead on.

        This used to be a severity breakdown ("▲ 13 warnings  ■ 28 infos").
        Over the same findings the results header said "10 application
        problem(s) · 31 simple warning(s)", so the last screen of the flow —
        the one worth screenshotting — quietly changed axis and disagreed with
        the screen before it: 10 ≠ 13, 31 ≠ 28, with nothing to explain why.
        """
        t = Text(justify="center")
        if not self._findings:
            return t
        problems = sum(1 for f in self._findings if f.impact.is_application)
        warnings = len(self._findings) - problems
        if problems:
            t.append("▲ ", style=_WARN)
            t.append(f"{problems} application problem(s)", style=f"bold {_WARN}")
            t.append(" (broken or risky)", style=FAINT)
        else:
            t.append("✓ ", style=OK)
            t.append("no application problems", style=f"bold {OK}")
        if warnings:
            t.append("    ·    ", style=FAINT)
            t.append(f"{warnings} simple warning(s)", style=DIM)
        return t

    def _slop_line(self, slop: int) -> Text:
        color = BAD if slop >= 75 else _WARN if slop >= 45 else OK
        t = Text(justify="center")
        t.append("SLOP SCORE  ", style=f"bold {DIM}")
        t.append(f"{slop}", style=f"bold {color}")
        t.append("/100", style=DIM)
        return t

    def _status_line(self, remaining: int) -> Text:
        t = Text(justify="center")
        if not self._findings:
            t.append("Nothing to fix — this project is clean. ✦", style=OK)
        elif remaining == 0:
            t.append("All issues handled. ✓", style=OK)
        else:
            t.append(f"{remaining} issue(s) still open — ", style=_WARN)
            t.append("scan again any time.", style=DIM)
        return t

    def _tip_line(self, remaining: int) -> Text:
        """Where the report went; how to hand the leftovers to an AI assistant.

        Kept under ~66 columns — the box's inner width at the size the README
        screenshots use. The line is ``no_wrap``, so the old wording (101 chars)
        was chopped to "…b back, then x" and ended on a bare key nobody could
        act on.
        """
        t = Text(justify="center", no_wrap=True, overflow="ellipsis")
        t.append("report: .aislopfixer/report.md", style=FAINT)
        if remaining:
            t.append("  ·  ", style=FAINT)
            t.append("b", style=f"bold {ACCENT}")
            t.append(" back, then ", style=DIM)
            t.append("x", style=f"bold {ACCENT}")
            t.append(" for a fix brief", style=DIM)
        return t

    def _menu_line(self) -> Text:
        t = Text(justify="center")

        def opt(k: str, label: str, last: bool = False) -> None:
            t.append(f" {k} ", style=f"bold {BG} on {ACCENT}")
            t.append(f" {label}", style=TEXT)
            if not last:
                t.append("        ", style=DIM)

        opt("B", "Back")
        opt("R", "Scan again")
        opt("N", "New folder")
        opt("Q", "Quit", last=True)
        return t

    def on_mount(self) -> None:
        box = self.query_one("#summary-box")
        box.border_title = "AISLOPFIXER"
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.5)
        found, fixed, skipped, remaining = self._totals
        self.query_one("#s-found", CountUp).set_target(found)
        self.query_one("#s-fixed", CountUp).set_target(fixed)
        self.query_one("#s-skip", CountUp).set_target(skipped)
        self.query_one("#s-left", CountUp).set_target(remaining)
        self.call_after_refresh(self._fit)

    def action_back(self) -> None:
        self.app.show_results(self._findings)

    def action_rescan(self) -> None:
        self.app.rescan()

    def action_new_folder(self) -> None:
        self.app.choose_new_folder()

    def action_quit(self) -> None:
        self.app.exit()
