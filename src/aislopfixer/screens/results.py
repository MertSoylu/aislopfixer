"""Results screen: browse findings and apply interactive fixes.

Navigation model: a category → file → finding tree on the left, a rich detail
pane on the right. Findings can be filtered by severity (1/2/3, 0 clears) and
handled items hidden (h); ? opens the keyboard reference.
"""

from __future__ import annotations

from collections import defaultdict

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Static, Tree
from textual.widgets.tree import TreeNode

from .. import fixer
from ..engine.models import Category, Finding, Fixability, Status
from ..engine.scoring import file_score, project_score_from_findings
from ..headless import AUTO_FIX_FLOOR, MAX_FIX_PASSES  # keep bulk fix in step with --fix
from ..pipeline import rescan_paths
from .base import AdaptiveScreen
from ..screens.modal import ConfirmModal, DiffModal, ExportModal, HelpModal, PromptModal
from ..theme import (
    ACCENT,
    BAD,
    BG,
    BORDER,
    CATEGORY_COLORS,
    CATEGORY_ICON,
    DIM,
    FAINT,
    FIX_COLOR,
    FIX_ICON,
    IMPACT_BLURB,
    IMPACT_COLORS,
    IMPACT_LABEL,
    MUTED,
    OK,
    SEVERITY_COLORS,
    SEVERITY_ICON,
    SOURCE,
    TEXT,
    WARN,
)

_HELP_ROWS: list[tuple[str, str]] = [
    ("WHAT THE TAGS MEAN", ""),
    ("BROKEN", "This code does not work as written — fix before shipping"),
    ("RISKY", "It runs, but ships a real hazard (sink, dead link, fake data)"),
    ("·", "Untagged: a simple warning — voice/aesthetics, not a defect"),
    ("ACT ON A FINDING", ""),
    ("f", "Fix it (auto, or prompts you for the real value)"),
    ("d", "Preview the exact diff the fix would make"),
    ("a", "Annotate it in the source (manual-review items)"),
    ("s", "Skip for now — it resurfaces on the next scan"),
    ("i", "Not slop — allowlists this token across the project"),
    ("u", "Undo the last fix / annotate (restores the file)"),
    ("BULK & EXPORT", ""),
    ("p", "Apply every high-confidence automatic fix at once"),
    ("s i", "On a category/file row: skip / not-slop the whole branch"),
    ("x", "AI fix brief: details BROKEN/RISKY, sums up the warnings"),
    ("VIEW & FILTER", ""),
    ("1 2 3", "Show only errors / warnings / info (again to clear)"),
    ("0", "Clear the severity filter"),
    ("c", "Cycle the confidence floor (all → 45 → 60 → 75%)"),
    ("h", "Toggle: hide already-handled findings"),
    ("NAVIGATE", ""),
    ("↑ ↓", "Move between findings"),
    ("e", "Expand / collapse the selected branch"),
    ("q", "Finish and open the summary"),
]


