"""Detect leftover version-control conflict markers.

A merge/rebase that was resolved by an AI paste (or never resolved at all) often
leaves the literal conflict markers behind::

    <<<<<<< HEAD
    const port = 3000;
    =======
    const port = 8080;
    >>>>>>> feature/config

These are not *slop* in the marketing sense — they are broken source. A file
carrying them does not parse and ships a merge the author never finished. We flag
every marker line at ERROR severity. The fix is inherently MANUAL: resolving a
conflict means *choosing a side*, which no rule can do safely.

Markers are matched only as whole lines starting at column 0, exactly seven
characters wide — git's fixed width. The ``=======`` divider is ambiguous on its
own (a Markdown setext underline, a comment rule), so it is reported only when
the file also contains a ``<<<<<<<`` opener — i.e. a real conflict is present.
"""

from __future__ import annotations

import re

from ..models import Category, Fixability, Severity, SourceFile, Finding
from ..registry import file_rule
from ..util import build_finding

# Whole-line markers, exactly seven characters wide (git's marker width).
_OPEN = re.compile(r"(?m)^<{7}(?= |\r?$).*$")
_MID = re.compile(r"(?m)^={7}\r?$")
_BASE = re.compile(r"(?m)^\|{7}(?= |\r?$).*$")   # diff3 common-ancestor section
_CLOSE = re.compile(r"(?m)^>{7}(?= |\r?$).*$")


@file_rule
class MergeConflictRule:
    category = Category.CODE_SLOP

    def scan(self, sf: SourceFile) -> list[Finding]:
        text = sf.text
        opens = list(_OPEN.finditer(text))
        # The divider alone is too common to trust; require a real conflict opener
        # somewhere in the file before believing a bare ``=======`` line.
        has_conflict = bool(opens)
        out: list[Finding] = []

        def flag(m: re.Match, what: str) -> None:
            out.append(
                build_finding(
                    sf,
                    rule_id="merge.conflict_marker",
                    category=self.category,
                    severity=Severity.ERROR,
                    message=f"Unresolved merge conflict marker ({what})",
                    start=m.start(),
                    end=m.end(),
                    fixability=Fixability.MANUAL,
                    suggested_fix="Resolve the conflict: keep one side, delete the markers",
                )
            )

        for m in opens:
            flag(m, "<<<<<<<")
        for m in _BASE.finditer(text):
            flag(m, "|||||||")
        for m in _CLOSE.finditer(text):
            flag(m, ">>>>>>>")
        if has_conflict:
            for m in _MID.finditer(text):
                flag(m, "=======")
        return out
