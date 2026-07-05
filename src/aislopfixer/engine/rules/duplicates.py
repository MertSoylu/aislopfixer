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


_SIMILARITY = 0.85   # Jaccard floor for two prose blocks to count as the "same"
_SHINGLE_K = 3       # word-gram size
_MAX_BLOCKS = 800    # safety cap on the O(blocks×clusters) pass

# ------------------------------------------------------- duplicated code blocks
# Modern generators re-emit the same helper into several files instead of
# importing it once. Much stricter than the prose pass: the block must be real
# logic (not imports/config data), long enough to be meaningful, and nearly
# token-identical — renamed variables push Jaccard below the floor, which is
# intentional (structural similarity alone is not slop).
_CODE_MIN_LINES = 8      # comment-stripped code lines per block
_CODE_SIMILARITY = 0.92
_CODE_SHINGLE_K = 5      # token-gram size
_COMMENT_LINE = re.compile(r"^\s*(?://|/\*|\*|<!--)")
_IMPORTISH_LINE = re.compile(r"^\s*(?:import|export)\b")
_LOGIC_HINT = re.compile(r"\b(?:function|class|return|if|for|while)\b|=>")


def _shingles(norm: str) -> frozenset[str]:
    """Set of word ``_SHINGLE_K``-grams — the fingerprint for fuzzy matching."""
    words = norm.split()
    if len(words) < _SHINGLE_K:
        return frozenset(words)
    return frozenset(
        " ".join(words[i:i + _SHINGLE_K]) for i in range(len(words) - _SHINGLE_K + 1)
    )


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


@cross_rule
class DuplicateRule:
    category = Category.DUPLICATE

    def scan_all(self, files: list[SourceFile]) -> list[Finding]:
        return self._scan_prose(files) + self._scan_code(files)

    # ------------------------------------------------------------- code pass
    def _scan_code(self, files: list[SourceFile]) -> list[Finding]:
        blocks: list[tuple[SourceFile, int, int, str, frozenset[str]]] = []
        for sf in files:
            if file_kind(sf.rel_path) not in ("code", "jsx"):
                continue
            for start, end, raw in self._blocks(sf.text):
                code = [
                    s for line in raw.splitlines()
                    if (s := line.strip()) and not _COMMENT_LINE.match(line)
                ]
                if len(code) < _CODE_MIN_LINES:
                    continue
                importish = sum(1 for s in code if _IMPORTISH_LINE.match(s))
                if importish / len(code) > 0.5:
                    continue  # shared import prologues are normal, not slop
                norm = " ".join(" ".join(s.split()) for s in code)
                if not _LOGIC_HINT.search(norm):
                    continue  # config/data blobs, not logic
                tokens = norm.split()
                sh = frozenset(
                    " ".join(tokens[i:i + _CODE_SHINGLE_K])
                    for i in range(max(1, len(tokens) - _CODE_SHINGLE_K + 1))
                )
                blocks.append((sf, start, end, norm, sh))
                if len(blocks) >= _MAX_BLOCKS:
                    break
            if len(blocks) >= _MAX_BLOCKS:
                break

        out: list[Finding] = []
        for occ in self._cluster(blocks, floor=_CODE_SIMILARITY):
            if len({b[0].rel_path for b in occ}) < 2:
                continue
            locs = [f"{b[0].rel_path}:{line_col(b[0].text, b[1])[0]}" for b in occ]
            for i, (sf, start, end, _norm, _sh) in enumerate(occ):
                others = ", ".join(loc for j, loc in enumerate(locs) if j != i)
                out.append(
                    build_finding(
                        sf,
                        rule_id="duplicate.code_block",
                        category=self.category,
                        severity=Severity.INFO,
                        message=(
                            f"Duplicated code block (appears {len(occ)}×; "
                            f"also at {others})"
                        ),
                        start=start,
                        end=end,
                        fixability=Fixability.MANUAL,
                        suggested_fix="Extract into a shared module and import it",
                    )
                )
        return out

    # ------------------------------------------------------------ prose pass
    def _scan_prose(self, files: list[SourceFile]) -> list[Finding]:
        # (sf, start, end, norm, shingles) for every candidate prose block.
        blocks: list[tuple[SourceFile, int, int, str, frozenset[str]]] = []
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
                blocks.append((sf, start, end, norm, _shingles(norm)))
                if len(blocks) >= _MAX_BLOCKS:
                    break
            if len(blocks) >= _MAX_BLOCKS:
                break

        out: list[Finding] = []
        for occ in self._cluster(blocks):
            # Cross-file only: the same marketing copy pasted across pages is the
            # slop we want. A block repeated within one file is usually a
            # legitimate template (list items, repeated cards), not slop.
            if len({b[0].rel_path for b in occ}) < 2:
                continue
            exact = all(b[3] == occ[0][3] for b in occ)
            label = "Duplicate" if exact else "Near-duplicate"
            locs = [f"{b[0].rel_path}:{line_col(b[0].text, b[1])[0]}" for b in occ]
            for i, (sf, start, end, _norm, _sh) in enumerate(occ):
                others = ", ".join(loc for j, loc in enumerate(locs) if j != i)
                out.append(
                    build_finding(
                        sf,
                        rule_id="duplicate.block",
                        category=self.category,
                        severity=Severity.INFO,
                        message=f"{label} prose (appears {len(occ)}×; also at {others})",
                        start=start,
                        end=end,
                        fixability=Fixability.MANUAL,
                        suggested_fix="Rewrite each instance for its page, or extract a shared component",
                    )
                )
        return out

    @staticmethod
    def _cluster(blocks, floor: float = _SIMILARITY):
        """Greedy single-linkage clustering by shingle-set Jaccard similarity.

        Each block joins the first cluster whose representative it resembles
        (≥ ``floor``); otherwise it seeds a new cluster. Catches the same
        marketing paragraph lightly reworded per page, not just byte-identical
        copies.
        """
        clusters: list[list] = []
        for b in blocks:
            for c in clusters:
                if _jaccard(b[4], c[0][4]) >= floor:
                    c.append(b)
                    break
            else:
                clusters.append([b])
        return clusters

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
