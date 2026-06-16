"""Results screen: browse findings and apply interactive fixes."""

from __future__ import annotations

from collections import defaultdict

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Static, Tree
from textual.widgets.tree import TreeNode

from .. import fixer
from ..engine.models import Category, Finding, Fixability, Status
from ..engine.scoring import file_score, project_score_from_findings

AUTO_FIX_FLOOR = 0.60  # bulk auto-fix skips findings below this confidence
from .base import AdaptiveScreen
from ..screens.modal import PromptModal
from ..theme import (
    ACCENT,
    BAD,
    CATEGORY_COLORS,
    CATEGORY_ICON,
    DIM,
    FIX_COLOR,
    FIX_ICON,
    OK,
    SEVERITY_COLORS,
    SEVERITY_ICON,
)

_WARN = "#fbbf24"
_TEXT = "#cdd6f4"
_FAINT = "#5b647a"
_SOURCE = "#6b7280"


class ResultsScreen(AdaptiveScreen):
    MIN_WIDTH = 80
    MIN_HEIGHT = 20

    BINDINGS = [
        ("f", "fix", "Fix"),
        ("s", "skip", "Skip"),
        ("a", "annotate", "Annotate"),
        ("i", "ignore", "Not slop"),
        ("p", "fix_auto", "Fix all auto"),
        ("e", "toggle", "Expand/Collapse"),
        ("q", "summary", "Summary"),
    ]

    def __init__(self, findings: list[Finding]) -> None:
        super().__init__()
        self._findings = findings
        self._leaf_nodes: dict[str, TreeNode] = {}

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        yield self.adaptive_guard()
        with Vertical(id="results-root"):
            with Horizontal(id="results-header"):
                yield Static(self._wordmark(), id="results-wordmark")
                from ..widgets import SlopBadge

                yield SlopBadge(self._slop_score(), id="results-slop")
            with Horizontal(id="results-strip"):
                yield self._chip("c-found", "Found", ACCENT, "◆")
                yield self._chip("c-fixed", "Fixed", OK, "✓")
                yield self._chip("c-skip", "Skipped", DIM, "→")
                yield self._chip("c-left", "Remaining", _WARN, "▲")
            if not self._findings:
                yield Static(self._clean_banner(), id="clean")
            else:
                with Horizontal(id="results-main"):
                    yield Tree("Findings", id="tree")
                    yield Static("", id="detail")
        yield Footer()

    def _chip(self, cid: str, label: str, color: str, icon: str):
        from ..widgets import StatChip

        return StatChip(label, color, icon, id=cid, classes="rc")

    def _wordmark(self) -> Text:
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append("AISLOPFIXER", style=f"bold {ACCENT}")
        target = getattr(self.app, "target_path", None)
        if target:
            t.append("  ·  ", style=_FAINT)
            t.append(str(target), style=DIM)
        return t

    def _slop_score(self) -> int:
        return round(project_score_from_findings(self._findings) * 100)

    def _clean_banner(self) -> Text:
        t = Text(justify="center")
        t.append("\n✦  NO SLOP DETECTED  ✦\n\n", style=f"bold {OK}")
        t.append("This project came back clean.\n\n", style=_TEXT)
        t.append("Press ", style=DIM)
        t.append("q", style=f"bold {ACCENT}")
        t.append(" for the summary.", style=DIM)
        return t

    # -------------------------------------------------------------------- mount
    def on_mount(self) -> None:
        root = self.query_one("#results-root")
        root.styles.opacity = 0.0
        root.styles.animate("opacity", 1.0, duration=0.45)
        if self._findings:
            self._build_tree()
        self._refresh_counters()
        self.call_after_refresh(self._fit)

    def _build_tree(self) -> None:
        tree = self.query_one("#tree", Tree)
        tree.show_root = False
        tree.guide_depth = 3
        by_cat: dict[Category, dict[str, list[Finding]]] = defaultdict(lambda: defaultdict(list))
        for f in self._findings:
            by_cat[f.category][f.file].append(f)

        for cat in Category:
            files = by_cat.get(cat)
            if not files:
                continue
            count = sum(len(v) for v in files.values())
            cat_label = Text(no_wrap=True, overflow="ellipsis")
            cat_label.append(f"{CATEGORY_ICON[cat]} ", style=CATEGORY_COLORS[cat])
            cat_label.append(f"{cat.value} ", style=f"bold {CATEGORY_COLORS[cat]}")
            cat_label.append(f"{count}", style=DIM)
            cat_node = tree.root.add(cat_label, expand=True)
            for path, items in files.items():
                items.sort(key=lambda f: (-f.confidence, f.line))
                score = file_score(items)
                file_label = Text(no_wrap=True, overflow="ellipsis")
                file_label.append(f"{self._basename(path)} ", style=_TEXT)
                file_label.append(f"{len(items)} ", style=DIM)
                file_label.append_text(self._mini_bar(score))
                file_node = cat_node.add(file_label, expand=True)
                for f in items:
                    leaf = file_node.add_leaf(self._leaf_label(f), data=f)
                    self._leaf_nodes[f.key] = leaf

        first = self._findings[0]
        self.query_one("#detail", Static).update(self._detail(first))

    @staticmethod
    def _basename(path: str) -> str:
        return path.replace("\\", "/").rsplit("/", 1)[-1]

    @staticmethod
    def _slop_color(score: float) -> str:
        if score >= 0.75:
            return BAD
        if score >= 0.45:
            return _WARN
        return DIM

    def _mini_bar(self, score: float, cells: int = 5) -> Text:
        color = self._slop_color(score)
        filled = int(round(score * cells))
        t = Text()
        t.append("▰" * filled, style=color)
        t.append("▱" * (cells - filled), style="#2a2f3a")
        return t

    # ------------------------------------------------------------------ labels
    @staticmethod
    def _trunc(s: str, n: int) -> str:
        s = " ".join(s.split())
        return s if len(s) <= n else s[: n - 1] + "…"

    def _leaf_label(self, f: Finding) -> Text:
        t = Text(no_wrap=True, overflow="ellipsis")
        t.append(SEVERITY_ICON[f.severity] + " ", style=SEVERITY_COLORS[f.severity])
        if f.status is Status.FIXED:
            t.append("✓ ", style=OK)
        elif f.status is Status.ANNOTATED:
            t.append("✎ ", style=ACCENT)
        elif f.status is Status.SKIPPED:
            t.append("→ ", style=DIM)
        elif f.status is Status.IGNORED:
            t.append("⊘ ", style=DIM)
        body_style = DIM if f.status is not Status.OPEN else _TEXT
        t.append(f"{self._trunc(f.message, 40)} ", style=body_style)
        t.append(f"L{f.line} ", style=_FAINT)
        t.append(FIX_ICON[f.fixability.value], style=FIX_COLOR[f.fixability.value])
        return t

    # --------------------------------------------------------------- detail pane
    def _conf_meter(self, conf: float, cells: int = 5) -> Text:
        color = OK if conf >= 0.75 else _WARN if conf >= 0.45 else DIM
        filled = int(round(conf * cells))
        t = Text()
        t.append("▰" * filled, style=color)
        t.append("▱" * (cells - filled), style="#2a2f3a")
        t.append(f"  {round(conf * 100)}%", style=color)
        return t

    @staticmethod
    def _fix_phrase(fix: Fixability) -> str:
        return {
            Fixability.AUTO: "automatic fix",
            Fixability.PROMPT: "needs a value",
            Fixability.MANUAL: "manual review",
        }[fix]

    @staticmethod
    def _status_text(status: Status) -> Text:
        color = {
            Status.OPEN: _WARN,
            Status.FIXED: OK,
            Status.ANNOTATED: ACCENT,
            Status.SKIPPED: DIM,
            Status.IGNORED: DIM,
        }[status]
        return Text(status.value, style=f"bold {color}")

    def _source_block(self, f: Finding, max_lines: int = 12) -> Text:
        t = Text()
        snippet = f.snippet or "—"
        lines = snippet.splitlines() or ["—"]
        clipped = lines[:max_lines]
        joined = "\n".join(clipped)
        if f.matched_text and f.matched_text in joined:
            i = joined.index(f.matched_text)
            self._emit_indented(t, joined[:i], _SOURCE)
            t.append(f.matched_text, style=f"bold #0b0e14 on {BAD}")
            self._emit_indented(t, joined[i + len(f.matched_text):], _SOURCE)
        else:
            self._emit_indented(t, joined, _SOURCE)
        if len(lines) > max_lines:
            t.append("\n  …", style=_FAINT)
        return t

    @staticmethod
    def _emit_indented(t: Text, body: str, style: str) -> None:
        """Append ``body`` with a two-space gutter on every line."""
        parts = body.split("\n")
        for idx, part in enumerate(parts):
            if idx > 0:
                t.append("\n")
            t.append("  ", style=DIM)
            t.append(part, style=style)

    @staticmethod
    def _first_line(s: str, n: int = 60) -> str:
        line = (s.splitlines() or [""])[0]
        return line if len(line) <= n else line[: n - 1] + "…"

    def _preview(self, f: Finding) -> tuple[str, Text]:
        body = Text()
        if f.fixability is Fixability.AUTO:
            old = self._first_line(f.matched_text)
            new = self._first_line(f.replacement) if f.replacement else "(removed)"
            body.append("  − ", style=BAD)
            body.append(old + "\n", style=_SOURCE)
            body.append("  + ", style=OK)
            body.append(new, style=OK if f.replacement else _FAINT)
            return "FIX PREVIEW", body
        if f.fixability is Fixability.PROMPT:
            tmpl = f.replace_template or f.suggested_fix or "{value}"
            body.append("  ", style=DIM)
            self._emit_template(body, tmpl)
            if f.prompt_label:
                body.append(f"\n  you'll be asked: {f.prompt_label}", style=_FAINT)
            return "FIX PREVIEW", body
        body.append("  ", style=DIM)
        body.append(f.suggested_fix or "Review and edit by hand.", style="#9aa4b8")
        return "SUGGESTED FIX", body

    @staticmethod
    def _emit_template(t: Text, tmpl: str) -> None:
        """Render a PROMPT template, highlighting the ``{value}`` placeholder."""
        marker = "{value}"
        if marker in tmpl:
            i = tmpl.index(marker)
            t.append(tmpl[:i], style="#9aa4b8")
            t.append("value", style=f"bold #0b0e14 on {ACCENT}")
            t.append(tmpl[i + len(marker):], style="#9aa4b8")
        else:
            t.append(tmpl, style="#9aa4b8")

    def _action_hint(self, f: Finding) -> Text:
        t = Text()

        def key(k: str, label: str) -> None:
            t.append(f" {k} ", style=f"bold #0b0e14 on {ACCENT}")
            t.append(f" {label}  ", style=DIM)

        if f.status is not Status.OPEN:
            t.append("already handled — ", style=_FAINT)
            t.append("pick another finding", style=DIM)
            return t
        if f.fixability is Fixability.AUTO:
            key("f", "apply fix")
        elif f.fixability is Fixability.PROMPT:
            key("f", "fix + value")
        else:
            key("a", "annotate")
        key("s", "skip")
        key("i", "not slop")
        return t

    def _detail(self, f: Finding) -> Text:
        t = Text()
        t.append(SEVERITY_ICON[f.severity] + " ", style=f"bold {SEVERITY_COLORS[f.severity]}")
        t.append(f.severity.value.upper(), style=f"bold {SEVERITY_COLORS[f.severity]}")
        t.append("   ·   ", style=_FAINT)
        t.append(CATEGORY_ICON[f.category] + " ", style=CATEGORY_COLORS[f.category])
        t.append(f.category.value, style=f"bold {CATEGORY_COLORS[f.category]}")
        t.append("\n\n")
        t.append(f.message + "\n\n", style=_TEXT)

        t.append(f"{f.file}:{f.line}:{f.col}\n", style=DIM)
        t.append("confidence  ", style=DIM)
        t.append_text(self._conf_meter(f.confidence))
        t.append("\n")
        t.append(FIX_ICON[f.fixability.value] + " ", style=FIX_COLOR[f.fixability.value])
        t.append(self._fix_phrase(f.fixability), style=FIX_COLOR[f.fixability.value])
        t.append("     status  ", style=DIM)
        t.append_text(self._status_text(f.status))
        t.append("\n\n")

        t.append("SOURCE\n", style=f"bold {DIM}")
        t.append_text(self._source_block(f))
        t.append("\n\n")

        title, body = self._preview(f)
        t.append(title + "\n", style=f"bold {DIM}")
        t.append_text(body)
        t.append("\n\n")
        t.append_text(self._action_hint(f))
        return t

    # ----------------------------------------------------------------- helpers
    def _tree(self) -> Tree | None:
        """The findings tree, or None on a clean project (no tree composed)."""
        try:
            return self.query_one("#tree", Tree)
        except NoMatches:
            return None

    def _current(self) -> Finding | None:
        tree = self._tree()
        if tree is None:
            return None
        node = tree.cursor_node
        if node is not None and isinstance(node.data, Finding):
            return node.data
        return None

    def _record(self, f: Finding) -> None:
        """Persist how a finding was handled, so re-scans don't re-report it."""
        store = getattr(self.app, "store", None)
        if store is not None:
            store.record(f)

    def _refresh_node(self, f: Finding) -> None:
        node = self._leaf_nodes.get(f.key)
        if node is not None:
            node.set_label(self._leaf_label(f))
        self.query_one("#detail", Static).update(self._detail(f))

    def _refresh_counters(self) -> None:
        from ..widgets import StatChip

        fixed = sum(1 for f in self._findings if f.status in (Status.FIXED, Status.ANNOTATED))
        skipped = sum(1 for f in self._findings if f.status in (Status.SKIPPED, Status.IGNORED))
        remaining = sum(1 for f in self._findings if f.status is Status.OPEN)
        self.query_one("#c-found", StatChip).set_target(len(self._findings))
        self.query_one("#c-fixed", StatChip).set_target(fixed)
        self.query_one("#c-skip", StatChip).set_target(skipped)
        self.query_one("#c-left", StatChip).set_target(remaining)

    def _advance(self) -> None:
        tree = self._tree()
        if tree is not None:
            tree.action_cursor_down()

    # ----------------------------------------------------------------- actions
    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if isinstance(event.node.data, Finding):
            self.query_one("#detail", Static).update(self._detail(event.node.data))

    def action_fix(self) -> None:
        f = self._current()
        if f is None:
            return
        if f.status is not Status.OPEN:
            self.notify("Already handled.", severity="warning", timeout=2)
            return
        if f.fixability is Fixability.AUTO:
            self._do_fix(f, None)
        elif f.fixability is Fixability.PROMPT:
            def callback(value: str | None, finding: Finding = f) -> None:
                if value is not None:
                    self._do_fix(finding, value)
            self.app.push_screen(PromptModal(f), callback)
        else:
            self.notify("Manual only — use [a]nnotate or [s]kip.", severity="warning", timeout=3)

    def _do_fix(self, f: Finding, value: str | None) -> None:
        if not fixer.apply_fix(f, value):
            self.notify("Could not apply fix (content moved?).", severity="error", timeout=3)
            return
        self._record(f)
        self._refresh_node(f)
        self._refresh_counters()
        self.notify(f"✓ Fixed: {f.message}", severity="information", timeout=2)
        self._advance()

    def action_skip(self) -> None:
        f = self._current()
        if f is None or f.status is not Status.OPEN:
            return
        f.status = Status.SKIPPED
        self._record(f)
        self._refresh_node(f)
        self._refresh_counters()
        self._advance()

    def action_annotate(self) -> None:
        f = self._current()
        if f is None or f.status is not Status.OPEN:
            return
        if fixer.annotate(f):
            self._record(f)
            self._refresh_node(f)
            self._refresh_counters()
            self.notify("✎ Annotated in source.", severity="information", timeout=2)
            self._advance()

    def action_ignore(self) -> None:
        """Mark the finding as not-slop: suppress it now and in future scans.

        The (rule_id, matched_text) signature is persisted to the project
        allowlist, and every other open finding with the same signature — the
        same token across every file — is set aside in one shot.
        """
        f = self._current()
        if f is None or f.status is not Status.OPEN:
            return
        allow = getattr(self.app, "allowlist", None)
        if allow is not None:
            allow.add(f)
        sig = (f.rule_id, f.matched_text)
        n = 0
        for g in self._findings:
            if g.status is Status.OPEN and (g.rule_id, g.matched_text) == sig:
                g.status = Status.IGNORED
                self._record(g)
                self._refresh_node(g)
                n += 1
        self._refresh_counters()
        token = f.matched_text.strip() or f.message
        extra = f" (+{n - 1} elsewhere)" if n > 1 else ""
        self.notify(f"⊘ Marked not-slop: {token}{extra}", severity="information", timeout=3)
        self._advance()

    def action_fix_auto(self) -> None:
        auto_open = [
            f for f in self._findings
            if f.status is Status.OPEN and f.fixability is Fixability.AUTO
        ]
        targets = [f for f in auto_open if f.confidence >= AUTO_FIX_FLOOR]
        skipped = len(auto_open) - len(targets)
        if not targets:
            self.notify("No automatic fixes available.", severity="warning", timeout=2)
            return
        n = 0
        for f in targets:
            if fixer.apply_fix(f, None):
                self._record(f)
                self._refresh_node(f)
                n += 1
        self._refresh_counters()
        extra = f" (skipped {skipped} low-confidence)" if skipped else ""
        self.notify(
            f"⚡ Applied {n} automatic fix(es).{extra}",
            severity="information",
            timeout=3,
        )

    def action_toggle(self) -> None:
        tree = self._tree()
        if tree is None:
            return
        node = tree.cursor_node
        if node is not None and node.children:
            node.toggle()

    def action_summary(self) -> None:
        self.app.show_summary()
