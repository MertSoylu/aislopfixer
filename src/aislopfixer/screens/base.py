"""Shared screen behaviour: a responsive too-small guard for every screen."""

from __future__ import annotations

from textual.css.query import NoMatches
from textual.events import Resize
from textual.screen import Screen

from ..widgets import TooSmall


class AdaptiveScreen(Screen):
    """A screen that shows a "widen the window" overlay below a minimum size.

    Subclasses set ``MIN_WIDTH`` / ``MIN_HEIGHT``, yield ``self.adaptive_guard()``
    as the first thing in ``compose``, and call ``self._fit()`` from ``on_mount``
    (after the first refresh, once the real size is known).
    """

    MIN_WIDTH = 72
    MIN_HEIGHT = 18

    def adaptive_guard(self) -> TooSmall:
        return TooSmall(self.MIN_WIDTH, self.MIN_HEIGHT, id="guard")

    def on_resize(self, event: Resize) -> None:
        self._fit()

    def _fit(self) -> None:
        try:
            guard = self.query_one("#guard", TooSmall)
        except NoMatches:
            return
        w, h = self.size.width, self.size.height
        guard.update_fit(w, h, self.MIN_WIDTH, self.MIN_HEIGHT)
        guard.set_class(w < self.MIN_WIDTH or h < self.MIN_HEIGHT, "on")
