"""Apply fixes to source files, with backups and offset-resilient relocation."""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path

from .engine.models import Finding, Fixability, Status
from .engine.util import line_col, make_snippet

BACKUP_SUFFIX = ".aislopfixer.bak"


def make_backup(abs_path: str) -> str | None:
    """Copy a file to ``<file>.aislopfixer.bak`` once (idempotent)."""
    bak = abs_path + BACKUP_SUFFIX
    if not Path(bak).exists():
        shutil.copy2(abs_path, bak)
    return bak


def _read_text(path: Path) -> tuple[str, str, bool]:
    """``(LF-normalized text, original newline, had_bom)`` for a source file.

    Finding offsets are computed against LF-normalized, BOM-stripped text (the
    scanner reads with universal newlines and ``utf-8-sig``), so edits must
    happen in that exact form — but writing the result back must not silently
    convert the file's line endings or drop its BOM.
    """
    raw = path.read_bytes().decode("utf-8")
    bom = raw.startswith("﻿")
    if bom:
        raw = raw[1:]
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n").replace("\r", "\n"), newline, bom


def _write_text(path: Path, text: str, newline: str, bom: bool) -> None:
    """Write LF-normalized ``text`` back with the original newline and BOM."""
    path.write_text(("﻿" if bom else "") + text, encoding="utf-8", newline=newline)


def snapshot_file(abs_path: str) -> tuple[str, str, bool] | None:
    """Capture a file's exact restorable state (text, newline, BOM) for undo."""
    try:
        return _read_text(Path(abs_path))
    except (OSError, UnicodeDecodeError):
        return None


def restore_file(abs_path: str, state: tuple[str, str, bool]) -> bool:
    """Write a :func:`snapshot_file` state back; True on success."""
    text, newline, bom = state
    try:
        _write_text(Path(abs_path), text, newline, bom)
    except OSError:
        return False
    return True


def _locate(text: str, finding: Finding) -> tuple[int, int] | None:
    """Return the current (start, end) of the finding, surviving prior edits."""
    s, e = finding.start, finding.end
    if 0 <= s <= e <= len(text) and text[s:e] == finding.matched_text:
        return s, e
    needle = finding.matched_text
    if not needle:
        return None  # cannot relocate an empty anchor
    idx = text.find(needle, max(0, s - 250))
    if idx == -1:
        idx = text.find(needle)
    if idx == -1:
        return None
    return idx, idx + len(needle)


def _consume_trailing_newline(text: str, start: int, end: int) -> int:
    """When deleting a whole line, also drop its trailing newline."""
    line_start = text.rfind("\n", 0, start) + 1
    is_full_line = line_start == start and (end >= len(text) or text[end] == "\n")
    if is_full_line and end < len(text) and text[end] == "\n":
        return end + 1
    return end


def compute_new_text(text: str, finding: Finding, value: str | None) -> str | None:
    """Return the file text with the finding's fix applied, or None if not fixable."""
    span = _locate(text, finding)
    if span is None:
        return None
    start, end = span

    if finding.fixability is Fixability.AUTO:
        repl = finding.replacement
        if repl == "" and start < end:
            end = _consume_trailing_newline(text, start, end)
        return text[:start] + repl + text[end:]

    if finding.fixability is Fixability.PROMPT:
        if value is None:
            return None
        repl = (
            finding.replace_template.format(value=value)
            if finding.replace_template
            else value
        )
        return text[:start] + repl + text[end:]

    return None  # MANUAL


def diff_preview(finding: Finding, value: str | None = None) -> str | None:
    """Unified diff of the change the fix would make, or None if not applicable."""
    try:
        text, _, _ = _read_text(Path(finding.abs_path))
    except (OSError, UnicodeDecodeError):
        return None
    new_text = compute_new_text(text, finding, value)
    if new_text is None or new_text == text:
        return None
    diff = difflib.unified_diff(
        text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=finding.file,
        tofile=finding.file + " (fixed)",
        n=1,
    )
    return "".join(diff)


def apply_fix(finding: Finding, value: str | None = None, *, backup: bool = True) -> bool:
    """Apply a single finding's fix to its file. Returns True on success."""
    path = Path(finding.abs_path)
    try:
        text, newline, bom = _read_text(path)
    except (OSError, UnicodeDecodeError):
        return False
    new_text = compute_new_text(text, finding, value)
    if new_text is None or new_text == text:
        return False
    if backup:
        make_backup(finding.abs_path)
    _write_text(path, new_text, newline, bom)
    finding.status = Status.FIXED
    return True


def _comment_for(path: str, msg: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"}:
        # SFCs are mostly JS in <script>; // is valid there and harmless in
        # markup as a non-tag line the next scan will still recognize.
        return f"// aislopfixer: {msg}"
    if ext == ".css":
        return f"/* aislopfixer: {msg} */"
    if ext in {".md", ".mdx"}:
        return f"<!-- aislopfixer: {msg} -->"
    return f"<!-- aislopfixer: {msg} -->"


def annotate(finding: Finding, *, backup: bool = True) -> bool:
    """Insert a comment marker on the line above the finding."""
    path = Path(finding.abs_path)
    try:
        text, newline, bom = _read_text(path)
    except (OSError, UnicodeDecodeError):
        return False
    span = _locate(text, finding)
    start = span[0] if span else min(finding.start, len(text))
    line_start = text.rfind("\n", 0, start) + 1
    line = text[line_start:text.find("\n", line_start) if text.find("\n", line_start) != -1 else len(text)]
    indent = line[: len(line) - len(line.lstrip())]
    comment = indent + _comment_for(finding.abs_path, finding.message) + "\n"
    new_text = text[:line_start] + comment + text[line_start:]
    if backup:
        make_backup(finding.abs_path)
    _write_text(path, new_text, newline, bom)
    finding.status = Status.ANNOTATED
    return True


def reanchor(findings: list[Finding]) -> None:
    """Recompute line/col/snippet of OPEN findings from current file content.

    A fix that deletes lines shifts every finding below it; the shifted
    findings would otherwise be reported (and rendered) at their pre-fix
    positions. Groups by file so each file is read once; findings whose
    ``matched_text`` can no longer be found are left untouched.
    """
    by_path: dict[str, list[Finding]] = {}
    for f in findings:
        if f.status is Status.OPEN:
            by_path.setdefault(f.abs_path, []).append(f)
    for abs_path, group in by_path.items():
        try:
            text, _, _ = _read_text(Path(abs_path))
        except (OSError, UnicodeDecodeError):
            continue
        for f in group:
            span = _locate(text, f)
            if span is None:
                continue
            f.start, f.end = span
            f.line, f.col = line_col(text, f.start)
            f.snippet = make_snippet(text, f.start, f.end)
