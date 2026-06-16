"""Base class for regex-pattern-driven file rules."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .context import file_kind
from .models import Category, Finding, Fixability, Severity, SourceFile
from .util import build_finding


@dataclass
class Pattern:
    """One regex check producing one kind of Finding."""

    id: str
    regex: re.Pattern
    severity: Severity
    fixability: Fixability
    message: str
    suggested_fix: str = ""
    group: int = 0                       # which capture group is the offending span
    replacement: str = ""                # AUTO: replacement text for the span
    replace_template: str | None = None  # PROMPT: template, e.g. 'href="{value}"'
    prompt_label: str | None = None
    expand_line: bool = False            # expand span to the whole line
    # Restrict the pattern to certain file kinds (see context.file_kind):
    # "html", "jsx", "md", "code". None means "run on every file". Use it to keep
    # markup-only checks (dead hrefs, void links) out of CSS/JS/Markdown, where
    # the same text is legitimate (a CSS selector ``a[href="#"]``, a JS string).
    kinds: frozenset[str] | None = None
    # Context gate: return True to keep a match, False to reject it. Lets a
    # pattern distinguish real slop from legitimate code that looks similar.
    guard: Callable[[re.Match, SourceFile], bool] | None = None


class PatternRule:
    """Yields findings for every match of a list of :class:`Pattern`."""

    category: Category = Category.PLACEHOLDER
    patterns: list[Pattern] = []

    def scan(self, sf: SourceFile) -> list[Finding]:
        out: list[Finding] = []
        kind = file_kind(sf.rel_path)
        for pat in self.patterns:
            if pat.kinds is not None and kind not in pat.kinds:
                continue
            for m in pat.regex.finditer(sf.text):
                if pat.guard is not None and not pat.guard(m, sf):
                    continue
                start, end = m.span(pat.group)
                out.append(
                    build_finding(
                        sf,
                        rule_id=pat.id,
                        category=self.category,
                        severity=pat.severity,
                        message=pat.message,
                        start=start,
                        end=end,
                        fixability=pat.fixability,
                        suggested_fix=pat.suggested_fix,
                        replacement=pat.replacement,
                        replace_template=pat.replace_template,
                        prompt_label=pat.prompt_label,
                        expand_line=pat.expand_line,
                    )
                )
        return out
