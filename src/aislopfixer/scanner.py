"""Walk a project directory and yield scannable source files."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .engine.models import SourceFile

IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "out", "vendor",
    ".cache", "coverage", ".svelte-kit", ".nuxt", "__pycache__", ".turbo",
    ".vercel", ".astro", ".output", "bower_components",
}

EXTENSIONS = {
    ".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".mjs", ".cjs",
    ".vue", ".svelte", ".astro", ".md", ".mdx", ".css",
}

# Repo-meta and AI-instruction docs — these are not website content, so scanning
# them only produces noise. Matched by filename stem, case-insensitively, and
# only for *doc-like* extensions. ``security.ts`` / ``support.tsx`` are real
# source modules and must still be scanned.
IGNORE_FILE_STEMS = {
    "readme", "claude", "agents", "gemini", "copilot",
    "contributing", "changelog", "license", "code_of_conduct",
    "security", "codeowners", "authors", "notice", "support",
}
# LICENSE (no ext), README.md, SECURITY.md, … — not security.js / support.tsx
_META_DOC_EXTS = {"", ".md", ".mdx", ".txt", ".rst", ".markdown"}

MAX_BYTES = 2_000_000

# Minified/bundled artifacts are generated output, not authored source: scanning
# them floods per-match rules (a vendor bundle carries hundreds of `catch(t){}`)
# with findings nobody can act on. Same class as dist/ and build/, which
# IGNORE_DIRS already skips — these are the stragglers living outside them.
_MIN_NAME = re.compile(r"[.-]min\.(?:js|mjs|cjs|css)$", re.IGNORECASE)
_MINIFIED_EXTS = {".js", ".mjs", ".cjs", ".css"}
_MINIFIED_SAMPLE = 16_384   # chars of the file head the heuristic looks at
_MINIFIED_MIN_LEN = 2_048   # below this, line-length ratios mean nothing
_MINIFIED_AVG_LINE = 300    # authored code averages ~40-60 chars per line


def _looks_minified(name: str, sample: str) -> bool:
    """True when ``name``/``sample`` (file head) reads as minified build output.

    Judged on the *average* line length of the head, so one long inlined
    data-URI among normal authored lines does not trip it.
    """
    if _MIN_NAME.search(name):
        return True
    if os.path.splitext(name)[1].lower() not in _MINIFIED_EXTS:
        return False
    sample = sample[:_MINIFIED_SAMPLE]
    if len(sample) < _MINIFIED_MIN_LEN:
        return False
    lines = sample.splitlines()
    return len(sample) / max(1, len(lines)) > _MINIFIED_AVG_LINE


def _is_meta_file(name: str) -> bool:
    """True for repo-meta/instruction docs we never want to scan."""
    stem, ext = os.path.splitext(name)
    return (
        stem.lower() in IGNORE_FILE_STEMS
        and ext.lower() in _META_DOC_EXTS
    )


def iter_files(root: str):
    """Yield SourceFile for each eligible text file under ``root``."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]
        for name in sorted(filenames):
            if _is_meta_file(name):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in EXTENSIONS:
                continue
            ap = os.path.join(dirpath, name)
            try:
                if os.path.getsize(ap) > MAX_BYTES:
                    continue
                # utf-8-sig: a leading BOM would otherwise survive as ﻿ and
                # stop every ^-anchored rule from matching the first line.
                text = Path(ap).read_text(encoding="utf-8-sig")
            except (UnicodeDecodeError, OSError):
                continue
            if _looks_minified(name, text):
                continue
            rel = os.path.relpath(ap, root)
            yield SourceFile(abs_path=ap, rel_path=rel, text=text)


def collect(root: str) -> list[SourceFile]:
    """Return all eligible source files under ``root`` as a list."""
    return list(iter_files(root))


def count_eligible(root: str, config=None) -> int:
    """Cheap pre-count of eligible files (for progress totals).

    ``config`` (a :class:`aislopfixer.config.Config`) applies the project's
    ``ignore`` globs, mirroring the pipeline — otherwise the progress total
    counts files the scan will silently skip and the bar never reaches 100%.
    """
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            if _is_meta_file(name):
                continue
            if os.path.splitext(name)[1].lower() not in EXTENSIONS:
                continue
            ap = os.path.join(dirpath, name)
            # Mirror iter_files' size and minified gates so the progress total
            # matches the number of files actually yielded. Only the file head
            # is read here — this stays a cheap pre-count.
            try:
                if os.path.getsize(ap) > MAX_BYTES:
                    continue
                with open(ap, "rb") as fh:
                    head = fh.read(_MINIFIED_SAMPLE)
                if _looks_minified(name, head.decode("utf-8", errors="replace")):
                    continue
            except OSError:
                continue
            if config is not None and config.path_ignored(os.path.relpath(ap, root)):
                continue
            n += 1
    return n
