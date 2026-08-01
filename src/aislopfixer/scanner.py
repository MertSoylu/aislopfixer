"""Walk a project directory and yield scannable source files.

Extensions are the ones a *design* can live in. Markdown is deliberately
absent: prose files carry no layout, no palette and no rhythm, so scanning them
would add findings the design report has no axis for.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass
class SourceFile:
    """A text source file handed to the parser."""

    abs_path: str
    rel_path: str
    text: str


IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", "out", "vendor",
    ".cache", "coverage", ".svelte-kit", ".nuxt", "__pycache__", ".turbo",
    ".vercel", ".astro", ".output", "bower_components",
}

# Dot-directories that hold *authored source*, not build output. The blanket
# "skip anything starting with a dot" rule is right for `.next` and `.cache` and
# wrong for exactly one class of project: a VitePress/VuePress site keeps its
# entire theme — every component, every stylesheet, the whole design — inside
# `.vitepress/theme`. Skipping it read `hono-website` as four markup files with
# 42 elements and then blamed the gap on its `.md` pages, which carry no design
# at all: the theme *is* the design of every page on that site.
SOURCE_DOT_DIRS = {".vitepress", ".vuepress", ".storybook", ".ladle", ".config"}
# …but a build cache lives *inside* those. `.vitepress/cache` and
# `.vitepress/dist` are generated, and `dist` is already refused above.
NESTED_IGNORE_DIRS = {"cache", "temp", ".temp"}

EXTENSIONS = {
    ".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".mjs", ".cjs",
    ".vue", ".svelte", ".astro", ".mdx",
    ".css", ".scss", ".sass", ".less", ".pcss", ".postcss",
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
_MINIFIED_EXTS = {".js", ".mjs", ".cjs", ".css", ".scss", ".less"}
_MINIFIED_SAMPLE = 16_384   # chars of the file head the heuristic looks at
_MINIFIED_MIN_LEN = 2_048   # below this, line-length ratios mean nothing
_MINIFIED_AVG_LINE = 300    # authored code averages ~40-60 chars per line


# A compiled Tailwind stylesheet is not minified — the dev build is pretty-
# printed — so the length heuristic above walks straight past it and the scan
# then counts *the framework's* whole utility set as the project's vocabulary.
# `landwind/output.css` is 49 KB of generated rules, and reading it gave that
# repository 154 distinct colour values and 77 "tokens" nobody wrote.
#
# Both markers are things no one authors by hand: Tailwind's own banner, and the
# runtime custom properties its utilities compile to. Neither is a guess.
_GENERATED_CSS = re.compile(
    r"--tw-ring-offset-shadow|--tw-border-spacing-x|tailwindcss v\d")
_GENERATED_EXTS = {".css", ".scss", ".less", ".pcss", ".postcss"}
_GENERATED_SAMPLE = 65_536   # the banner is at the top; preflight right after


def _looks_generated(name: str, sample: str) -> bool:
    """True when a stylesheet is a framework's build output, not source."""
    if os.path.splitext(name)[1].lower() not in _GENERATED_EXTS:
        return False
    return _GENERATED_CSS.search(sample[:_GENERATED_SAMPLE]) is not None


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


# Markup this tool cannot read. Each one is a real page in a real repository —
# a Jekyll layout, an Eleventy template — and skipping it in silence is how a
# five-file scan of a fifty-page site reads as a full one. They are *counted*
# here and reported as coverage; see design.models.Coverage.
TEMPLATE_EXTENSIONS = {
    ".erb", ".njk", ".hbs", ".handlebars",
    ".ejs", ".liquid", ".pug", ".jade", ".twig", ".haml", ".slim", ".php",
}

# Prose pages, counted apart from the templates above and deliberately *not*
# scanned. A `.md` page in a docs site is a page — but its design belongs to the
# theme that renders it, and that theme is source this tool already reads. The
# markup inside one is nearly always a fenced code sample, so scanning it would
# measure a documented snippet as the site's own vocabulary.
#
# They are a separate census because they must not drag coverage confidence
# down the way a `.erb` page does: an unread Liquid template is a page whose
# design is somewhere the tool cannot look, while an unread `.md` page is a page
# with no design of its own. `.mdx` is neither — its body is JSX, and it is
# read like any other markup file.
PROSE_EXTENSIONS = {".md", ".markdown"}
# Deliberately *not* a directory rule. A Jekyll `_layouts/default.html` is HTML
# with Liquid interpolations in it, and the markup scanner reads it — skipping
# the directory took `tholman` from 65 elements to 1, which is a scan that has
# stopped seeing the site in order to be tidy about where the site lives.


@dataclass(frozen=True)
class Walk:
    """One directory walk: what will be read, and what will not be."""

    paths: tuple[str, ...]
    # extension → how many files the scan cannot read at all
    templates: dict[str, int] = field(default_factory=dict)
    # extension → how many prose pages were counted and deliberately not read
    prose: dict[str, int] = field(default_factory=dict)


