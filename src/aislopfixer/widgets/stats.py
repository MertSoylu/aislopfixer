"""Compact animated stats for the results header strip."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from ..theme import DIM, OK

_BAD = "#f87171"
_WARN = "#fbbf24"


class StatChip(Static):
    """A one-line ``icon count LABEL`` chip whose number eases to its target."""

    DEFAULT_CSS = "StatChip { width: 1fr; height: 1; content-align: center middle; }"

    value: reactive[float] = reactive(0.0)

    def __init__(self, label: str, color: str, icon: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._color = color
        self._icon = icon

    def set_target(self, n: int) -> None:
        self.animate("value", float(n), duration=0.6, easing="out_cubic")

    def watch_value(self) -> None:
        self.refresh()

    def render(self) -> Text:
        t = Text(justify="center")
        t.append(f"{self._icon} ", style=self._color)
        t.append(f"{int(round(self.value))} ", style=f"bold {self._color}")
        t.append(self._label.upper(), style=DIM)
        return t


class SlopBadge(Static):
    """A right-aligned ``SLOP nn/100 ▰▰▱`` badge that fills once on mount."""

    DEFAULT_CSS = "SlopBadge { height: 1; content-align: right middle; }"

    frac: reactive[float] = reactive(0.0)

    def __init__(self, score: int, cells: int = 6, **kwargs) -> None:
        super().__init__(**kwargs)
        self._score = max(0, min(100, score))
        self._cells = cells

    def on_mount(self) -> None:
        self.animate("frac", self._score / 100, duration=0.9, easing="out_cubic")

    def watch_frac(self) -> None:
        self.refresh()

    def render(self) -> Text:
        color = _BAD if self._score >= 75 else _WARN if self._score >= 45 else OK
        filled = int(round(self.frac * self._cells))
        t = Text(justify="right")
        t.append("SLOP ", style=DIM)
        t.append(f"{int(round(self.frac * 100))}", style=f"bold {color}")
        t.append("/100  ", style=DIM)
        t.append("▰" * filled, style=color)
        t.append("▱" * (self._cells - filled), style="#2a2f3a")
        return t
