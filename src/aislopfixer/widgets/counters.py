"""Animated count-up numeric display."""

from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class CountUp(Static):
    """A big number that eases up to its target when changed."""

    DEFAULT_CSS = "CountUp { height: auto; content-align: center middle; }"

    value: reactive[float] = reactive(0.0)

    def __init__(self, label: str, color: str = "#36e2e6", **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._color = color

    def set_target(self, n: int) -> None:
        self.animate("value", float(n), duration=0.6, easing="out_cubic")

    def watch_value(self) -> None:
        self.refresh()

    def render(self) -> Text:
        text = Text(justify="center")
        text.append(f"{int(round(self.value))}\n", style=f"bold {self._color}")
        text.append(self._label.upper(), style="#7b8496")
        return text
