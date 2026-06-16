"""Responsive guard: a full-screen overlay shown when the terminal is too small."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ..theme import ACCENT, BAD, DIM, OK

_ACCENT_DIM = "#1f8f93"


class TooSmall(Static):
    """Covers a screen and asks the user to widen the terminal.

    Lives on a dedicated CSS layer (``#guard``) so it paints over whatever the
    screen composed. ``update_fit`` feeds it the live vs. required size; the
    arrows breathe so it reads as an active, recoverable state, not a crash.
    """

    def __init__(self, min_w: int, min_h: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_class("guard")
        self._min_w = min_w
        self._min_h = min_h
        self._w = 0
        self._h = 0
        self._bright = True

    def on_mount(self) -> None:
        self.set_interval(0.7, self._pulse)

    def _pulse(self) -> None:
        self._bright = not self._bright
        self.refresh()

    def update_fit(self, w: int, h: int, min_w: int, min_h: int) -> None:
        self._w, self._h, self._min_w, self._min_h = w, h, min_w, min_h
        self.refresh()

    def render(self) -> Text:
        w_ok = self._w >= self._min_w
        h_ok = self._h >= self._min_h
        arrow = ACCENT if self._bright else _ACCENT_DIM
        t = Text(justify="center")
        t.append("←  ⊟  →\n\n", style=f"bold {arrow}")
        t.append("WINDOW TOO SMALL\n", style=f"bold {ACCENT}")
        t.append("Resize the terminal to keep going\n\n", style=DIM)
        t.append("now ", style=DIM)
        t.append(f"{self._w}", style=f"bold {OK if w_ok else BAD}")
        t.append(" × ", style=DIM)
        t.append(f"{self._h}", style=f"bold {OK if h_ok else BAD}")
        t.append("      need ", style=DIM)
        t.append(f"{self._min_w} × {self._min_h}", style=f"bold {ACCENT}")
        return t
