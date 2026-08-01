"""The design report — the screen the whole tool exists to show.

Three regions, in the order a reader needs them:

* the headline, which is two numbers and a sentence. The template score alone
  would be a verdict without an argument, so decision density and repetition
  are always shown beside it;
* the axis meters, which say *where* the missing decisions are;
* the observation list and its detail pane, which say what was measured, where
  in the source, and what to do instead.

Every observation carries evidence with real file/line positions, because a
claim about a distribution is only checkable if the reader can go look.
"""

from __future__ import annotations

import os
import subprocess

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from .base import AdaptiveScreen, titled
from ..design.analyze import priorities
from ..design.brief import render as render_brief
from ..design.models import Axis, DesignReport, Observation
from ..editor import launch_detached as launch_editor
from ..editor import resolve as resolve_editor
from ..theme import (ACCENT, AXIS_COLORS, AXIS_ICON, BORDER, DIM, FAINT, MUTED,
                     OK, SOURCE, TEXT, meter, score_color, severity_color,
                     sparkline)

_METER_W = 22
_EVIDENCE_SHOWN = 6


class ReportScreen(AdaptiveScreen):
    MIN_WIDTH = 92
    MIN_HEIGHT = 26

    BINDINGS = [
        Binding("i", "toggle_order", "önce ne"),
        Binding("o", "open_source", "kaynağı aç"),
        Binding("s", "system", "sistem"),
        Binding("x", "export", "reçete"),
        Binding("a", "accept", "kabul et"),
        Binding("r", "rescan", "yeniden tara"),
        Binding("n", "new_folder", "başka klasör"),
        Binding("q", "quit_app", "çık"),
        Binding("escape", "quit_app", "çık", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._selected: str = ""
        # "all" is every observation by weight — what was measured. "impact" is
        # the first five jobs by how far each is projected to move the score,
        # which is the question a reader actually arrives with.
        self._order: str = "all"

    # ------------------------------------------------------------------ data
    @property
    def report(self) -> DesignReport:
        return self.app.report

    @property
    def accepted(self) -> set[str]:
        store = getattr(self.app, "store", None)
        return store.accepted if store else set()

    def observations(self) -> list[Observation]:
        return self.report.observations

    # --------------------------------------------------------------- compose
    def compose(self) -> ComposeResult:
        # Titles are set on the widget as it is built, not queried for in
        # ``on_mount``: a screen's mount handler can run before its *nested*
        # children are in the DOM, and a report that crashes on a fast machine
        # once in fifty runs is worse than no report at all.
        yield self.adaptive_guard()
        yield titled(Static(self._headline(), id="rep-head"), "◇ TASARIM RAPORU")
        with Horizontal(id="rep-body"):
            with Vertical(id="rep-left"):
                yield titled(Static(self._axis_block(), id="rep-axes"), "eksenler")
                yield titled(OptionList(*self._options(), id="rep-list"),
                             self._list_title())
            with titled(VerticalScroll(id="rep-detail"), "ayrıntı"):
                yield Static("", id="rep-detail-body")
        yield Footer()

    def on_mount(self) -> None:
        # Selecting is state and happens now, unconditionally: deferring it
        # would race anything that acts on the screen as soon as it appears.
        if self.observations():
            self._selected = self.observations()[0].key
        self._render_detail()
        # `#rep-list` is two containers deep, and a screen's mount handler can
        # run before its nested children are in the DOM — the same race the
        # compose comment above describes, fixed there for border titles and
        # left here, where it surfaced as a `NoMatches` in one full test run out
        # of five. For a user that is a crash instead of a report. So the normal
        # path stays synchronous and only the failure retries.
        if not self._focus_list():
            self.call_after_refresh(self._focus_list)
        self.call_after_refresh(self._fit)

    def _focus_list(self) -> bool:
        """Focus and preselect the list; ``False`` when it is not in the DOM yet."""
        try:
            options = self.query_one("#rep-list", OptionList)
        except NoMatches:
            return False
        options.focus()
        if self.observations():
            options.highlighted = 0
        return True

    # --------------------------------------------------------------- headline
    def _headline(self) -> Text:
        r = self.report
        t = Text()
        colour = score_color(r.template_score)
        t.append("ŞABLON  ", style=f"bold {DIM}")
        t.append(f"{r.template_score:>5.0f}", style=f"bold {colour}")
        t.append(" /100   ", style=FAINT)
        t.append(meter(r.template_score, _METER_W), style=colour)
        t.append("   ")
        t.append(r.verdict, style=f"bold {colour}")
        t.append("\n\n")

        t.append("karar yoğunluğu ", style=DIM)
        t.append(f"{r.decision_density:>5.0f}", style=f"bold {TEXT}")
        t.append("  ", style=FAINT)
        t.append(meter(r.decision_density, _METER_W), style=ACCENT)
        t.append("   kaç bağımsız tasarım kararı var\n", style=FAINT)

        t.append("tekrar          ", style=DIM)
        t.append(f"{r.repetition:>5.0f}", style=f"bold {TEXT}")
        t.append("  ", style=FAINT)
        t.append(meter(r.repetition, _METER_W), style=AXIS_COLORS[Axis.LAYOUT])
        t.append("   sayfanın ne kadarı kendisinin kopyası\n", style=FAINT)

        t.append_text(self._since_last_run())
        t.append(
            f"\n{r.files_scanned} dosya · {r.elements} eleman"
            f" · {len(self.observations())} gözlem", style=FAINT)
        if r.stack:
            t.append(f" · {', '.join(sorted(r.stack))}", style=FAINT)
        for line in r.notes:
            # Not a finding — a statement about how much of the project the
            # numbers above cover. A silent skip reads as "I looked at
            # everything", which is the one thing the report must never imply.
            t.append(f"\n⚠ {line}", style=FAINT)
        return t

    def _since_last_run(self) -> Text:
        """"Better or worse than last time" — the most convincing line here.

        Read from the stored history, never recomputed: the previous run's
        number is whatever the tool actually said that day, and re-deriving it
        from today's code would quietly rewrite the past.
        """
        t = Text()
        previous = getattr(self.app, "previous_run", None)
        if not previous or "template" not in previous:
            return t
        before = float(previous["template"])
        delta = self.report.template_score - before
        if abs(delta) < 0.05:
            t.append(f"\ngeçen çalıştırma {before:.0f} · değişmedi", style=FAINT)
            return t
        colour = OK if delta < 0 else severity_color(1.0)
        t.append(f"\ngeçen çalıştırma {before:.0f} → ", style=FAINT)
        t.append(f"{self.report.template_score:.0f}", style=f"bold {colour}")
        t.append(f"  ({delta:+.0f})", style=colour)
        history = [float(h.get("template", 0.0))
                   for h in (getattr(self.app, "store", None).history
                             if getattr(self.app, "store", None) else [])]
        if len(history) >= 3:
            t.append(f"   {sparkline(history[-10:])}", style=ACCENT)
        return t

    def _axis_block(self) -> Text:
        t = Text()
        for axis in Axis:
            score = self.report.axes.get(axis)
            colour = AXIS_COLORS[axis]
            t.append(f"{AXIS_ICON[axis]:<2} ", style=colour)
            t.append(f"{axis.label:<19}", style=TEXT)
            if score is None or not score.measured:
                t.append("—  kullanılmıyor\n", style=FAINT)
                continue
            t.append(meter(score.decision_score, 12), style=colour)
            t.append(f" {score.decision_score:>3.0f}", style=TEXT)
            t.append(f"  tekrar {score.repetition:>3.0f}", style=DIM)
            t.append(f"  {score.verdict}\n", style=FAINT)
        return t

    # ------------------------------------------------------------------ list
    def _list_title(self) -> str:
        if self._order == "impact":
            return "ilk beş iş · i: hepsi"
        return "gözlemler · i: önce ne"

    def _options(self) -> list[Option]:
        if self._order == "impact":
            return self._impact_options()
        out: list[Option] = []
        accepted = self.accepted
        for obs in self.observations():
            row = Text(no_wrap=True, overflow="ellipsis")
            colour = severity_color(obs.severity)
            is_accepted = obs.key in accepted
            row.append("✓ " if is_accepted else "● ",
                       style=OK if is_accepted else colour)
            row.append(f"{AXIS_ICON[obs.axis]:<2} ", style=AXIS_COLORS[obs.axis])
            row.append(obs.title, style=FAINT if is_accepted else TEXT)
            row.append(f"  · {obs.stat}", style=DIM)
            out.append(Option(row, id=obs.key))
        if not out:
            out.append(Option(
                Text("Hiçbir şey ölçülmedi — bu projede tasarım kodu yok.",
                     style=FAINT),
                id="__empty__", disabled=True,
            ))
        return out

    def _impact_options(self) -> list[Option]:
        """The five jobs that move the number most, with who closes each.

        The projected drop is the tool's own score re-run with the observation
        closed, so the ordering is about this measurement rather than a second
        opinion about it. ``⚡`` marks what the transform does by itself.
        """
        jobs = priorities(self.report)
        if not jobs:
            return [Option(Text("Sıralanacak iş yok.", style=FAINT),
                           id="__empty__", disabled=True)]
        out: list[Option] = []
        for n, job in enumerate(jobs, 1):
            obs = job.observation
            row = Text(no_wrap=True, overflow="ellipsis")
            row.append(f"{n}. ", style=DIM)
            row.append(f"−{job.drop:<4.1f}", style=f"bold {severity_color(obs.severity)}")
            row.append("⚡ " if job.self_fixable else "✎ ",
                       style=OK if job.self_fixable else ACCENT)
            row.append(f"{AXIS_ICON[obs.axis]:<2} ", style=AXIS_COLORS[obs.axis])
            row.append(obs.title, style=TEXT)
            out.append(Option(row, id=obs.key))
        out.append(Option(
            Text("⚡ araç kendisi düzeltir  ·  ✎ sana kalıyor  ·  "
                 "−n: skorun tahmini düşüşü", style=FAINT),
            id="__legend__", disabled=True,
        ))
        return out

    def on_option_list_option_highlighted(
            self, event: OptionList.OptionHighlighted) -> None:
        self._selected = event.option.id or ""
        self._render_detail()

    def _current(self) -> Observation | None:
        return next((o for o in self.observations() if o.key == self._selected), None)

    # ---------------------------------------------------------------- detail
    def _render_detail(self) -> None:
        try:
            body = self.query_one("#rep-detail-body", Static)
        except NoMatches:
            # The option list can emit its first highlight while the detail
            # pane beside it is still being mounted. Nothing is lost by
            # skipping: `on_mount` renders the detail once everything is up.
            return
        obs = self._current()
        if obs is None:
            body.update(Text("—", style=FAINT))
            return
        t = Text()
        colour = severity_color(obs.severity)
        t.append(f"{AXIS_ICON[obs.axis]} {obs.axis.label}", style=AXIS_COLORS[obs.axis])
        t.append(f"   ağırlık {obs.severity:.2f}", style=colour)
        t.append(f"   {obs.id}\n", style=FAINT)
        job = next((p for p in priorities(self.report, limit=0)
                    if p.observation is obs), None)
        if job is not None and job.drop > 0:
            t.append(f"kapanırsa şablon skoru ≈ −{job.drop:.1f}", style=OK)
            t.append("  (aracın kendi formülüyle yeniden hesaplandı)\n"
                     if job.self_fixable else "  · bu iş sana kalıyor\n",
                     style=FAINT)
        t.append(f"{obs.title}\n\n", style=f"bold {TEXT}")
        t.append(obs.detail + "\n", style=MUTED)

        if obs.prescription:
            t.append("\nYAPILACAK\n", style=f"bold {ACCENT}")
            t.append(obs.prescription + "\n", style=TEXT)

        if obs.evidence:
            t.append(f"\nKANIT ({len(obs.evidence)} yer)\n", style=f"bold {DIM}")
            for ev in obs.evidence[:_EVIDENCE_SHOWN]:
                t.append(f"{ev.file}:{ev.line}", style=ACCENT)
                if ev.value:
                    t.append(f"  {ev.value}", style=OK)
                t.append("\n")
                t.append(f"    {ev.snippet}\n", style=SOURCE)
            if len(obs.evidence) > _EVIDENCE_SHOWN:
                t.append(f"    …{len(obs.evidence) - _EVIDENCE_SHOWN} yer daha\n",
                         style=FAINT)

        score = self.report.axes.get(obs.axis)
        if score is not None and score.vocabulary:
            t.append("\nBU EKSENDE KULLANILAN DEĞERLER\n", style=f"bold {DIM}")
            top = sorted(score.vocabulary.items(), key=lambda kv: -kv[1])[:12]
            for name, uses in top:
                t.append(f"    {name:<28}", style=TEXT)
                t.append(f"×{uses}\n", style=DIM)
            t.append(f"    varsayılan oranı %{score.default_share * 100:.0f}\n",
                     style=FAINT)

        if obs.key in self.accepted:
            t.append("\n✓ Bu gözlemi kabul ettin — raporda kalır, reçeteye girmez.\n",
                     style=OK)
        body.update(t)

    # --------------------------------------------------------------- actions
    def action_toggle_order(self) -> None:
        self._order = "impact" if self._order == "all" else "all"
        options = self.query_one("#rep-list", OptionList)
        options.clear_options()
        options.add_options(self._options())
        options.border_title = self._list_title()
        if options.option_count:
            options.highlighted = 0
        self._render_detail()

    def action_open_source(self) -> None:
        """Open the first place this observation points at.

        Falls back to the clipboard when no editor can be found, and says which
        of the two happened — a key that silently does nothing is worse than no
        key, because the reader cannot tell it from a broken install.
        """
        obs = self._current()
        if obs is None or not obs.evidence:
            self.notify("Bu gözlemin açılacak bir konumu yok.", timeout=2)
            return
        ev = obs.evidence[0]
        root = self.app.target_path or ""
        path = os.path.join(root, ev.file) if root else ev.file
        where = f"{ev.file}:{ev.line}"
        command = resolve_editor(path, ev.line)
        if command is None:
            try:
                self.app.copy_to_clipboard(f"{path}:{ev.line}")
            except Exception:  # noqa: BLE001 — clipboard is best-effort
                self.notify(f"Editör bulunamadı. Konum: {where}", timeout=6)
                return
            self.notify(
                f"Editör bulunamadı ($EDITOR boş, code/subl yok). "
                f"{where} panoya kopyalandı.", timeout=6)
            return
        try:
            if command.terminal:
                # A terminal editor shares this terminal; hand it over and take
                # it back rather than letting both draw at once.
                with self.app.suspend():
                    subprocess.call(command.argv)
            else:
                launch_editor(command)
        except OSError as exc:
            self.notify(f"{command.name} açılamadı: {exc}", severity="error")
            return
        self.notify(f"{command.name} · {where}", timeout=3)

    def action_system(self) -> None:
        self.app.show_system()

    def action_accept(self) -> None:
        obs = self._current()
        store = getattr(self.app, "store", None)
        if obs is None or store is None:
            return
        now = store.toggle_accepted(obs.key)
        options = self.query_one("#rep-list", OptionList)
        index = options.highlighted
        options.clear_options()
        options.add_options(self._options())
        if index is not None:
            options.highlighted = index
        self._render_detail()
        self.notify("Kabul edildi" if now else "Kabul geri alındı", timeout=2)

    def action_export(self) -> None:
        store = getattr(self.app, "store", None)
        if store is None:
            return
        text = render_brief(self.report, self.app.system,
                            applied=self.app.applied_edits,
                            accepted=self.accepted)
        path = store.dir / "brief.md"
        try:
            store.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            self.notify(f"Yazılamadı: {exc}", severity="error")
            return
        try:
            self.app.copy_to_clipboard(text)
        except Exception:  # noqa: BLE001 — clipboard is a nicety, not the feature
            pass
        self.notify(f"Reçete yazıldı: {path}", timeout=4)

    def action_rescan(self) -> None:
        self.app.rescan()

    def action_new_folder(self) -> None:
        self.app.choose_new_folder()

    def action_quit_app(self) -> None:
        self.app.show_summary()
