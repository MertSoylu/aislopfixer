"""Animated splash screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.widgets import Static

from .base import AdaptiveScreen
from ..widgets import Logo, Typewriter
from .. import __version__


class SplashScreen(AdaptiveScreen):
    MIN_WIDTH = 80
    MIN_HEIGHT = 15

    BINDINGS = [
        ("enter", "go", "Begin"),
        ("space", "go", "Begin"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        with Vertical(id="splash-box"):
            yield Logo()
            yield Typewriter("Detect & fix AI-generated slop in your web project")
            yield Static("PRESS  ENTER  TO  BEGIN", id="splash-hint")
            yield Static(f"v{__version__}", id="splash-version")

    def on_mount(self) -> None:
        box = self.query_one("#splash-box")
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.7)
        self._bright = True
        self.set_interval(0.7, self._pulse)
        self.call_after_refresh(self._fit)

    def _pulse(self) -> None:
        hint = self.query_one("#splash-hint")
        self._bright = not self._bright
        hint.styles.animate("opacity", 1.0 if self._bright else 0.25, duration=0.6)

    def on_key(self, event: Key) -> None:
        # any key (other than the bound q) begins
        if event.key not in ("q", "enter", "space"):
            self.action_go()

    def action_go(self) -> None:
        self.app.start_after_splash()

    def action_quit(self) -> None:
        self.app.exit()