def _keep_dir(name: str, inside_source_dot: bool) -> bool:
    """True when the walk should descend into ``name``."""
    if name in IGNORE_DIRS:
        return False
    if inside_source_dot:
        return name not in NESTED_IGNORE_DIRS
    return name in SOURCE_DOT_DIRS or not name.startswith(".")


def walk(root: str) -> Walk:
    """Every file worth reading, plus a census of the ones in a foreign language."""
    out: list[str] = []
    templates: dict[str, int] = {}
    prose: dict[str, int] = {}
    root_parts = len(os.path.abspath(root).split(os.sep))
    for dirpath, dirnames, filenames in os.walk(root):
        # Inside `.vitepress/` the walk stops applying the dot rule (the theme's
        # own directories are ordinary names) but starts refusing the build
        # cache that framework writes next to the theme.
        parts = os.path.abspath(dirpath).split(os.sep)[root_parts - 1:]
        inside = any(p in SOURCE_DOT_DIRS for p in parts)
        dirnames[:] = [d for d in dirnames if _keep_dir(d, inside)]
        for name in sorted(filenames):
            if _is_meta_file(name):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in TEMPLATE_EXTENSIONS:
                templates[ext] = templates.get(ext, 0) + 1
                continue
            if ext in PROSE_EXTENSIONS:
                prose[ext] = prose.get(ext, 0) + 1
                continue
            if ext not in EXTENSIONS:
                continue
            out.append(os.path.join(dirpath, name))
    return Walk(paths=tuple(out), templates=templates, prose=prose)


def eligible_paths(root: str) -> list[str]:
    """Absolute paths of every file worth reading, in a stable order."""
    return list(walk(root).paths)


def _read(ap: str) -> tuple[SourceFile | None, str]:
    """``(file, "")`` or ``(None, reason)`` — the reason reaches the report."""
    try:
        if os.path.getsize(ap) > MAX_BYTES:
            return None, "too_large"
        # utf-8-sig: a leading BOM would otherwise survive as ﻿ and stop every
        # ^-anchored rule from matching the first line.
        text = Path(ap).read_text(encoding="utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return None, "unreadable"
    name = os.path.basename(ap)
    if _looks_minified(name, text):
        return None, "minified"
    if _looks_generated(name, text):
        return None, "generated"
    return SourceFile(abs_path=ap, rel_path="", text=text), ""


# Reading is the single largest cost of a scan on a real repository — on
# Windows, with a virus scanner in the path, opening a few thousand small files
# costs more than every measurement put together. It is pure I/O, so threads
# actually help: the GIL is released for the duration of each read.
_READ_WORKERS = min(16, (os.cpu_count() or 4) * 4)
_PARALLEL_AT = 24        # below this, the pool costs more than it saves


def iter_files(root: str, skipped: dict[str, int] | None = None):
    """Yield SourceFile for each eligible text file under ``root``.

    Order matches :func:`eligible_paths` regardless of which read finishes
    first: the report lists files in a stable order, and a scan whose output
    depends on disk timing cannot be diffed between runs.

    ``skipped`` — when given — is filled with ``reason → count`` for the files
    that were walked but not read. A file dropped without a number next to it
    is a hole the reader has no way to see.
    """
    found = walk(root)
    paths = list(found.paths)
    if skipped is not None:
        for ext, n in found.templates.items():
            skipped[f"template:{ext}"] = skipped.get(f"template:{ext}", 0) + n
        for ext, n in found.prose.items():
            skipped[f"prose:{ext}"] = skipped.get(f"prose:{ext}", 0) + n
    if len(paths) < _PARALLEL_AT:
        results = (_read(ap) for ap in paths)
    else:
        with ThreadPoolExecutor(max_workers=_READ_WORKERS) as pool:
            results = list(pool.map(_read, paths))
    for ap, (sf, why) in zip(paths, results):
        if sf is None:
            if skipped is not None:
                skipped[why] = skipped.get(why, 0) + 1
            continue
        yield replace(sf, rel_path=os.path.relpath(ap, root))


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
    for ap in walk(root).paths:
        name = os.path.basename(ap)
        # Mirror iter_files' size, minified and generated gates so the progress
        # total matches the number of files actually yielded. Only the file head
        # is read here — this stays a cheap pre-count.
        try:
            if os.path.getsize(ap) > MAX_BYTES:
                continue
            with open(ap, "rb") as fh:
                head = fh.read(_GENERATED_SAMPLE)
            sample = head.decode("utf-8", errors="replace")
            if _looks_minified(name, sample) or _looks_generated(name, sample):
                continue
        except OSError:
            continue
        if config is not None and config.path_ignored(os.path.relpath(ap, root)):
            continue
        n += 1
    return n
