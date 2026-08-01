"""Final summary: the two axes, before and after, and what is left to do.

The before/after line is the point of this screen. A tool that rewrites source
has to show what it changed the measurement to, or the user has no way to know
whether running it helped — and the numbers come from a genuine re-scan of the
files on disk, not from an estimate of what the edits should have done.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.reactive import reactive
from textual.widgets import Static

from .base import AdaptiveScreen
from ..design.models import Axis
from ..theme import (ACCENT, AXIS_COLORS, AXIS_ICON, BG, DIM, FAINT, OK, TEXT,
                     meter, score_color, sparkline)
from ..widgets import CountUp

_BAR_WIDTH = 26


class AxisBar(Static):
    """One axis row whose decision meter fills on mount."""

    DEFAULT_CSS = "AxisBar { height: 1; }"

    frac: reactive[float] = reactive(0.0)

    def __init__(self, axis: Axis, score, **kwargs) -> None:
        super().__init__(**kwargs)
        self._axis = axis
        self._score = score
        self._target = (score.decision_score / 100.0) if score else 0.0

    def on_mount(self) -> None:
        self.animate("frac", self._target, duration=0.8, easing="out_cubic")

    def watch_frac(self) -> None:
        self.refresh()

    def render(self) -> Text:
        colour = AXIS_COLORS[self._axis]
        filled = int(self.frac * _BAR_WIDTH)
        t = Text()
        t.append(f"{AXIS_ICON[self._axis]:<2} ", style=colour)
        t.append(f"{self._axis.label:<19}", style=TEXT)
        if self._score is None or not self._score.measured:
            t.append("kullanılmıyor", style=FAINT)
            return t
        t.append("█" * filled, style=colour)
        t.append("░" * (_BAR_WIDTH - filled), style=FAINT)
        t.append(f" {self._score.decision_score:>3.0f}", style=TEXT)
        t.append(f"  {self._score.verdict}", style=FAINT)
        return t


class SummaryScreen(AdaptiveScreen):
    MIN_WIDTH = 80
    MIN_HEIGHT = 22

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        report = self.app.report
        with Vertical(id="sum-box"):
            yield Static(self._headline(), id="sum-title")
            yield Static(self._delta(), id="sum-delta")
            yield Static(self._history(), id="sum-history")
            for axis in Axis:
                yield AxisBar(axis, report.axes.get(axis) if report else None)
            yield Static(self._remaining(), id="sum-remaining")
            yield Static(self._keys(), id="sum-keys")

    def on_mount(self) -> None:
        box = self.query_one("#sum-box")
        box.border_title = "◇ ÖZET"
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.4)
        self.call_after_refresh(self._fit)

    def _headline(self) -> Text:
        report = self.app.report
        t = Text(justify="center")
        if report is None:
            t.append("Rapor yok.", style=FAINT)
            return t
        colour = score_color(report.template_score)
        t.append("ŞABLON SKORU  ", style=DIM)
        t.append(f"{report.template_score:.0f}", style=f"bold {colour}")
        t.append("/100\n", style=FAINT)
        t.append(meter(report.template_score, 30), style=colour)
        t.append(f"\n{report.verdict}", style=colour)
        return t

    def _delta(self) -> Text:
        """Before/after, from the store's history — real re-scan numbers."""
        t = Text(justify="center")
        report = self.app.report
        if report is None:
            return t
        t.append(f"\nkarar {report.decision_density:.0f}", style=TEXT)
        t.append("   ·   ", style=FAINT)
        t.append(f"tekrar {report.repetition:.0f}", style=TEXT)
        applied = getattr(self.app, "applied_edits", 0)
        previous = getattr(self.app, "previous_run", None)
        if applied and previous and "template" in previous:
            # The run recorded just before the rewrite, not the oldest one on
            # file: crediting a transform with every improvement the project
            # ever made would be a nice number and a false one.
            t.append(
                f"\n{applied} düzenleme uygulandı — şablon "
                f"{float(previous['template']):.0f} → {report.template_score:.0f}",
                style=OK,
            )
        elif applied:
            t.append(f"\n{applied} düzenleme uygulandı", style=OK)
        return t

    def _history(self) -> Text:
        """The last ten runs as one line — is this project getting better?"""
        t = Text(justify="center")
        store = getattr(self.app, "store", None)
        runs = [h for h in (store.history if store else []) if "template" in h]
        if len(runs) < 2:
            return t
        recent = runs[-10:]
        scores = [float(h["template"]) for h in recent]
        t.append(f"\nson {len(recent)} çalıştırma  ", style=DIM)
        t.append(sparkline(scores), style=ACCENT)
        t.append(f"  {scores[0]:.0f} → {scores[-1]:.0f}", style=FAINT)
        return t

    def _remaining(self) -> Text:
        report = self.app.report
        t = Text()
        if report is None:
            return t
        store = getattr(self.app, "store", None)
        accepted = store.accepted if store else set()
        live = [o for o in report.observations
                if o.key not in accepted and o.severity >= 0.4]
        t.append("\nKALAN İŞ\n", style=f"bold {DIM}")
        if not live:
            t.append("  Sınıf düzeyinde çözülemeyen bir şey kalmadı.\n", style=OK)
            return t
        for obs in live[:5]:
            t.append(f"  · {obs.title}", style=TEXT)
            t.append(f" — {obs.stat}\n", style=FAINT)
        if len(live) > 5:
            t.append(f"  · …{len(live) - 5} gözlem daha\n", style=FAINT)
        t.append("  Tam reçete için raporda x tuşu (.aislopfixer/brief.md)\n",
                 style=FAINT)
        return t

    def _keys(self) -> Text:
        t = Text(justify="center")
        for key, label in (("b", "rapora dön"), ("r", "yeniden tara"),
                           ("n", "başka klasör"), ("q", "çık")):
            t.append(f" {key} ", style=f"bold {BG} on {ACCENT}")
            t.append(f" {label}    ", style=DIM)
        return t

    def on_key(self, event: Key) -> None:
        if event.key == "b":
            from .report import ReportScreen

            self.app.switch_screen(ReportScreen())
        elif event.key == "r":
            self.app.rescan()
        elif event.key == "n":
            self.app.choose_new_folder()
        elif event.key in ("q", "escape"):
            self.app.exit()
