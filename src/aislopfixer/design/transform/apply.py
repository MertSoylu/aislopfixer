"""Write a plan to disk — reversibly, and without reformatting anything.

Three properties this module has to hold, because everything downstream of a
bad write is unrecoverable:

* **Byte-exact outside the edits.** Files are read as LF-normalised text (so the
  offsets the parser produced are valid) and written back with the file's own
  line endings and BOM. A bare ``write_text`` here would silently convert an
  entire repository to CRLF on Windows.
* **Reversible twice over.** Every touched file gets a one-time ``.bak`` copy on
  disk, and the run returns an in-memory snapshot the TUI's undo restores from.
* **Applied right-to-left.** Edits within a file are written from the end
  backwards so earlier offsets stay valid; applying forwards would shift every
  subsequent span by the length delta of the one before it.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from .plan import Edit, Plan

BACKUP_SUFFIX = ".aislopfixer.bak"

FileState = tuple[str, str, bool]      # (LF text, newline, had BOM)


def read_text(path: Path) -> FileState:
    """``(LF-normalised text, original newline, had BOM)``."""
    raw = path.read_bytes().decode("utf-8")
    bom = raw.startswith("﻿")
    if bom:
        raw = raw[1:]
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n").replace("\r", "\n"), newline, bom


def write_text(path: Path, state: FileState) -> None:
    """Write a state back with its original newline and BOM."""
    text, newline, bom = state
    path.write_text(("﻿" if bom else "") + text, encoding="utf-8",
                    newline=newline)


def make_backup(abs_path: str) -> str | None:
    """Copy a file to ``<file>.aislopfixer.bak`` once; idempotent."""
    bak = Path(abs_path + BACKUP_SUFFIX)
    if bak.exists():
        return str(bak)
    src = Path(abs_path)
    try:
        bak.write_bytes(src.read_bytes())
    except OSError:
        return None
    return str(bak)


def apply_edits(text: str, edits: list[Edit]) -> str:
    """Apply a file's edits to its text, right to left."""
    out = text
    for edit in sorted(edits, key=lambda e: -e.start):
        if not (0 <= edit.start <= edit.end <= len(out)):
            continue
        if out[edit.start:edit.end] != edit.old:
            continue          # the file moved under us; skip rather than corrupt
        out = out[:edit.start] + edit.new + out[edit.end:]
    return out


def diff_for(abs_path: str, rel_path: str, edits: list[Edit],
             context: int = 2, git: bool = False) -> str:
    """Unified diff of what a file's edits would do, or ``""``.

    ``git=True`` labels the sides ``a/…`` and ``b/…`` so the result is a patch
    a tool can consume; the default labels are for a human reading the preview.
    """
    try:
        text, _, _ = read_text(Path(abs_path))
    except (OSError, UnicodeDecodeError):
        return ""
    new = apply_edits(text, edits)
    if new == text:
        return ""
    rel = rel_path.replace("\\", "/")
    from_label = f"a/{rel}" if git else rel_path
    to_label = f"b/{rel}" if git else f"{rel_path} (yeni)"
    body = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=from_label, tofile=to_label, n=context,
    ))
    # A patch whose last hunk lacks a trailing newline is rejected outright.
    if body and not body.endswith("\n"):
        body += "\n\\ No newline at end of file\n"
    return body


def plan_diff(plan: Plan) -> str:
    """The whole plan as one patch, in the form ``git apply`` accepts.

    Built from the same :class:`Plan` and the same :func:`apply_edits` as the
    write itself, so the file on disk cannot disagree with the file that gets
    written. A tool whose exported diff differs from what it applies has no
    business being run unattended, and this is the one place that could drift.

    Paths are project-relative with ``a/``/``b/`` prefixes and forward slashes,
    which is what ``git apply -p1`` (the default) expects. The text compared is
    the file's **LF-normalised** content — the same text the parser measured —
    so on a CRLF checkout the patch describes the same edits against LF lines.
    """
    out: list[str] = []
    for abs_path, edits in plan.by_file().items():
        rel = edits[0].file.replace("\\", "/")
        body = diff_for(abs_path, rel, edits, context=3, git=True)
        if body:
            out.append(f"diff --git a/{rel} b/{rel}\n{body}")
    return "".join(out)


@dataclass
class ApplyResult:
    """What a run did, and what it needs to undo itself."""

    files: list[str] = field(default_factory=list)
    edits: int = 0
    failed: list[str] = field(default_factory=list)
    snapshot: dict[str, FileState] = field(default_factory=dict)
    written: list[str] = field(default_factory=list)   # files created, not edited


def apply_plan(plan: Plan, *, backup: bool = True) -> ApplyResult:
    """Write every edit in ``plan``; returns the undo snapshot."""
    result = ApplyResult()
    for abs_path, edits in plan.by_file().items():
        path = Path(abs_path)
        try:
            state = read_text(path)
        except (OSError, UnicodeDecodeError):
            result.failed.append(abs_path)
            continue
        new_text = apply_edits(state[0], edits)
        if new_text == state[0]:
            continue
        if backup:
            make_backup(abs_path)
        result.snapshot[abs_path] = state
        try:
            write_text(path, (new_text, state[1], state[2]))
        except OSError:
            result.failed.append(abs_path)
            del result.snapshot[abs_path]
            continue
        result.files.append(abs_path)
        result.edits += len(edits)
    return result


def undo(result: ApplyResult) -> int:
    """Restore every file a run touched; returns how many were restored."""
    restored = 0
    for abs_path, state in result.snapshot.items():
        try:
            write_text(Path(abs_path), state)
        except OSError:
            continue
        restored += 1
    for created in result.written:
        try:
            Path(created).unlink()
        except OSError:
            pass
    return restored
