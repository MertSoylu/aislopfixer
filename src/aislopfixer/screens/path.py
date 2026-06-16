"""Target-folder selection screen."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Static

from .base import AdaptiveScreen
from ..theme import DIM, OK

_BAD = "#f87171"
_FAINT = "#5b647a"


class PathScreen(AdaptiveScreen):
    MIN_WIDTH = 64
    MIN_HEIGHT = 13

    BINDINGS = [("escape", "quit", "Quit")]

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        with Vertical(id="path-box"):
            yield Static("◈  SELECT TARGET", id="path-title")
            yield Static("Path to the web project folder to scan", id="path-sub")
            yield Input(value=self._initial, placeholder="e.g.  ./my-site", id="path-input")
            yield Static("", id="path-error")
            yield Static("Enter to scan  ·  Esc to quit", id="path-hint")

    def on_mount(self) -> None:
        box = self.query_one("#path-box")
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.4)
        self.query_one(Input).focus()
        self.call_after_refresh(self._fit)
        if self._initial:
            self._validate(self._initial)

    @staticmethod
    def _clean(raw: str) -> str:
        return raw.strip().strip('"').strip("'")

    def _validate(self, raw: str) -> bool:
        error = self.query_one("#path-error", Static)
        raw = self._clean(raw)
        if not raw:
            error.update("")
            return False
        if Path(raw).expanduser().is_dir():
            t = Text()
            t.append("✓ ", style=f"bold {OK}")
            t.append("folder found — press Enter to scan", style=DIM)
            error.update(t)
            return True
        t = Text()
        t.append("✗ ", style=f"bold {_BAD}")
        t.append("no folder at that path yet", style=_FAINT)
        error.update(t)
        return False

    def on_input_changed(self, event: Input.Changed) -> None:
        self._validate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = self._clean(event.value)
        error = self.query_one("#path-error", Static)
        if not raw:
            error.update(Text("✗ enter a path", style=_BAD))
            return
        path = Path(raw).expanduser()
        if not path.is_dir():
            error.update(Text(f"✗ not a folder: {raw}", style=_BAD))
            return
        self.app.begin_scan(str(path))

    def action_quit(self) -> None:
        self.app.exit()
