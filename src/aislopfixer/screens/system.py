"""The derived system and the transform preview.

Nothing is written until the user presses ``a``, and the diff shown before that
is the exact diff that will be applied — it is produced by the same plan
object. Showing an approximation here and applying something else is how a tool
loses the right to be run on a real repository.

The archetype can be cycled with ``s``. Each press re-derives the system and
re-plans from scratch, so the preview always matches the archetype on screen.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from .base import AdaptiveScreen, titled
from ..design import transform
from ..design.models import Axis
from ..design.system.archetypes import ARCHETYPES
from ..design.system.emit import token_pairs, wiring_hint
from ..design.system.preview import render as system_preview
from ..theme import (ACCENT, ACCENT_ALT, BAD, DIM, FAINT, MUTED, OK, SOURCE,
                     TEXT, WARN)

_DIFF_FILES = 3        # files whose diff is rendered in full
_DIFF_LINES = 260      # hard cap so a huge project cannot lock the render

# Below this many points the transform is not worth what it costs, and `a` is
# offered **disarmed**. It is not a threshold on the score, it is a threshold on
# the *change* the tool's own preview measures: on `clean_studio` the whole plan
# moves 0.4 points and on `clean_config` it moves the score up, because a
# project that already has a system gets the tool's narrower one in exchange for
# its own. Rewriting 450 files for 1.7 points is not a recommendation, and a
# warning printed beside a one-key write is not an offer anybody can decline.
_WORTH_AT = 3.0

# The axes the transform can actually write, in the order the keys 1..5 select
# them. Mirrors ``transform.plan._AXIS_OF``; an axis the planner never produces
# an edit for would be a switch that does nothing.
TRANSFORM_AXES: tuple[Axis, ...] = (
    Axis.COLOR, Axis.TYPE, Axis.SPACE, Axis.LAYOUT, Axis.MATERIAL,
)


class SystemScreen(AdaptiveScreen):
    MIN_WIDTH = 92
    MIN_HEIGHT = 26

    BINDINGS = [
        Binding("s", "cycle", "arketip"),
        Binding("a", "apply", "uygula"),
        Binding("u", "undo", "geri al"),
        Binding("d", "write_diff", "diff yaz"),
        Binding("v", "toggle_diff", "diff/özet"),
        Binding("escape", "back", "rapora dön"),
        Binding("q", "quit_app", "çık"),
    ] + [
        Binding(str(n), f"toggle_axis({n})", show=False)
        for n in range(0, len(TRANSFORM_AXES) + 1)
    ]

    def __init__(self) -> None:
        super().__init__()
        self._plan = None
        self._show_diff = True
        # Which axes the next apply covers. `plan_all` has taken this filter
        # since it was written; until now the interface never offered it, so the
        # only choices were everything and nothing — and the first real step on
        # a real repository is almost always "take the colours, leave the
        # layout alone".
        self._axes: set[Axis] = set(TRANSFORM_AXES)
        # What the measured preview says pressing `a` costs, and whether the
        # user has been shown that. On a project the tool would make *worse* the
        # key is not armed: the warning was on screen for a release and only in
        # words, while `a` stayed a single keystroke away from writing it.
        self._delta: float | None = None
        self._armed = False

    def _restore_axis_selection(self) -> None:
        """Open on the work that is left, not on everything again."""
        store = getattr(self.app, "store", None)
        done = store.applied_axes if store is not None else set()
        remaining = {a for a in TRANSFORM_AXES if a.value not in done}
        self._axes = remaining or set(TRANSFORM_AXES)

    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        with Horizontal(id="sys-body"):
            with Vertical(id="sys-col"):
                # The picker is above the system, not behind a keystroke: `s`
                # alone told the reader neither how many archetypes there are,
                # which one they are on, nor how to get back to it.
                yield titled(OptionList(*self._archetype_options(), id="sys-arch"),
                             "arketip · ↑↓ gez")
                with titled(VerticalScroll(id="sys-left"), "◇ TÜRETİLEN SİSTEM"):
                    yield Static("", id="sys-system")
            with Vertical(id="sys-right"):
                yield titled(Static("", id="sys-plan"), "plan")
                with titled(VerticalScroll(id="sys-preview"), "önizleme"):
                    yield Static("", id="sys-preview-body")
        yield Footer()

    def on_mount(self) -> None:
        self._restore_axis_selection()
        # `#sys-arch` is two containers deep and a screen's mount handler can run
        # before its nested children are in the DOM. Same race as the report
        # screen's option list: the normal path stays synchronous, only the
        # failure retries, because deferring outright races anything that acts
        # on the screen the moment it appears.
        if not self._focus_archetypes():
            self.call_after_refresh(self._focus_archetypes)
        self._replan()
        self.call_after_refresh(self._fit)

    def _focus_archetypes(self) -> bool:
        """Preselect the derived archetype; ``False`` when it is not mounted yet."""
        try:
            options = self.query_one("#sys-arch", OptionList)
        except NoMatches:
            return False
        options.highlighted = self._current_index()
        options.focus()
        return True

    # ------------------------------------------------------------- archetypes
    def _current_index(self) -> int:
        system = self.app.system
        if system is None:
            return 0
        return next((i for i, a in enumerate(ARCHETYPES)
                     if a.key == system.archetype.key), 0)

    def _archetype_options(self) -> list[Option]:
        current = self.app.system.archetype.key if self.app.system else ""
        out: list[Option] = []
        for arch in ARCHETYPES:
            row = Text(no_wrap=True, overflow="ellipsis")
            here = arch.key == current
            row.append("● " if here else "○ ", style=ACCENT if here else DIM)
            row.append(f"{arch.name:<15}", style=f"bold {TEXT}" if here else TEXT)
            row.append(arch.note, style=FAINT)
            out.append(Option(row, id=arch.key))
        return out

    def on_option_list_option_highlighted(
            self, event: OptionList.OptionHighlighted) -> None:
        key = event.option.id or ""
        system = self.app.system
        if not key or (system is not None and system.archetype.key == key):
            return
        if self.app.set_archetype(key) is None:
            return
        self._replan()

    def _preview_width(self) -> int:
        """Bar width for the drawing, from the pane it is drawn in."""
        try:
            return max(30, min(60, self.query_one("#sys-left").size.width - 6))
        except NoMatches:
            return 44

    # ------------------------------------------------------------------ plan
    def _replan(self) -> None:
        # A different archetype or a different axis selection is a different
        # offer, so the confirmation the last one earned does not carry over.
        self._armed = False
        app = self.app
        if app.system is None or app.report is None:
            self._plan = None
        else:
            self._plan = transform.plan_all(
                app.target_path, app.docs, app.report, app.system,
                axes=self._axes)
        self._render_system()
        self._render_plan()
        self._render_preview()
        self._mark_current()

    def _mark_current(self) -> None:
        """Repaint the picker so the selected row is the derived one."""
        try:
            options = self.query_one("#sys-arch", OptionList)
        except NoMatches:
            return
        index = options.highlighted
        options.clear_options()
        options.add_options(self._archetype_options())
        if index is not None:
            options.highlighted = index

    def _render_system(self) -> None:
        system = self.app.system
        body = self.query_one("#sys-system", Static)
        if system is None:
            body.update(Text("Sistem türetilemedi.", style=BAD))
            return
        t = Text()
        t.append(f"{system.archetype.name}\n", style=f"bold {ACCENT}")
        t.append(f"{system.archetype.note}\n\n", style=FAINT)
        # The drawing goes first: `s` cycles six archetypes, and the thing that
        # tells them apart has to be the thing on screen when the key is pressed.
        t.append_text(system_preview(system, self._preview_width()))
        t.append("\n")
        for label, value in system.summary()[1:]:
            t.append(f"{label:<10}", style=DIM)
            t.append(f"{value}\n", style=TEXT)

        t.append("\nKURALLAR\n", style=f"bold {ACCENT_ALT}")
        for rule in system.doctrine:
            t.append(f"  · {rule}\n", style=MUTED)

        t.append("\nTOKENLAR\n", style=f"bold {DIM}")
        group = ""
        for name, prop, value in token_pairs(system):
            if name != group:
                t.append(f"\n  {name}\n", style=FAINT)
                group = name
            t.append(f"    {prop:<22}", style=TEXT)
            t.append(f"{value[:44]}\n", style=SOURCE)

        t.append(f"\nBAĞLANTI\n", style=f"bold {DIM}")
        t.append(f"  {wiring_hint(self.app.target_path)}\n", style=MUTED)
        t.append("  Araç bunu HTML/CSS girişine kendisi ekler; JS girişli "
                 "projelerde elle eklemen gerekir.\n", style=FAINT)
        body.update(t)

    def _axis_row(self) -> Text:
        """The per-axis switches — one key each, state visible at all times."""
        store = getattr(self.app, "store", None)
        done = store.applied_axes if store is not None else set()
        t = Text()
        t.append("eksenler ", style=DIM)
        for n, axis in enumerate(TRANSFORM_AXES, 1):
            on = axis in self._axes
            t.append(f"{n}", style=ACCENT if on else DIM)
            t.append("✓" if on else "·", style=OK if on else DIM)
            label = axis.label.split(" /")[0]
            t.append(f"{label} ", style=TEXT if on else FAINT)
            if axis.value in done:
                t.append("↺ ", style=FAINT)
        t.append("  0: hepsi\n", style=FAINT)
        if done:
            t.append("↺ önceki çalıştırmada uygulanmıştı\n", style=FAINT)
        return t

    def _render_plan(self) -> None:
        panel = self.query_one("#sys-plan", Static)
        t = self._axis_row()
        if self._plan is None or not self._plan.edits:
            t.append("Uygulanacak değişiklik yok.", style=OK)
            if self.app.applied_edits:
                t.append(f"  ({self.app.applied_edits} düzenleme uygulanmış)",
                         style=FAINT)
            panel.update(t)
            return
        counts = self._plan.counts()
        t.append(f"{len(self._plan.edits)} düzenleme", style=f"bold {ACCENT}")
        t.append(f" · {len(self._plan.files)} dosya\n", style=DIM)
        labels = {"token": "renk/token", "type": "tipografi", "rhythm": "ritim",
                  "layout": "yerleşim", "material": "malzeme"}
        for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            t.append(f"  {labels.get(kind, kind):<12}", style=TEXT)
            t.append(f"{n}\n", style=DIM)
        if self._plan.skipped_expressions:
            t.append(f"  {self._plan.skipped_expressions} eleman atlandı — "
                     f"yeni sınıf koşulsuz bir yere sığmadı\n", style=WARN)
        if self._plan.glued_tokens:
            t.append(f"  {self._plan.glued_tokens} sınıf interpolasyona yapışık "
                     f"(`py-${{n}}`), elle düzenlenmeli\n", style=WARN)
        t.append_text(self._forecast())
        panel.update(t)

    def _forecast(self) -> Text:
        """What the score will be if `a` is pressed — measured, not estimated.

        The transform is run in memory over the same plan and the result goes
        through the same measurement, so this is the number the next scan will
        report rather than a projection of it. It can go *up*: on a project that
        already has a system, the tool's own is narrower. Saying so before the
        write is the difference between a tool and a gamble.
        """
        app = self.app
        t = Text()
        self._delta = None
        if app.report is None or app.system is None:
            return t
        try:
            after = transform.preview(app.target_path, app.docs, app.report,
                                      app.system, axes=self._axes)
        except Exception:                # noqa: BLE001 — a preview must never
            return t                     # be the thing that breaks the screen
        before = app.report.template_score
        delta = after.template_score - before
        self._delta = delta
        style = OK if delta < 0 else WARN
        t.append("\n  uygulanırsa   ", style=DIM)
        t.append(f"{before:.0f} → {after.template_score:.0f}", style=f"bold {style}")
        t.append(f"  ({delta:+.1f} puan)", style=style)
        if delta >= 0:
            t.append("\n  bu projede araç skoru düşürmüyor — kendi sistemi "
                     "projeninkinden dar", style=WARN)
        elif -delta < _WORTH_AT:
            t.append(f"\n  kazanç {_WORTH_AT:.0f} puanın altında — bu proje "
                     f"için dönüşüm önerilmiyor", style=WARN)
        if not self._worth_it:
            t.append("\n  `a` kapalı: yine de yazmak için iki kez bas",
                     style=WARN)
        return t

    @property
    def _worth_it(self) -> bool:
        """Whether the tool recommends its own transform on this project."""
        return self._delta is not None and -self._delta >= _WORTH_AT

    def _render_preview(self) -> None:
        body = self.query_one("#sys-preview-body", Static)
        if self._plan is None or not self._plan.edits:
            body.update(Text("—", style=FAINT))
            return
        if not self._show_diff:
            t = Text()
            for edit in self._plan.edits[:80]:
                t.append(f"{edit.file}:{edit.line}  ", style=ACCENT)
                t.append(f"{edit.note}\n", style=DIM)
                t.append(f"  − {edit.old.strip()[:110]}\n", style=BAD)
                t.append(f"  + {edit.new.strip()[:110]}\n", style=OK)
            body.update(t)
            return
        t = Text()
        lines = 0
        for abs_path, edits in list(self._plan.by_file().items())[:_DIFF_FILES]:
            rel = edits[0].file
            diff = transform.diff_for(abs_path, rel, edits)
            for line in diff.splitlines():
                if lines >= _DIFF_LINES:
                    t.append("\n… önizleme kesildi; tamamı uygulandığında "
                             "dosyalara yazılır\n", style=FAINT)
                    body.update(t)
                    return
                style = SOURCE
                if line.startswith("+++") or line.startswith("---"):
                    style = f"bold {DIM}"
                elif line.startswith("@@"):
                    style = ACCENT_ALT
                elif line.startswith("+"):
                    style = OK
                elif line.startswith("-"):
                    style = BAD
                t.append(line + "\n", style=style)
                lines += 1
        remaining = len(self._plan.by_file()) - _DIFF_FILES
        if remaining > 0:
            t.append(f"\n…ve {remaining} dosya daha\n", style=FAINT)
        body.update(t)

    # --------------------------------------------------------------- actions
    def action_cycle(self) -> None:
        """`s` still steps to the next archetype — the list follows the cursor.

        Moving the highlight is what re-derives, so the key only has to move the
        highlight: two paths to the same state would eventually disagree.
        """
        options = self.query_one("#sys-arch", OptionList)
        options.highlighted = ((options.highlighted or 0) + 1) % len(ARCHETYPES)
        system = self.app.system
        if system is not None:
            self.notify(f"Arketip: {system.archetype.name}", timeout=2)

    def action_toggle_axis(self, index: int) -> None:
        """Turn one axis of the transform on or off; ``0`` turns them all on.

        The plan, its counts and the diff are rebuilt from the new selection,
        so what is on screen is always what ``a`` would write — the same rule
        the archetype picker follows.
        """
        if index == 0:
            self._axes = set(TRANSFORM_AXES)
        elif 1 <= index <= len(TRANSFORM_AXES):
            axis = TRANSFORM_AXES[index - 1]
            self._axes.symmetric_difference_update({axis})
            if not self._axes:
                # An empty selection plans nothing, which reads as "there is
                # nothing to do" rather than "you turned everything off".
                self._axes = {axis}
                self.notify("En az bir eksen açık kalmalı.", timeout=2)
        else:
            return
        self._replan()

    def action_write_diff(self) -> None:
        """Write the whole plan as a patch, without applying a byte of it.

        Produced from the same plan object the apply uses, so what lands in
        ``plan.diff`` is what pressing ``a`` would do — a file that differs from
        the preview would cost the tool the right to be run unattended.
        """
        app = self.app
        store = getattr(app, "store", None)
        if self._plan is None or not self._plan.edits or store is None:
            self.notify("Yazılacak bir plan yok.", timeout=2)
            return
        text = transform.plan_diff(self._plan)
        if not text:
            self.notify("Plan hiçbir dosyada değişiklik üretmiyor.", timeout=3)
            return
        path = store.dir / "plan.diff"
        try:
            store.dir.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            self.notify(f"Yazılamadı: {exc}", severity="error")
            return
        self.notify(
            f"{path} yazıldı ({len(self._plan.files)} dosya) — "
            f"`git apply` ile uygulanabilir. Token dosyası buna dahil değil; "
            f"onu yalnızca `a` oluşturur.",
            timeout=6,
        )

    def action_toggle_diff(self) -> None:
        self._show_diff = not self._show_diff
        self.query_one("#sys-preview").border_title = (
            "önizleme" if self._show_diff else "değişiklik listesi")
        self._render_preview()

    def action_apply(self) -> None:
        """Write the plan — unless the measurement says it would make it worse.

        On a project that already has a system the tool's own is narrower and
        the score goes **up**; on one that mostly has a system it moves a
        fraction of a point for hundreds of edits. That was already on screen
        in words, and words beside a one-key write are not an offer the user
        can decline by default. So the key is *disarmed* in exactly those
        cases: the first press says what it would cost, the second one does it.
        Nothing is forbidden; the default is simply "no" where the number says
        no.
        """
        app = self.app
        if self._plan is None or not self._plan.edits or app.system is None:
            self.notify("Uygulanacak değişiklik yok.", timeout=2)
            return
        if self._delta is not None and not self._worth_it and not self._armed:
            self._armed = True
            self.notify(
                f"Bu projede dönüşüm şablon skorunu yalnızca "
                f"{self._delta:+.1f} puan hareket ettiriyor "
                f"({len(self._plan.edits)} düzenleme karşılığında) — araç "
                f"kendi sistemini projeninkinden dar buluyor. Yine de yazmak "
                f"için `a`'ya tekrar bas.",
                severity="warning", timeout=8)
            return
        result = transform.run(app.target_path, app.docs, app.report, app.system,
                               axes=set(self._axes))
        app.last_transform = result
        app.applied_edits += result.applied.edits
        if result.applied.failed:
            self.notify(f"{len(result.applied.failed)} dosya yazılamadı",
                        severity="error")
        app.refresh_report()
        if app.store is not None:
            app.store.record_run(app.report, result.applied.edits)
            app.store.add_applied_axes(a.value for a in self._axes)
        self._replan()
        self.notify(
            f"{result.applied.edits} düzenleme uygulandı · şablon skoru "
            f"{app.report.template_score:.0f}/100  (geri almak için u)",
            timeout=6,
        )

    def action_undo(self) -> None:
        app = self.app
        if app.last_transform is None:
            self.notify("Geri alınacak bir şey yok.", timeout=2)
            return
        n = transform.undo(app.last_transform.applied)
        app.applied_edits = 0
        app.last_transform = None
        if app.store is not None:
            app.store.clear_applied_axes()
        app.refresh_report()
        self._replan()
        self.notify(f"{n} dosya geri alındı · şablon skoru "
                    f"{app.report.template_score:.0f}/100", timeout=4)

    def action_back(self) -> None:
        from .report import ReportScreen

        self.app.switch_screen(ReportScreen())

    def action_quit_app(self) -> None:
        self.app.show_summary()
