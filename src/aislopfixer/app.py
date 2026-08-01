"""The Textual application and screen orchestration.

Flow: splash → path → scan → report → system → summary. The app object owns
everything that has to outlive a screen swap — the parsed documents, the
report, the derived system and the undo state of the last transform — because a
screen is recreated on every navigation and losing the undo snapshot would make
"apply" a one-way door.
"""

from __future__ import annotations

from textual.app import App

from .design.models import Document, DesignReport
from .design.system import DesignSystem, derive
from .design.transform import TransformResult
from .screens import (PathScreen, ReportScreen, ScanScreen, SplashScreen,
                      SummaryScreen, SystemScreen)
from .store import Store


class AISlopFixerApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "AI SLOP FIXER"

    def __init__(self, initial_path: str | None = None,
                 pages: list[str] | None = None) -> None:
        super().__init__()
        self.initial_path = initial_path
        # `--pages`: which site inside the repository the numbers are about.
        # Carried on the app because the scan screen builds the Config and the
        # command line has to win over the file. See design.scope.
        self.pages: tuple[str, ...] = tuple(pages or ())
        self.target_path: str | None = None
        self.store: Store | None = None
        self.report: DesignReport | None = None
        self.docs: list[Document] = []
        self.system: DesignSystem | None = None
        # How far the user has cycled the archetype past the seeded default.
        # Kept on the app so leaving and re-entering the system screen does not
        # silently snap the project back to a system they moved away from.
        self.archetype_offset = 0
        self.last_transform: TransformResult | None = None
        self.applied_edits = 0
        # The run *before* this one, captured before the current run is written
        # to the history. Reading the store after recording would compare a run
        # with itself and always report no change.
        self.previous_run: dict | None = None

    def on_mount(self) -> None:
        self.push_screen(SplashScreen())

    # ------------------------------------------------------------ navigation
    def start_after_splash(self) -> None:
        # Always confirm the target on the path screen, even when a PATH arg
        # was passed on the command line — pre-filled, so a valid arg is one
        # Enter away, but the user always sees and can edit it.
        self.switch_screen(PathScreen(self.initial_path or ""))

    def begin_scan(self, path: str) -> None:
        self.target_path = path
        self.store = Store(path)
        self.last_transform = None
        self.applied_edits = 0
        self.archetype_offset = 0
        self.switch_screen(ScanScreen(path))

    def rescan(self) -> None:
        if self.target_path:
            self.switch_screen(ScanScreen(self.target_path))
        else:
            self.switch_screen(PathScreen(""))

    def choose_new_folder(self) -> None:
        self.switch_screen(PathScreen(self.target_path or ""))

    def show_report(self, report: DesignReport, docs: list[Document]) -> None:
        self.report = report
        self.docs = docs
        self.system = self._derive()
        if self.store is not None:
            self.previous_run = self.store.previous
            self.store.record_run(report)
            self.store.write_report(report, self.system)
        self.switch_screen(ReportScreen())

    def show_system(self) -> None:
        self.switch_screen(SystemScreen())

    def show_summary(self) -> None:
        self.switch_screen(SummaryScreen())

    # ---------------------------------------------------------------- system
    def _derive(self) -> DesignSystem | None:
        if self.report is None or self.target_path is None:
            return None
        remembered = self.store.archetype if self.store else None
        return derive(self.target_path, self.report,
                      archetype_key=remembered if self.archetype_offset == 0 else None,
                      offset=self.archetype_offset)

    def cycle_archetype(self, step: int = 1) -> DesignSystem | None:
        """Move to the next archetype and re-derive; remembered per project."""
        self.archetype_offset += step
        self.system = self._derive()
        if self.store is not None and self.system is not None:
            self.store.set_archetype(self.system.archetype.key)
        return self.system

    def set_archetype(self, key: str) -> DesignSystem | None:
        """Derive against a *named* archetype — what the picker selects.

        Goes through the store like the cycle does, so a project keeps whatever
        the user last landed on whether they arrived by arrow key or by ``s``.
        """
        if self.report is None or self.target_path is None:
            return None
        self.archetype_offset = 0
        if self.store is not None:
            self.store.set_archetype(key)
        self.system = derive(self.target_path, self.report, archetype_key=key)
        return self.system

    def refresh_report(self) -> None:
        """Re-parse and re-measure after a transform, in place."""
        if self.target_path is None:
            return
        from .config import Config
        from .design.project import scan_project

        # The scope has to survive the re-measure, or the score shown after a
        # transform would be about a different site than the one before it.
        self.report, self.docs = scan_project(
            self.target_path,
            Config.load(self.target_path).with_pages(self.pages))
        if self.store is not None:
            self.previous_run = self.store.previous
            self.store.record_run(self.report, applied=self.applied_edits)
            self.store.write_report(self.report, self.system)
