"""Scanning screen: runs the engine in a thread and animates progress."""

from __future__ import annotations

import time

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import ProgressBar, Static

from .base import AdaptiveScreen
from ..engine.models import Category, Finding, SourceFile
from ..pipeline import scan_project
from ..scanner import count_eligible
from ..theme import ACCENT, CATEGORY_COLORS, CATEGORY_ICON, DIM, OK
from ..widgets import CountUp, ScanPulse, Spinner

_TEXT = "#cdd6f4"
_FAINT = "#5b647a"


class SetTotal(Message):
    def __init__(self, total: int) -> None:
        self.total = total
        super().__init__()


class FileDone(Message):
    def __init__(self, rel: str, findings: list[Finding]) -> None:
        self.rel = rel
        self.findings = findings
        super().__init__()


class CrossStart(Message):
    """Per-file pass finished; cross-file analysis is starting."""


class Done(Message):
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        super().__init__()


class Failed(Message):
    """The scan worker raised; carries the error text for display."""

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__()


class ScanScreen(AdaptiveScreen):
    MIN_WIDTH = 80
    MIN_HEIGHT = 20

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._total = 0
        self._done = 0
        self._found = 0
        self._t0 = 0.0
        self._counts: dict[Category, int] = {c: 0 for c in Category}

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        with Vertical(id="scan-box"):
            yield Static("◇  SCANNING PROJECT", id="scan-title")
            yield Static(self._path_line(), id="scan-target")
            yield Spinner("Indexing files…", id="scan-spinner")
            yield ProgressBar(total=100, show_eta=False, id="scan-prog")
            yield Static(self._count_line(), id="scan-count")
            yield ScanPulse(id="scan-pulse")
            yield Static("", id="scan-current")
            with Horizontal(id="scan-counters"):
                for cat in Category:
                    yield CountUp(
                        f"{CATEGORY_ICON[cat]} {cat.value}",
                        CATEGORY_COLORS[cat],
                        id=f"cat-{cat.name}",
                        classes="cat-counter",
                    )

    def _path_line(self) -> Text:
        t = Text(justify="center", no_wrap=True, overflow="ellipsis")
        t.append(str(self._path), style=DIM)
        return t

    def _count_line(self) -> Text:
        t = Text(justify="center")
        if not self._total:
            t.append("preparing…", style=_FAINT)
            return t
        pct = round(self._done / self._total * 100)
        t.append(f"{self._done}", style=f"bold {ACCENT}")
        t.append(f" / {self._total} files", style=DIM)
        t.append("   ·   ", style=_FAINT)
        t.append(f"{pct}%", style=_TEXT)
        t.append("   ·   ", style=_FAINT)
        found_color = "#fbbf24" if self._found else DIM
        t.append(f"{self._found} found", style=found_color)
        if self._t0:
            t.append("   ·   ", style=_FAINT)
            t.append(f"{time.monotonic() - self._t0:.0f}s", style=DIM)
        return t

    def on_mount(self) -> None:
        box = self.query_one("#scan-box")
        box.border_title = "◇ SCAN"
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.4)
        self._t0 = time.monotonic()
        self._clock = self.set_interval(0.5, self._tick_clock)
        self.call_after_refresh(self._fit)
        self._scan()

    def _tick_clock(self) -> None:
        if self._total:
            self.query_one("#scan-count", Static).update(self._count_line())

    @work(thread=True)
    def _scan(self) -> None:
        try:
            total = count_eligible(self._path)
            self.post_message(SetTotal(total))
            # spread tiny scans over ~1.2s so the animation is visible; ~0 for big repos
            delay = min(0.04, 1.2 / total) if total else 0.0

            def on_file(sf: SourceFile, file_findings: list[Finding]) -> None:
                self.post_message(FileDone(sf.rel_path, file_findings))
                if delay:
                    time.sleep(delay)

            findings = scan_project(
                self._path,
                store=getattr(self.app, "store", None),
                on_file=on_file,
                on_cross_start=lambda: self.post_message(CrossStart()),
            )
            self.post_message(Done(findings))
        except Exception as exc:  # noqa: BLE0001 — surface any engine failure to the UI
            self.post_message(Failed(f"{type(exc).__name__}: {exc}"))

    def on_set_total(self, message: SetTotal) -> None:
        self._total = message.total
        spinner = self.query_one("#scan-spinner", Spinner)
        if message.total == 0:
            spinner.set_label("No scannable files found.")
            self.query_one("#scan-current", Static).update(
                Text("This folder has nothing to scan.", style=_FAINT)
            )
        else:
            spinner.set_label(f"Scanning {message.total} files…")
        self.query_one("#scan-count", Static).update(self._count_line())

    def on_file_done(self, message: FileDone) -> None:
        self._done += 1
        if self._total:
            pct = self._done / self._total * 100
            self.query_one("#scan-prog", ProgressBar).update(progress=pct)
        self.query_one("#scan-count", Static).update(self._count_line())
        cur = Text(no_wrap=True, overflow="ellipsis")
        cur.append("› ", style=ACCENT)
        cur.append(message.rel, style=DIM)
        self.query_one("#scan-current", Static).update(cur)
        changed: set[Category] = set()
        for f in message.findings:
            self._counts[f.category] += 1
            self._found += 1
            changed.add(f.category)
        for cat in changed:
            self.query_one(f"#cat-{cat.name}", CountUp).set_target(self._counts[cat])

    def on_cross_start(self, message: CrossStart) -> None:
        if self._total:
            self.query_one("#scan-spinner", Spinner).set_label("Analyzing cross-file duplicates…")
            self.query_one("#scan-current", Static).update(
                Text("› comparing content across files", style=_FAINT)
            )

    def on_done(self, message: Done) -> None:
        self._clock.stop()
        self._found = len(message.findings)
        self.query_one("#scan-count", Static).update(self._count_line())
        self.query_one("#scan-prog", ProgressBar).update(progress=100)
        total = len(message.findings)
        spinner = self.query_one("#scan-spinner", Spinner)
        spinner.stop()
        done = Text()
        done.append("✓ ", style=f"bold {OK}")
        done.append(f"Scan complete — {total} issue(s) found", style=_TEXT)
        spinner.set_label(done)
        self.query_one("#scan-current", Static).update(
            Text("opening report…", style=_FAINT)
        )
        self.set_timer(0.8, lambda: self.app.show_results(message.findings))

    def on_failed(self, message: Failed) -> None:
        self._clock.stop()
        spinner = self.query_one("#scan-spinner", Spinner)
        spinner.stop()
        err = Text()
        err.append("✗ ", style="bold #f38ba8")
        err.append("Scan failed", style=_TEXT)
        spinner.set_label(err)
        detail = Text(no_wrap=True, overflow="ellipsis")
        detail.append(message.error, style="#f38ba8")
        self.query_one("#scan-current", Static).update(detail)
        # let the user out with whatever was collected (empty) rather than hang
        self.set_timer(2.0, lambda: self.app.show_results([]))
