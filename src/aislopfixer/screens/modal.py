"""Modals: prompt for a fix value, confirm bulk actions, keyboard help."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ..engine.models import Finding
from ..theme import ACCENT, FAINT, TEXT


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


class ExportModal(ModalScreen[str | None]):
    """Pick an export format; dismisses with the format key or None.

    Formats mirror the headless flags so everything the CLI can emit is one
    keystroke away in the TUI: ``brief`` (--prompt), ``json`` (--json),
    ``sarif`` (--sarif) or ``all``.
    """

    BINDINGS = [
        ("b", "pick('brief')", "Fix brief"),
        ("j", "pick('json')", "JSON"),
        ("s", "pick('sarif')", "SARIF"),
        ("a", "pick('all')", "All three"),
        ("escape", "cancel", "Cancel"),
    ]

    _ROWS = [
        ("b", "Fix brief for your AI assistant (fix-prompt.md, + clipboard)"),
        ("j", "Findings as JSON (findings.json)"),
        ("s", "SARIF 2.1.0 for code scanning (findings.sarif)"),
        ("a", "All three at once"),
    ]

    def __init__(self, n_open: int) -> None:
        super().__init__()
        self._n_open = n_open

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(f"⇩  EXPORT {self._n_open} OPEN FINDING(S)", id="modal-title")
            yield Static(self._body(), id="help-body")
            yield Static("Files land in .aislopfixer/  ·  Esc to cancel", id="modal-hint")

    def _body(self) -> Text:
        t = Text()
        for i, (key, desc) in enumerate(self._ROWS):
            if i:
                t.append("\n")
            t.append(f" {key} ", style=f"bold #0b0e14 on {ACCENT}")
            t.append("  ")
            t.append(desc, style=TEXT)
        return t

    def on_mount(self) -> None:
        box = self.query_one("#modal-box")
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.25)

    def action_pick(self, fmt: str) -> None:
        self.dismiss(fmt)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpModal(ModalScreen[None]):
    """A keyboard-reference overlay; rows are ``(key, description)`` pairs."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("question_mark", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, rows: list[tuple[str, str]], title: str = "KEYBOARD REFERENCE") -> None:
        super().__init__()
        self._rows = rows
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(f"⌨  {self._title}", id="modal-title")
            yield Static(self._body(), id="help-body")
            yield Static("Esc to close", id="modal-hint")

    def _body(self) -> Text:
        # Key chips are sized to the widest *key*; header rows (empty desc)
        # start a new section and don't influence the chip width.
        t = Text()
        width = max((len(k) for k, d in self._rows if d), default=1)
        started = False
        for key, desc in self._rows:
            if not desc:  # section header row
                if started:
                    t.append("\n\n")
                t.append(key, style=f"bold {FAINT}")
                started = True
                continue
            if started:
                t.append("\n")
            t.append(f" {key.center(width)} ", style=f"bold #0b0e14 on {ACCENT}")
            t.append("  ")
            t.append(desc, style=TEXT)
            started = True
        return t

    def on_mount(self) -> None:
        box = self.query_one("#modal-box")
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.25)

    def action_close(self) -> None:
        self.dismiss(None)
