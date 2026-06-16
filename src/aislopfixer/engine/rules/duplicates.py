"""Detect duplicated *prose* blocks repeated across the project.

Duplicate detection is the weakest AI-slop signal: shared imports, repeated CSS
rules and boilerplate code are normal and not slop at all. So this rule is
deliberately conservative — it only looks at human-visible prose (page text,
markdown paragraphs), skips anything that smells like code, and reports at
INFO severity. The intent is to catch the same marketing paragraph pasted onto
five pages, not "both files import React".
"""

from __future__ import annotations

import re

from ..context import file_kind, in_any, prose_regions
from ..models import Category, Fixability, Severity, SourceFile, Finding
from ..registry import cross_rule
from ..util import build_finding, line_col

_BLOCK_SPLIT = re.compile(r"(\n\s*\n)")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_MIN_LEN = 120   # min normalized length to consider a block (prose, not a token)
_MIN_WORDS = 8   # a real duplicated paragraph, not a stray identifier list

# A block is code (not slop) if any of its lines opens with a code construct.
# Kills the "same imports in different files" false positive the user hit.
_CODE_LINE = re.compile(
    r"^[ \t]*(?:import|export|from|const|let|var|function|class|return|require|"
    r"module\.exports|package|using|#include|@import|@media|@font-face)\b",
    re.M,
)


def _looks_like_code(raw: str) -> bool:
    return bool(_CODE_LINE.search(raw))


@cross_rule
class DuplicateRule:
    category = Category.DUPLICATE

    def scan_all(self, files: list[SourceFile]) -> list[Finding]:
        seen: dict[str, list[tuple[SourceFile, int, int]]] = {}
        for sf in files:
            regions = prose_regions(sf.text, file_kind(sf.rel_path))
            for start, end, raw in self._blocks(sf.text):
                if _looks_like_code(raw):
                    continue
                if not in_any(regions, start, end):  # code files -> regions empty
                    continue
                norm = self._norm(raw)
                if len(norm) < _MIN_LEN or len(norm.split()) < _MIN_WORDS:
                    continue
                seen.setdefault(norm, []).append((sf, start, end))

        out: list[Finding] = []
        for occ in seen.values():
            # Cross-file only: the same marketing copy pasted across pages is the
            # slop we want. A block repeated within one file is usually a
            # legitimate template (list items, repeated cards), not slop.
            if len({sf.rel_path for sf, _, _ in occ}) < 2:
                continue
            locs = [f"{sf.rel_path}:{line_col(sf.text, s)[0]}" for sf, s, _ in occ]
            for i, (sf, start, end) in enumerate(occ):
                others = ", ".join(loc for j, loc in enumerate(locs) if j != i)
                out.append(
                    build_finding(
                        sf,
                        rule_id="duplicate.block",
                        category=self.category,
                        severity=Severity.INFO,
                        message=f"Duplicate prose (appears {len(occ)}×; also at {others})",
                        start=start,
                        end=end,
                        fixability=Fixability.MANUAL,
                        suggested_fix="Rewrite each instance for its page, or extract a shared component",
                    )
                )
        return out

    @staticmethod
    def _blocks(text: str):
        idx = 0
        for part in _BLOCK_SPLIT.split(text):
            if not (part.startswith("\n") and part.strip() == ""):
                if part.strip():
                    yield idx, idx + len(part), part
            idx += len(part)

    @staticmethod
    def _norm(s: str) -> str:
        s = _TAG.sub(" ", s)
        s = _WS.sub(" ", s).strip().lower()
        return s
