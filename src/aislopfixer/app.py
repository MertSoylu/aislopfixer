"""The Textual application and screen orchestration."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from .engine.models import Finding
from .screens import PathScreen, ResultsScreen, ScanScreen, SplashScreen, SummaryScreen
from .store import Store


class AISlopFixerApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "AI SLOP FIXER"

    def __init__(self, initial_path: str | None = None) -> None:
        super().__init__()
        self.initial_path = initial_path
        self.target_path: str | None = None
        self.findings: list[Finding] = []
        self.store: Store | None = None

    @property
    def allowlist(self):
        """The project's not-slop allowlist (None before a scan starts)."""
        return self.store.allowlist if self.store else None

    def on_mount(self) -> None:
        self.push_screen(SplashScreen())

    def start_after_splash(self) -> None:
        if self.initial_path:
            path = Path(self.initial_path).expanduser()
            if path.is_dir():
                self.begin_scan(str(path))
                return
        self.switch_screen(PathScreen(self.initial_path or ""))

    def begin_scan(self, path: str) -> None:
        self.target_path = path
        self.store = Store(path)
        self.switch_screen(ScanScreen(path))

    def rescan(self) -> None:
        """Re-run the scan on the current target (already-fixed items stay gone)."""
        if self.target_path:
            self.begin_scan(self.target_path)
        else:
            self.switch_screen(PathScreen(""))

    def choose_new_folder(self) -> None:
        """Return to the path picker to scan a different folder."""
        self.switch_screen(PathScreen(self.target_path or ""))

    def show_results(self, findings: list[Finding]) -> None:
        self.findings = findings
        if self.store is not None:
            self.store.write_report(findings, self.target_path)
        self.switch_screen(ResultsScreen(findings))

    def show_summary(self) -> None:
        if self.store is not None:
            self.store.write_report(self.findings, self.target_path)
        self.switch_screen(SummaryScreen(self.findings))
