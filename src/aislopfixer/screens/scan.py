"""Scanning screen: parses the project in a thread and animates progress.

Two phases, and the display distinguishes them because their costs are very
different: parsing is per file and linear, while the metrics are cross-file and
run once at the end. A progress bar that jumped to 100% and then sat there for
a second would read as a hang.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Key
from textual.message import Message
from textual.widgets import ProgressBar, Static

from .base import AdaptiveScreen
from ..config import Config
from ..design.models import Axis, DesignReport, Document
from ..design.project import load_documents, measure
from ..scanner import count_eligible
from ..theme import ACCENT, AXIS_COLORS, AXIS_ICON, BAD, BG, DIM, FAINT, OK, TEXT, WARN
from ..widgets import CountUp, ScanPulse, Spinner


class _ScanCancelled(Exception):
    """Raised inside the worker thread to abandon a user-cancelled scan."""


class SetTotal(Message):
    def __init__(self, total: int) -> None:
        self.total = total
        super().__init__()


class FileDone(Message):
    def __init__(self, rel: str, elements: int, per_axis: dict[Axis, int]) -> None:
        self.rel = rel
        self.elements = elements
        self.per_axis = per_axis
        super().__init__()


class MeasureStart(Message):
    """Parsing finished; the cross-file metrics are starting."""


class Done(Message):
    def __init__(self, report: DesignReport, docs: list[Document]) -> None:
        self.report = report
        self.docs = docs
        super().__init__()


class Failed(Message):
    """The worker raised; carries the error text for display."""

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__()


class ScanScreen(AdaptiveScreen):
    MIN_WIDTH = 80
    MIN_HEIGHT = 20

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path
        self._total: int | None = None  # None = not counted yet; 0 = truly empty
        self._done = 0
        self._elements = 0
        self._t0 = 0.0
        self._failed = False
        self._cancelled = False  # set on Esc; the worker checks it per file
        self._counts: dict[Axis, int] = {a: 0 for a in Axis}

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        with Vertical(id="scan-box"):
            yield Static("◇  TASARIM TARANIYOR", id="scan-title")
            yield Static(self._path_line(), id="scan-target")
            yield Spinner("Dosyalar sayılıyor…", id="scan-spinner")
            yield ProgressBar(total=100, show_eta=False, id="scan-prog")
            yield Static(self._count_line(), id="scan-count")
            yield ScanPulse(id="scan-pulse")
            yield Static("", id="scan-current")
            with Horizontal(id="scan-counters"):
                for axis in Axis:
                    yield CountUp(
                        f"{AXIS_ICON[axis]} {axis.label}",
                        AXIS_COLORS[axis],
                        id=f"axis-{axis.name}",
                        classes="cat-counter",
                    )
            yield Static(
                Text("iptal için esc", style=FAINT, justify="center"),
                id="scan-hint",
            )

    def _path_line(self) -> Text:
        t = Text(justify="center", no_wrap=True, overflow="ellipsis")
        t.append(str(self._path), style=DIM)
        return t

    def _count_line(self) -> Text:
        t = Text(justify="center")
        if self._total is None:
            t.append("hazırlanıyor…", style=FAINT)
            return t
        if self._total == 0:
            t.append("0 dosya — taranacak bir şey yok", style=FAINT)
            return t
        pct = round(self._done / self._total * 100)
        t.append(f"{self._done}", style=f"bold {ACCENT}")
        t.append(f" / {self._total} dosya", style=DIM)
        t.append("   ·   ", style=FAINT)
        t.append(f"%{pct}", style=TEXT)
        t.append("   ·   ", style=FAINT)
        t.append(f"{self._elements} eleman", style=WARN if self._elements else DIM)
        if self._t0:
            t.append("   ·   ", style=FAINT)
            t.append(f"{time.monotonic() - self._t0:.0f}s", style=DIM)
        return t

    def on_mount(self) -> None:
        box = self.query_one("#scan-box")
        box.border_title = "◇ TARAMA"
        box.styles.opacity = 0.0
        box.styles.animate("opacity", 1.0, duration=0.4)
        self._t0 = time.monotonic()
        self._clock = self.set_interval(0.5, self._tick_clock)
        self.call_after_refresh(self._fit)
        self._scan()

    def _tick_clock(self) -> None:
        if self._total:
            self.query_one("#scan-count", Static).update(self._count_line())

    @work(thread=True)
    def _scan(self) -> None:
        try:
            config = Config.load(self._path).with_pages(
                getattr(self.app, "pages", ()))
            # Pass the config so ignored paths are not counted — otherwise the
            # progress total is inflated and the bar never reaches 100%.
            total = count_eligible(self._path, config)
            self.post_message(SetTotal(total))
            # Spread tiny projects over ~1.2s so the animation is visible; ~0
            # for a large repo, where the parse itself is the wait.
            delay = min(0.04, 1.2 / total) if total else 0.0

            def on_file(doc: Document) -> None:
                if self._cancelled:
                    raise _ScanCancelled()
                per_axis: dict[Axis, int] = {}
                for el in doc.elements:
                    for d in el.decls:
                        per_axis[d.axis] = per_axis.get(d.axis, 0) + 1
                self.post_message(FileDone(doc.rel_path, len(doc.elements), per_axis))
                if delay:
                    time.sleep(delay)

            # load_documents resolves JSX components itself once the walk is
            # done — that is the point the message marks, not a second pass.
            skipped: dict[str, int] = {}
            docs = load_documents(self._path, config, on_file, skipped)
            self.post_message(MeasureStart())
            # Same entry point `scan_project` uses, so a scan from the
            # interface and a scan from a test cannot start disagreeing.
            report, docs = measure(self._path, docs, config, skipped)
            self.post_message(Done(report, docs))
        except _ScanCancelled:
            pass  # user backed out — the screen is already gone
        except Exception as exc:  # noqa: BLE001 — surface any engine failure to the UI
            self.post_message(Failed(f"{type(exc).__name__}: {exc}"))

    def on_set_total(self, message: SetTotal) -> None:
        if self._cancelled:
            return
        self._total = message.total
        spinner = self.query_one("#scan-spinner", Spinner)
        if message.total == 0:
            spinner.set_label("Taranabilir dosya yok.")
            self.query_one("#scan-current", Static).update(
                Text("Bu klasörde taranacak bir şey yok.", style=FAINT)
            )
        else:
            spinner.set_label(f"{message.total} dosya ayrıştırılıyor…")
        self.query_one("#scan-count", Static).update(self._count_line())

    def on_file_done(self, message: FileDone) -> None:
        if self._cancelled:
            return
        self._done += 1
        self._elements += message.elements
        if self._total:
            pct = self._done / self._total * 100
            self.query_one("#scan-prog", ProgressBar).update(progress=pct)
        self.query_one("#scan-count", Static).update(self._count_line())
        cur = Text(no_wrap=True, overflow="ellipsis")
        cur.append("› ", style=ACCENT)
        cur.append(message.rel, style=DIM)
        self.query_one("#scan-current", Static).update(cur)
        for axis, n in message.per_axis.items():
            self._counts[axis] += n
            self.query_one(f"#axis-{axis.name}", CountUp).set_target(self._counts[axis])

    def on_measure_start(self, message: MeasureStart) -> None:
        if self._cancelled or not self._total:
            return
        self.query_one("#scan-spinner", Spinner).set_label(
            "Dağılımlar ölçülüyor — ritim, simetri, tekrar…")
        self.query_one("#scan-current", Static).update(
            Text("› sayfalar birbiriyle karşılaştırılıyor", style=FAINT)
        )

    def on_done(self, message: Done) -> None:
        if self._cancelled:
            return
        self._clock.stop()
        self.query_one("#scan-count", Static).update(self._count_line())
        self.query_one("#scan-prog", ProgressBar).update(progress=100)
        spinner = self.query_one("#scan-spinner", Spinner)
        spinner.stop()
        done = Text()
        done.append("✓ ", style=f"bold {OK}")
        done.append(
            f"Ölçüm bitti — şablon skoru {message.report.template_score:.0f}/100",
            style=TEXT,
        )
        spinner.set_label(done)
        self.query_one("#scan-current", Static).update(
            Text("rapor açılıyor…", style=FAINT)
        )
        self.set_timer(0.8, lambda: self.app.show_report(message.report, message.docs))

    def on_failed(self, message: Failed) -> None:
        """Stay here and say so — never dress a failed scan up as a clean one."""
        if self._cancelled:
            return
        self._clock.stop()
        self._failed = True
        spinner = self.query_one("#scan-spinner", Spinner)
        spinner.stop()
        err = Text()
        err.append("✗ ", style=f"bold {BAD}")
        err.append("Tarama başarısız", style=TEXT)
        spinner.set_label(err)
        detail = Text(no_wrap=True, overflow="ellipsis")
        detail.append(message.error, style=BAD)
        self.query_one("#scan-current", Static).update(detail)
        hint = Text(justify="center")
        hint.append(" r ", style=f"bold {BG} on {ACCENT}")
        hint.append(" yeniden dene    ", style=DIM)
        hint.append(" n ", style=f"bold {BG} on {ACCENT}")
        hint.append(" başka klasör    ", style=DIM)
        hint.append(" q ", style=f"bold {BG} on {ACCENT}")
        hint.append(" çık", style=DIM)
        self.query_one("#scan-count", Static).update(hint)
        # The bottom hint still said "esc to cancel", but on a failed scan
        # Escape quits — refresh it so the two lines do not contradict.
        self.query_one("#scan-hint", Static).update(
            Text("çıkmak için q ya da esc", style=FAINT, justify="center")
        )

    def on_key(self, event: Key) -> None:
        if not self._failed:
            if event.key == "escape" and not self._cancelled:
                # Cooperative cancel: the worker checks the flag per file.
                self._cancelled = True
                self._clock.stop()
                self.app.choose_new_folder()
            return
        if event.key == "r":
            self.app.rescan()
        elif event.key == "n":
            self.app.choose_new_folder()
        elif event.key in ("q", "escape"):
            self.app.exit()
