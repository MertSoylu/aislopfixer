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
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