class ResultsScreen(AdaptiveScreen):
    MIN_WIDTH = 80
    MIN_HEIGHT = 20

    # Only six bindings are shown: the footer drops whatever overflows, and it
    # needed ~110 columns for nine — so at a classic 80x24 the last two silently
    # vanished, and the last two were `? Help` and `q Summary`. Help must not be
    # undiscoverable at exactly the size where the tree is hardest to read.
    # d/a/i stay off the footer because the detail pane's action hint already
    # offers them on the findings they apply to, and ? documents every key.
    BINDINGS = [
        Binding("f", "fix", "Fix"),
        Binding("d", "diff", "Diff", show=False),
        Binding("s", "skip", "Skip"),
        Binding("a", "annotate", "Annotate", show=False),
        Binding("i", "ignore", "Not slop", show=False),
        Binding("u", "undo", "Undo", show=False),
        Binding("p", "fix_auto", "Fix all"),
        Binding("x", "export", "Fix brief"),
        Binding("c", "conf_filter", "Confidence floor", show=False),
        Binding("e", "toggle", "Expand/Collapse", show=False),
        Binding("h", "hide_handled", "Hide handled", show=False),
        Binding("1", "filter('error')", "Errors only", show=False),
        Binding("2", "filter('warning')", "Warnings only", show=False),
        Binding("3", "filter('info')", "Info only", show=False),
        Binding("0", "filter('all')", "Show all", show=False),
        Binding("question_mark", "help", "Help", key_display="?"),
        Binding("q", "summary", "Summary"),
    ]

    # Confidence-floor steps the `c` key cycles through (0.0 = show all).
    _CONF_STEPS = (0.0, 0.45, 0.60, 0.75)

    def __init__(self, findings: list[Finding]) -> None:
        super().__init__()
        self._findings = findings
        self._leaf_nodes: dict[str, TreeNode] = {}
        self._sev: str | None = None      # severity filter: "error"/"warning"/"info"
        self._hide_handled = False
        self._conf = 0.0                  # confidence floor (mirrors --min-confidence)
        # LIFO of file-mutating actions; each entry restores file contents and
        # finding statuses exactly as they were before that action.
        self._undo: list[dict] = []

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
                yield self._chip("c-left", "Remaining", WARN, "▲")
            if self._findings:
                yield Static(self._brief_hint(), id="results-hint")
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
            t.append("  ·  ", style=FAINT)
            t.append(str(target), style=DIM)
        return t

    def _brief_hint(self) -> Text:
        """One always-visible line: the impact split.

        The headline number is *application problems*, not the total. "41
        findings need judgement" was true and useless — 31 of those 41 were
        single-word buzzwords. Naming the two classes separately is what makes
        the screen readable, and the fix brief leads on the same split.

        Nothing else rides on this line. It is ``no_wrap``, so the "press x for
        an AI fix brief (a ready prompt for Claude Code / Cursor / Copilot)"
        tail it used to carry was simply cut off at 80 columns, leaving the line
        ending on a dangling "—". The footer teaches ``x``; this says what the
        number is.
        """
        open_ = [f for f in self._findings if f.status is Status.OPEN]
        problems = sum(1 for f in open_ if f.impact.is_application)
        warnings = len(open_) - problems
        t = Text(no_wrap=True, overflow="ellipsis")
        if not open_:
            t.append("✨ press ", style=FAINT)
            t.append("x", style=f"bold {ACCENT}")
            t.append(" to export the findings — AI fix brief, JSON or SARIF", style=FAINT)
            return t
        if problems:
            t.append("▲ ", style=WARN)
            t.append(f"{problems} application problem(s)", style=f"bold {WARN}")
            t.append(" (broken or risky)", style=FAINT)
        else:
            t.append("✓ ", style=OK)
            t.append("no application problems", style=f"bold {OK}")
        if warnings:
            t.append("  ·  ", style=FAINT)
            t.append(f"{warnings} simple warning(s)", style=DIM)
        return t

    def _slop_score(self) -> int:
        """Project slop over *unresolved* findings — drops as the user fixes."""
        live = [
            f for f in self._findings
            if f.status in (Status.OPEN, Status.SKIPPED)
        ]
        return round(project_score_from_findings(live) * 100)

    def _clean_banner(self) -> Text:
        t = Text(justify="center")
        scanned = getattr(self.app, "files_scanned", None)
        if scanned == 0:
            # An empty folder is not a clean project — don't claim it is.
            t.append("\n◇  NOTHING TO SCAN  ◇\n\n", style=f"bold {WARN}")
            t.append(
                "No scannable web files here (html, js/ts, css, md, …).\n\n",
                style=TEXT,
            )
        else:
            t.append("\n✦  NO SLOP DETECTED  ✦\n\n", style=f"bold {OK}")
            if scanned:
                t.append(f"{scanned} file(s) scanned — this project came back clean.\n\n", style=TEXT)
            else:
                t.append("This project came back clean.\n\n", style=TEXT)
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
            self.query_one("#detail", Static).border_title = "DETAIL"
            self._build_tree()
        self._refresh_counters()
        self.call_after_refresh(self._fit)

    # ---------------------------------------------------------------- filtering
    def _visible(self) -> list[Finding]:
        out = self._findings
        if self._sev is not None:
            out = [f for f in out if f.severity.value == self._sev]
        if self._hide_handled:
            out = [f for f in out if f.status is Status.OPEN]
        if self._conf:
            out = [f for f in out if f.confidence >= self._conf]
        return out

    def _filter_tag(self, visible: int) -> str:
        parts: list[str] = []
        if self._sev is not None:
            parts.append(f"{self._sev}s only")
        if self._hide_handled:
            parts.append("open only")
        if self._conf:
            parts.append(f"conf ≥ {round(self._conf * 100)}%")
        tag = " · ".join(parts)
        count = f"{visible}/{len(self._findings)}"
        return f"{tag} · {count}" if tag else count

    def _build_tree(self) -> None:
        tree = self._tree()
        if tree is None:
            return
        tree.clear()
        tree.show_root = False
        tree.guide_depth = 3
        self._leaf_nodes = {}
        visible = self._visible()
        tree.border_title = "FINDINGS"
        tree.border_subtitle = self._filter_tag(len(visible))

        detail = self.query_one("#detail", Static)
        if not visible:
            detail.update(self._empty_filter_note())
            return

        by_cat: dict[Category, dict[str, list[Finding]]] = defaultdict(lambda: defaultdict(list))
        for f in visible:
            by_cat[f.category][f.file].append(f)

        first_leaf: TreeNode | None = None
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
                # Impact first: a BROKEN import outranks a 97%-confidence
                # buzzword, because confidence answers "is this really slop?"
                # and impact answers "does this break my application?".
                items.sort(key=lambda f: (-f.impact.rank, -f.confidence, f.line))
                score = file_score(items)
                file_label = Text(no_wrap=True, overflow="ellipsis")
                file_label.append(f"{self._basename(path)} ", style=TEXT)
                file_label.append(f"{len(items)} ", style=DIM)
                file_label.append_text(self._mini_bar(score))
                file_node = cat_node.add(file_label, expand=True)
                for f in items:
                    leaf = file_node.add_leaf(self._leaf_label(f), data=f)
                    self._leaf_nodes[f.key] = leaf
                    if first_leaf is None:
                        first_leaf = leaf

        detail.update(self._detail(visible[0]))
        if first_leaf is not None:
            # Start with a finding under the cursor — otherwise nothing is
            # selected and the first f/d/s/i press silently does nothing.
            # Deferred: node line numbers exist only after the next refresh.
            self.call_after_refresh(tree.move_cursor, first_leaf)

    def _empty_filter_note(self) -> Text:
        """Offer a way out for each *active* filter — never a key that does nothing."""
        outs: list[tuple[str, str]] = []
        if self._sev is not None:
            outs.append(("0", "to clear the severity filter"))
        if self._hide_handled:
            outs.append(("h", "to show handled items"))
        if self._conf:
            outs.append(("c", "to drop the confidence floor"))
        t = Text()
        t.append("No findings match this view.\n\n", style=TEXT)
        if not outs:  # no filter active — the tree really is empty
            t.append("Nothing to show here.", style=DIM)
            return t
        t.append("Press ", style=DIM)
        for i, (key, what) in enumerate(outs):
            if i:
                t.append(" or ", style=DIM)
            t.append(f" {key} ", style=f"bold {BG} on {ACCENT}")
            t.append(f" {what}", style=DIM)
        t.append(".", style=DIM)
        return t

    @staticmethod
    def _basename(path: str) -> str:
        return path.replace("\\", "/").rsplit("/", 1)[-1]

    @staticmethod
    def _slop_color(score: float) -> str:
        if score >= 0.75:
            return BAD
        if score >= 0.45:
            return WARN
        return DIM

    def _mini_bar(self, score: float, cells: int = 5) -> Text:
        color = self._slop_color(score)
        filled = int(round(score * cells))
        t = Text()
        t.append("▰" * filled, style=color)
        t.append("▱" * (cells - filled), style=BORDER)
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
        # Only application problems are tagged — POLISH is the bulk of any tree
        # and a tag on every row would mark nothing. An unlabelled row *is* the
        # signal that this one is just taste.
        label = IMPACT_LABEL[f.impact]
        if label:
            t.append(f"{label} ", style=f"bold {IMPACT_COLORS[f.impact]}")
        body_style = DIM if f.status is not Status.OPEN else TEXT
        t.append(f"{self._trunc(f.message, 40)} ", style=body_style)
        t.append(f"L{f.line} ", style=FAINT)
        t.append(FIX_ICON[f.fixability.value], style=FIX_COLOR[f.fixability.value])
        return t

    # --------------------------------------------------------------- detail pane
    def _conf_meter(self, conf: float, cells: int = 5) -> Text:
        color = OK if conf >= 0.75 else WARN if conf >= 0.45 else DIM
        filled = int(round(conf * cells))
        t = Text()
        t.append("▰" * filled, style=color)
        t.append("▱" * (cells - filled), style=BORDER)
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
    def _impact_line(f: Finding) -> Text:
        """The impact tag plus the sentence that says what it means.

        Fixability says *how* to fix; this says *what is at stake*. Without it
        an SQLi sink and the word "seamless" both read "⚑ manual review".
        """
        color = IMPACT_COLORS[f.impact]
        t = Text()
        t.append("impact      ", style=DIM)
        t.append(f" {f.impact.value.upper()} ", style=f"bold {BG} on {color}")
        t.append("  ", style=DIM)
        t.append(IMPACT_BLURB[f.impact], style=color if f.impact.is_application else FAINT)
        return t

    @staticmethod
    def _status_text(status: Status) -> Text:
        color = {
            Status.OPEN: WARN,
            Status.FIXED: OK,
            Status.ANNOTATED: ACCENT,
            Status.SKIPPED: DIM,
            Status.IGNORED: DIM,
        }[status]
        return Text(status.value, style=f"bold {color}")

    def _source_block(self, f: Finding, max_lines: int = 12) -> Text:
        """The offending source lines, numbered, with the match highlighted."""
        if f.start == f.end == 0 and not f.matched_text:
            # Doc-level aggregate (density scores…): no single span to show —
            # quoting line 1 would point the user at innocent code.
            return Text("(applies to the whole file)", style=FAINT)
        t = Text()
        snippet = f.snippet or "—"
        lines = snippet.splitlines() or ["—"]
        clipped = lines[:max_lines]
        joined = "\n".join(clipped)
        span: tuple[int, int] | None = None
        if f.matched_text:
            # The snippet starts at the finding line's column 1, so the match
            # begins exactly at col-1 — a plain substring search could land on
            # an earlier identical occurrence elsewhere in the snippet.
            s = f.col - 1
            avail = joined[s: s + len(f.matched_text)]
            if avail and f.matched_text.startswith(avail):
                span = (s, s + len(avail))  # clipped lines may cut the match short
            elif f.matched_text in joined:
                i = joined.index(f.matched_text)
                span = (i, i + len(f.matched_text))
        pos = 0
        for k, line in enumerate(clipped):
            if k:
                t.append("\n")
            t.append(f"{f.line + k:>5} ", style=FAINT)
            t.append("│ ", style=BORDER)
            ls, le = pos, pos + len(line)
            if span and span[0] < le and span[1] > ls:
                s = max(span[0], ls) - ls
                e = min(span[1], le) - ls
                t.append(line[:s], style=SOURCE)
                t.append(line[s:e], style=f"bold {BG} on {BAD}")
                t.append(line[e:], style=SOURCE)
            else:
                t.append(line, style=SOURCE)
            pos = le + 1
        if len(lines) > max_lines:
            t.append("\n")
            t.append("      ┆ …", style=FAINT)
        return t

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
            body.append(old + "\n", style=SOURCE)
            body.append("  + ", style=OK)
            body.append(new, style=OK if f.replacement else FAINT)
            return "FIX PREVIEW", body
        if f.fixability is Fixability.PROMPT:
            tmpl = f.replace_template or f.suggested_fix or "{value}"
            body.append("  ", style=DIM)
            self._emit_template(body, tmpl)
            if f.prompt_label:
                body.append(f"\n  you'll be asked: {f.prompt_label}", style=FAINT)
            return "FIX PREVIEW", body
        body.append("  ", style=DIM)
        body.append(f.suggested_fix or "Review and edit by hand.", style=MUTED)
        body.append("\n  or let your AI assistant do it: ", style=FAINT)
        body.append("x", style=f"bold {BG} on {ACCENT}")
        # Say which half of the brief this finding lands in, so the offer is
        # never oversold: POLISH is rolled up there, not written out.
        body.append(
            " exports a fix brief — this one is written out in full"
            if f.impact.is_application
            else " exports a fix brief — this one is summarized there, not detailed",
            style=FAINT,
        )
        return "SUGGESTED FIX", body

    @staticmethod
    def _emit_template(t: Text, tmpl: str) -> None:
        """Render a PROMPT template, highlighting the ``{value}`` placeholder."""
        marker = "{value}"
        if marker in tmpl:
            i = tmpl.index(marker)
            t.append(tmpl[:i], style=MUTED)
            t.append("value", style=f"bold {BG} on {ACCENT}")
            t.append(tmpl[i + len(marker):], style=MUTED)
        else:
            t.append(tmpl, style=MUTED)

    def _action_hint(self, f: Finding) -> Text:
        t = Text()

        def key(k: str, label: str) -> None:
            t.append(f" {k} ", style=f"bold {BG} on {ACCENT}")
            t.append(f" {label}  ", style=DIM)

        if f.status is not Status.OPEN:
            t.append("already handled — ", style=FAINT)
            t.append("pick another finding", style=DIM)
            return t
        if f.fixability is Fixability.AUTO:
            key("f", "apply fix")
            key("d", "diff")
        elif f.fixability is Fixability.PROMPT:
            key("f", "fix + value")
            key("d", "diff")
        else:
            key("a", "annotate")
            key("x", "AI fix brief")
        key("s", "skip")
        key("i", "not slop")
        return t

    def _detail(self, f: Finding) -> Text:
        t = Text()
        t.append(SEVERITY_ICON[f.severity] + " ", style=f"bold {SEVERITY_COLORS[f.severity]}")
        t.append(f.severity.value.upper(), style=f"bold {SEVERITY_COLORS[f.severity]}")
        t.append("   ·   ", style=FAINT)
        t.append(CATEGORY_ICON[f.category] + " ", style=CATEGORY_COLORS[f.category])
        t.append(f.category.value, style=f"bold {CATEGORY_COLORS[f.category]}")
        t.append("   ·   ", style=FAINT)
        t.append(f.rule_id, style=FAINT)
        t.append("\n\n")
        t.append(f.message + "\n\n", style=TEXT)

        t.append(f"{f.file}:{f.line}:{f.col}\n", style=DIM)
        t.append("confidence  ", style=DIM)
        t.append_text(self._conf_meter(f.confidence))
        t.append("  ", style=DIM)
        t.append("is this really slop?", style=FAINT)
        t.append("\n")
        t.append_text(self._impact_line(f))
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

    def _branch(self) -> tuple[TreeNode, list[Finding]] | None:
        """The cursor's category/file node and every OPEN finding under it."""
        tree = self._tree()
        if tree is None:
            return None
        node = tree.cursor_node
        if node is None or isinstance(node.data, Finding) or not node.children:
            return None
        items: list[Finding] = []

        def walk(n: TreeNode) -> None:
            for child in n.children:
                if isinstance(child.data, Finding):
                    if child.data.status is Status.OPEN:
                        items.append(child.data)
                else:
                    walk(child)

        walk(node)
        return node, items

    # -------------------------------------------------------------------- undo
    def _push_undo(self, label: str, abs_paths: set[str],
                   affected: list[Finding]) -> dict:
        """Snapshot files + statuses *before* a mutating action. Returns the entry."""
        entry: dict = {
            "label": label,
            "files": {},
            "statuses": [(f, f.status) for f in affected],
            "added": [],   # findings born during the action (fixpoint passes)
        }
        for p in abs_paths:
            state = fixer.snapshot_file(p)
            if state is not None:
                entry["files"][p] = state
        self._undo.append(entry)
        return entry

    def action_undo(self) -> None:
        if not self._undo:
            self.notify("Nothing to undo.", severity="warning", timeout=2)
            return
        entry = self._undo.pop()
        for p, state in entry["files"].items():
            fixer.restore_file(p, state)
        for f, prev in entry["statuses"]:
            f.status = prev
            self._record(f, flush=False)
        for f in entry["added"]:
            if f in self._findings:
                self._findings.remove(f)
        self._flush_store()
        restored = [g for g in self._findings if g.abs_path in entry["files"]]
        fixer.reanchor(restored)
        self._build_tree()
        self._refresh_counters()
        self.notify(f"↶ Undid: {entry['label']}.", severity="information", timeout=2)

    def _record(self, f: Finding, *, flush: bool = True) -> None:
        """Persist how a finding was handled, so re-scans don't re-report it.

        Pass ``flush=False`` inside a bulk loop, then call :meth:`_flush_store`
        once afterwards to collapse N disk writes into one.
        """
        store = getattr(self.app, "store", None)
        if store is not None:
            store.record(f, flush=flush)

    def _flush_store(self) -> None:
        store = getattr(self.app, "store", None)
        if store is not None:
            store.flush()

    def _refresh_label(self, f: Finding) -> None:
        """Repaint a leaf's label only — no detail-pane redraw."""
        node = self._leaf_nodes.get(f.key)
        if node is not None:
            node.set_label(self._leaf_label(f))

    def _refresh_node(self, f: Finding) -> None:
        self._refresh_label(f)
        self.query_one("#detail", Static).update(self._detail(f))

    def _refresh_counters(self) -> None:
        from ..widgets import SlopBadge, StatChip

        fixed = sum(1 for f in self._findings if f.status in (Status.FIXED, Status.ANNOTATED))
        skipped = sum(1 for f in self._findings if f.status in (Status.SKIPPED, Status.IGNORED))
        remaining = sum(1 for f in self._findings if f.status is Status.OPEN)
        self.query_one("#c-found", StatChip).set_target(len(self._findings))
        self.query_one("#c-fixed", StatChip).set_target(fixed)
        self.query_one("#c-skip", StatChip).set_target(skipped)
        self.query_one("#c-left", StatChip).set_target(remaining)
        self.query_one("#results-slop", SlopBadge).set_score(self._slop_score())
        try:
            self.query_one("#results-hint", Static).update(self._brief_hint())
        except NoMatches:  # clean project: no hint line composed
            pass

    def _advance(self) -> None:
        """Move the cursor to the next *finding* leaf, skipping header rows.

        A plain cursor-down can land on a category/file node, which leaves the
        detail pane stale; keep stepping until we hit a Finding or the bottom.
        """
        tree = self._tree()
        if tree is None:
            return
        for _ in range(len(self._findings) + 4):  # bounded; never loops forever
            before = tree.cursor_line
            tree.action_cursor_down()
            if tree.cursor_line == before:  # already at the bottom
                break
            node = tree.cursor_node
            if node is not None and isinstance(node.data, Finding):
                break

    # ----------------------------------------------------------------- actions
    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if isinstance(event.node.data, Finding):
            self.query_one("#detail", Static).update(self._detail(event.node.data))

    def action_filter(self, sev: str) -> None:
        """Set/toggle the severity filter; ``'all'`` (or re-pressing) clears it."""
        if self._tree() is None:
            return
        self._sev = None if sev in ("all", self._sev) else sev
        self._build_tree()

    def action_hide_handled(self) -> None:
        if self._tree() is None:
            return
        self._hide_handled = not self._hide_handled
        self._build_tree()
        self.notify(
            "Hiding handled findings." if self._hide_handled
            else "Showing all statuses again.",
            severity="information",
            timeout=2,
        )

    def action_help(self) -> None:
        self.app.push_screen(HelpModal(_HELP_ROWS))

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

    def _reanchor_file(self, f: Finding) -> None:
        """Re-anchor the still-open findings sharing ``f``'s file after an edit.

        A fix/annotation that adds or removes lines shifts everything below it;
        without this the tree's ``L<n>`` labels and the detail pane's source
        block drift away from the real file.
        """
        moved = [g for g in self._findings if g.file == f.file and g is not f]
        if not moved:
            return
        fixer.reanchor(moved)
        for g in moved:
            self._refresh_label(g)

    def _do_fix(self, f: Finding, value: str | None) -> None:
        self._push_undo(f"fix {self._basename(f.file)}:{f.line}", {f.abs_path}, [f])
        if not fixer.apply_fix(f, value):
            self._undo.pop()  # nothing changed — keep the stack honest
            self.notify("Could not apply fix (content moved?).", severity="error", timeout=3)
            return
        self._record(f)
        self._reanchor_file(f)
        self._refresh_node(f)
        self._refresh_counters()
        self.notify(f"✓ Fixed: {f.message}  (u undoes)", severity="information", timeout=2)
        self._advance()

    def action_diff(self) -> None:
        """Preview the exact unified diff a fix would apply — before trusting it."""
        f = self._current()
        if f is None:
            return
        if f.status is not Status.OPEN:
            self.notify("Already handled.", severity="warning", timeout=2)
            return
        if f.fixability is Fixability.MANUAL:
            self.notify(
                "Manual finding — no automatic change to preview. x exports a fix brief.",
                severity="warning",
                timeout=3,
            )
            return
        value = "«value»" if f.fixability is Fixability.PROMPT else None
        diff = fixer.diff_preview(f, value)
        if not diff:
            self.notify("No preview available (content moved?).", severity="error", timeout=3)
            return
        self.app.push_screen(
            DiffModal(f"{f.file}:{f.line} — {self._trunc(f.message, 42)}", diff)
        )

    def action_skip(self) -> None:
        f = self._current()
        if f is not None:
            if f.status is not Status.OPEN:
                return
            f.status = Status.SKIPPED
            self._record(f)
            self._refresh_node(f)
            self._refresh_counters()
            self._advance()
            return
        # Cursor on a category/file row: offer to skip the whole branch.
        branch = self._branch()
        if branch is None:
            return
        node, items = branch
        if not items:
            self.notify("Nothing open under this branch.", severity="warning", timeout=2)
            return

        def callback(ok: bool | None) -> None:
            if ok:
                self._bulk_skip(items)

        self.app.push_screen(
            ConfirmModal(
                f"Skip all {len(items)} open finding(s) in this branch?",
                "They resurface on the next scan — skip means later, not never.",
            ),
            callback,
        )

    def _bulk_skip(self, items: list[Finding]) -> None:
        for g in items:
            g.status = Status.SKIPPED
            self._record(g, flush=False)
            self._refresh_label(g)
        self._flush_store()
        self._refresh_counters()
        self.notify(f"→ Skipped {len(items)} finding(s).", severity="information", timeout=2)

    def action_annotate(self) -> None:
        f = self._current()
        if f is None or f.status is not Status.OPEN:
            return
        self._push_undo(
            f"annotate {self._basename(f.file)}:{f.line}", {f.abs_path}, [f]
        )
        if fixer.annotate(f):
            self._record(f)
            self._reanchor_file(f)
            self._refresh_node(f)
            self._refresh_counters()
            self.notify("✎ Annotated in source.  (u undoes)", severity="information", timeout=2)
            self._advance()
        else:
            self._undo.pop()
            self.notify(
                "Could not annotate (file unreadable or content moved?).",
                severity="error",
                timeout=3,
            )

    def action_ignore(self) -> None:
        """Mark the finding as not-slop: suppress it now and in future scans.

        The (rule_id, matched_text) signature is persisted to the project
        allowlist, and every other open finding with the same signature — the
        same token across every file — is set aside in one shot.
        """
        f = self._current()
        if f is None:
            branch = self._branch()
            if branch is None:
                return
            node, items = branch
            if not items:
                self.notify("Nothing open under this branch.", severity="warning", timeout=2)
                return

            def callback(ok: bool | None) -> None:
                if ok:
                    self._bulk_ignore(items)

            self.app.push_screen(
                ConfirmModal(
                    f"Mark all {len(items)} open finding(s) here as not-slop?",
                    "Their tokens are allowlisted — future scans stay quiet about them.",
                ),
                callback,
            )
            return
        if f.status is not Status.OPEN:
            return
        n = self._ignore_signature(f)
        self._flush_store()
        self.query_one("#detail", Static).update(self._detail(f))
        self._refresh_counters()
        token = f.matched_text.strip() or f.message
        extra = f" (+{n - 1} elsewhere)" if n > 1 else ""
        store = getattr(self.app, "store", None)
        learned = ""
        if store is not None and store.ignored_count(f.rule_id) >= 3:
            learned = " — often dismissed here; it'll rank lower next scan"
        self.notify(
            f"⊘ Marked not-slop: {token}{extra}{learned}",
            severity="information",
            timeout=3,
        )
        self._advance()

    def _ignore_signature(self, f: Finding) -> int:
        """Allowlist ``f``'s signature; set aside every open twin. Returns count."""
        allow = getattr(self.app, "allowlist", None)
        if allow is not None:
            allow.add(f)
        sig = (f.rule_id, f.matched_text)
        n = 0
        for g in self._findings:
            if g.status is Status.OPEN and (g.rule_id, g.matched_text) == sig:
                g.status = Status.IGNORED
                self._record(g, flush=False)
                self._refresh_label(g)
                n += 1
        return n

    def _bulk_ignore(self, items: list[Finding]) -> None:
        n = 0
        for g in items:
            if g.status is Status.OPEN:  # a twin may already be set aside
                n += self._ignore_signature(g)
        self._flush_store()
        self._refresh_counters()
        self.notify(
            f"⊘ Marked {n} finding(s) not-slop (allowlisted for future scans).",
            severity="information",
            timeout=3,
        )

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
        detail = f"Rewrites {len(targets)} file location(s). Backups are kept (.aislopfixer.bak)."
        if skipped:
            detail += f"  {skipped} low-confidence finding(s) left untouched."

        def callback(ok: bool | None) -> None:
            if ok:
                self._apply_auto(targets, skipped)

        self.app.push_screen(
            ConfirmModal(
                f"Apply {len(targets)} automatic fix(es)?",
                detail,
            ),
            callback,
        )

    def _apply_auto(self, targets: list[Finding], skipped: int) -> None:
        entry = self._push_undo(
            f"bulk fix ({len(targets)} finding(s))",
            {f.abs_path for f in targets},
            targets,
        )
        # High offset first — same order as headless bulk fix — so earlier
        # deletes do not scramble later spans before relocation.
        ordered = sorted(targets, key=lambda f: (f.file, f.start), reverse=True)
        n = 0
        touched: set[str] = set()
        for f in ordered:
            if fixer.apply_fix(f, None):
                self._record(f, flush=False)
                touched.add(f.file)
                n += 1
        new_open = self._fixpoint(touched, entry) if touched else 0
        extra_fixed = sum(
            1 for f in entry["added"] if f.status is Status.FIXED
        )
        self._flush_store()
        if touched:
            moved = [f for f in self._findings if f.file in touched]
            fixer.reanchor(moved)
        if not n:
            self._undo.pop()
        # Findings may have been added — rebuild the tree rather than patch labels.
        self._build_tree()
        self._refresh_counters()
        msg = f"⚡ Applied {n + extra_fixed} automatic fix(es)."
        if skipped:
            msg += f" Skipped {skipped} low-confidence."
        if new_open:
            msg += f" {new_open} new finding(s) surfaced by the fixes."
        msg += "  (u undoes)"
        self.notify(msg, severity="information", timeout=4)

    def _fixpoint(self, touched: set[str], entry: dict) -> int:
        """Re-scan just-fixed files until stable; auto-fix what fixing unmasked.

        Mirrors headless ``--fix``: a removed decoration can expose a finding
        underneath (emoji header → bare boilerplate heading). New auto-fixable
        findings are fixed immediately; the rest join the tree as OPEN. Returns
        how many new open findings appeared. Everything born here is recorded in
        ``entry["added"]`` so one undo reverses the whole bulk action.
        """
        root = str(getattr(self.app, "target_path", "") or "")
        if not root:
            return 0
        store = getattr(self.app, "store", None)
        existing = {(g.file, g.rule_id, g.matched_text) for g in self._findings}
        new_open = 0
        for _ in range(MAX_FIX_PASSES - 1):
            fresh = rescan_paths(root, set(touched), store=store)
            new_items = [
                f for f in fresh
                if (f.file, f.rule_id, f.matched_text) not in existing
            ]
            if not new_items:
                break
            auto_now = [
                f for f in new_items
                if f.fixability is Fixability.AUTO and f.confidence >= AUTO_FIX_FLOOR
            ]
            for f in new_items:
                existing.add((f.file, f.rule_id, f.matched_text))
                self._findings.append(f)
                entry["added"].append(f)
                if f not in auto_now:
                    new_open += 1
            if not auto_now:
                break
            for f in sorted(auto_now, key=lambda f: (f.file, f.start), reverse=True):
                if fixer.apply_fix(f, None):
                    self._record(f, flush=False)
                    touched.add(f.file)
        return new_open

    def action_export(self) -> None:
        """Export the open findings — everything the headless flags can emit.

        Opens a format picker (fix brief / JSON / SARIF / all); files land in
        ``.aislopfixer/`` so they are never themselves scanned. The fix brief
        is also copied to the clipboard for pasting into an AI assistant.
        """
        open_ = [f for f in self._findings if f.status is Status.OPEN]
        if not open_:
            self.notify("Nothing open — nothing to export.", severity="warning", timeout=2)
            return

        def callback(fmt: str | None) -> None:
            if fmt is not None:
                self._export(fmt, open_)

        problems = sum(1 for f in open_ if f.impact.is_application)
        self.app.push_screen(ExportModal(len(open_), problems), callback)

    def _export(self, fmt: str, open_: list[Finding]) -> None:
        from pathlib import Path

        from ..headless import _render_json, _render_sarif
        from ..prompter import render_fix_prompt

        target = str(getattr(self.app, "target_path", None) or ".")
        reported = sorted(open_, key=lambda f: (f.file, f.line, f.col))
        jobs: dict[str, tuple[str, str]] = {
            "brief": ("fix-prompt.md", render_fix_prompt(reported, target=target)),
            "json": ("findings.json", _render_json(target, reported, [])),
            "sarif": ("findings.sarif", _render_sarif(reported)),
        }
        picks = list(jobs) if fmt == "all" else [fmt]
        store = getattr(self.app, "store", None)
        out_dir = store.dir if store is not None else Path(target) / ".aislopfixer"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            for k in picks:
                name, text = jobs[k]
                (out_dir / name).write_text(text, encoding="utf-8")
        except OSError as e:
            self.notify(f"Could not export: {e}", severity="error", timeout=4)
            return
        copied = ""
        if "brief" in picks:
            try:
                self.app.copy_to_clipboard(jobs["brief"][1])
                copied = " · brief copied to clipboard"
            except Exception:
                pass
        names = ", ".join(jobs[k][0] for k in picks)
        self.notify(
            f"⇩ Exported {len(reported)} finding(s) → .aislopfixer/ ({names}){copied}",
            severity="information",
            timeout=4,
        )

    def action_conf_filter(self) -> None:
        """Cycle the confidence floor — the TUI twin of ``--min-confidence``."""
        if self._tree() is None:
            return
        i = self._CONF_STEPS.index(self._conf)
        self._conf = self._CONF_STEPS[(i + 1) % len(self._CONF_STEPS)]
        self._build_tree()
        label = "showing all" if not self._conf else f"≥ {round(self._conf * 100)}%"
        self.notify(f"Confidence floor: {label}.", severity="information", timeout=2)

    def action_toggle(self) -> None:
        tree = self._tree()
        if tree is None:
            return
        node = tree.cursor_node
        if node is not None and node.children:
            node.toggle()
        else:
            self.notify("Nothing to expand here.", severity="warning", timeout=2)

    def action_summary(self) -> None:
        self.app.show_summary()
