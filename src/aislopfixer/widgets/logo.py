"""Animated shimmer banner and typewriter tagline."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from ..theme import SHIMMER

# 5-row, 4-wide block glyphs.
_FONT: dict[str, list[str]] = {
    "A": [" ██ ", "█  █", "████", "█  █", "█  █"],
    "I": ["████", " ██ ", " ██ ", " ██ ", "████"],
    "S": ["████", "█   ", "████", "   █", "████"],
    "L": ["█   ", "█   ", "█   ", "█   ", "████"],
    "O": ["████", "█  █", "█  █", "█  █", "████"],
    "P": ["████", "█  █", "████", "█   ", "█   "],
    "F": ["████", "█   ", "███ ", "█   ", "█   "],
    "X": ["█  █", " ██ ", " ██ ", " ██ ", "█  █"],
    "E": ["████", "█   ", "███ ", "█   ", "████"],
    "R": ["████", "█  █", "████", "█ █ ", "█  █"],
    " ": ["    ", "    ", "    ", "    ", "    "],
}


def banner_lines(text: str) -> list[str]:
    rows = ["", "", "", "", ""]
    for ch in text.upper():
        glyph = _FONT.get(ch, _FONT[" "])
        for i in range(5):
            rows[i] += glyph[i] + " "
    return rows


class Logo(Static):
    """Block-letter banner with a moving teal↔magenta shimmer."""

    DEFAULT_CSS = "Logo { height: auto; content-align: center middle; }"

    def __init__(self, text: str = "AI SLOP FIXER", **kwargs) -> None:
        super().__init__(**kwargs)
        self._lines = banner_lines(text)
        self._phase = 0

    def on_mount(self) -> None:
        self.set_interval(0.07, self._tick)

    def _tick(self) -> None:
        self._phase += 1
        self.refresh()

    def render(self) -> Text:
        text = Text(justify="center")
        pal = SHIMMER
        n = len(pal)
        for r, line in enumerate(self._lines):
            for c, ch in enumerate(line):
                if ch == " ":
                    text.append(" ")
                else:
                    text.append(ch, style=f"bold {pal[(c + r * 2 + self._phase) % n]}")
            text.append("\n")
        return text


class Typewriter(Static):
    """Types out a tagline character-by-character, then blinks a caret."""

    DEFAULT_CSS = "Typewriter { height: 1; content-align: center middle; }"

    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._full = text
        self._idx = 0
        self._caret = True

    def on_mount(self) -> None:
        self._type_timer = self.set_interval(0.03, self._type)
        self.set_interval(0.5, self._blink)

    def _type(self) -> None:
        if self._idx < len(self._full):
            self._idx += 1
        else:
            self._type_timer.pause()
        self.refresh()

    def _blink(self) -> None:
        self._caret = not self._caret
        self.refresh()

    def render(self) -> Text:
        text = Text(justify="center")
        text.append(self._full[: self._idx], style="#cdd6f4")
        text.append("▋" if self._caret else " ", style="#36e2e6")
        return text
