"""Modal that collects a replacement value for a PROMPT-fixable finding."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ..engine.models import Finding


class PromptModal(ModalScreen[str | None]):
    """Asks the user for a value; dismisses with the string or None."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, finding: Finding) -> None:
        super().__init__()
        self._finding = finding

    def compose(self) -> ComposeResult:
        f = self._finding
        with Vertical(id="modal-box"):
            yield Static(f"✎  {f.message}", id="modal-title")
            yield Static(f"{f.file}:{f.line}  ·  current: {f.matched_text!r}", id="modal-sub")
            yield Input(placeholder=f.prompt_label or "New value", id="modal-input")
            yield Static("Enter to apply  ·  Esc to cancel", id="modal-hint")

    def on_mount(self) -> None:
        box = self.query_one("#modal-box")
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.25)
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            self.query_one("#modal-hint", Static).update(
                "A value is required — type one, or Esc to cancel."
            )
            self.query_one(Input).focus()
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    """Yes/no confirmation; dismisses with True (confirm) or False (cancel)."""

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "No"),
    ]

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__()
        self._message = message
        self._detail = detail

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(self._message, id="modal-title")
            if self._detail:
                yield Static(self._detail, id="modal-sub")
            yield Static("y to confirm  ·  n / Esc to cancel", id="modal-hint")

    def on_mount(self) -> None:
        box = self.query_one("#modal-box")
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.25)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
