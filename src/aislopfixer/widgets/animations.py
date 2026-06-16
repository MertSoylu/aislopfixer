"""Scanning animations: a sweeping wave and a braille spinner."""

from __future__ import annotations

import math

from rich.text import Text
from textual.widgets import Static

from ..theme import SHIMMER

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class ScanPulse(Static):
    """A horizontal wave with a bright band sweeping back and forth."""

    DEFAULT_CSS = "ScanPulse { height: 1; content-align: center middle; }"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._phase = 0.0

    def on_mount(self) -> None:
        self.set_interval(0.05, self._tick)

    def _tick(self) -> None:
        self._phase += 0.6
        self.refresh()

    def render(self) -> Text:
        width = max(12, self.size.width or 48)
        pos = (math.sin(self._phase * 0.2) * 0.5 + 0.5) * (width - 1)
        text = Text(justify="left")
        pal = SHIMMER
        n = len(pal)
        for i in range(width):
            d = abs(i - pos)
            if d < 1:
                ch = "█"
            elif d < 3:
                ch = "▓"
            elif d < 6:
                ch = "▒"
            elif d < 10:
                ch = "░"
            else:
                ch = "·"
            color = pal[int(i + self._phase) % n]
            text.append(ch, style=color)
        return text


class Spinner(Static):
    """A braille spinner with an optional trailing label."""

    DEFAULT_CSS = "Spinner { height: 1; }"

    def __init__(self, label: str | Text = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._i = 0
        self._label = label
        self._timer = None

    def set_label(self, label: str | Text) -> None:
        self._label = label
        self.refresh()

    def stop(self) -> None:
        """Freeze the spinner (e.g. on completion or error)."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.08, self._tick)

    def _tick(self) -> None:
        self._i = (self._i + 1) % len(_BRAILLE)
        self.refresh()

    def render(self) -> Text:
        text = Text()
        text.append(_BRAILLE[self._i] + "  ", style="bold #36e2e6")
        if isinstance(self._label, Text):
            text.append_text(self._label)
        else:
            text.append(self._label, style="#cdd6f4")
        return text
