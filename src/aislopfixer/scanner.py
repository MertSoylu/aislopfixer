"""Walk a project directory and yield scannable source files."""

from __future__ import annotations

import os
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
# them only produces noise. Matched by filename stem, case-insensitively, at any
# extension (README.md, CLAUDE.md, AGENTS.md, LICENSE, ...).
IGNORE_FILE_STEMS = {
    "readme", "claude", "agents", "gemini", "copilot",
    "contributing", "changelog", "license", "code_of_conduct",
    "security", "codeowners", "authors", "notice", "support",
}

MAX_BYTES = 2_000_000


def _is_meta_file(name: str) -> bool:
    """True for repo-meta/instruction docs we never want to scan."""
    return os.path.splitext(name)[0].lower() in IGNORE_FILE_STEMS


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
                text = Path(ap).read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = os.path.relpath(ap, root)
            yield SourceFile(abs_path=ap, rel_path=rel, text=text)


def collect(root: str) -> list[SourceFile]:
    """Return all eligible source files under ``root`` as a list."""
    return list(iter_files(root))


def count_eligible(root: str) -> int:
    """Cheap pre-count of eligible files (for progress totals)."""
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
            # Mirror iter_files' size gate so the progress total matches the
            # number of files actually yielded (oversized files are skipped).
            try:
                if os.path.getsize(os.path.join(dirpath, name)) > MAX_BYTES:
                    continue
            except OSError:
                continue
            n += 1
    return n
