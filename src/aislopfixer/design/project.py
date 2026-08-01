"""Load and measure a project — the one pipeline the whole app shares.

Parsing is separated from measurement so the transformer can re-parse a subset
of files after an edit without re-running the report, and so the TUI can show
per-file progress while the expensive cross-file metrics wait for the end.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import Config
from ..scanner import SourceFile, iter_files
from . import scope
from .analyze import analyze
from .models import DesignReport, Document
from .parse import (load_theme, parse_document, resolve_components,
                    resolve_stylesheets)
from .parse.lexer import code_masks, prose_regions
from .parse.styles import resolve_styles


def load_documents(
    root: str,
    config: Config | None = None,
    on_file: Callable[[Document], None] | None = None,
    skipped: dict[str, int] | None = None,
) -> list[Document]:
    """Parse every eligible file under ``root``.

    ``skipped`` — when given — comes back filled with ``reason → count`` for the
    files that were walked and not read, which is what
    :class:`~.models.Coverage` turns into a sentence.
    """
    cfg = config if config is not None else Config.load(root)
    docs: list[Document] = []
    try:
        # The theme config decides whether a shipped scale key counts as a
        # decision, so it has to be known before the first class is decoded.
        # Read from the same in-memory pass rather than a second walk.
        sources = [sf for sf in iter_files(root, skipped)
                   if not cfg.path_ignored(sf.rel_path)]
        theme = load_theme(sources)
        for sf in sources:
            doc = parse_document(sf.rel_path, sf.abs_path, sf.text, theme)
            docs.append(doc)
            if on_file is not None:
                on_file(doc)
    finally:
        # The lexer caches key on whole file bodies; releasing them here keeps a
        # large project from holding every source in memory after the walk.
        code_masks.cache_clear()
        prose_regions.cache_clear()
    # Cross-file steps: a component's markup — and a CSS Module's stylesheet —
    # usually live in a different file from the pages that use them, so these
    # can only run once the walk is done. Styles first: `styled.div` definitions
    # become component roots that the component resolver then wires to usages.
    resolve_styles(docs)
    # Stylesheets before components: a component's root has to carry what its
    # class says before a usage inherits from it.
    resolve_stylesheets(docs)
    resolve_components(docs)
    return docs


def apply_config(report: DesignReport, config: Config) -> DesignReport:
    """Drop observations the project has turned off in ``.aislopfixer.toml``.

    Only the *observations* are filtered, never the scores. A disabled
    observation is one the user does not want listed; silently removing its
    contribution to the measurement would let a project score itself clean by
    editing a config file.
    """
    report.observations = [
        o for o in report.observations if not config.observation_disabled(o.id)
    ]
    return report


def scan_project(
    root: str,
    config: Config | None = None,
    on_file: Callable[[Document], None] | None = None,
) -> tuple[DesignReport, list[Document]]:
    """Parse and measure ``root``; returns the report and the parsed documents.

    With ``config.pages`` set, the whole tree is still parsed — components have
    to be resolvable wherever the repository keeps them — and only the documents
    the scope is *about* are measured. See :mod:`.scope`; the returned document
    list is the measured one, so the transform rewrites the same site the score
    describes.
    """
    cfg = config if config is not None else Config.load(root)
    skipped: dict[str, int] = {}
    docs = load_documents(root, cfg, on_file, skipped)
    return measure(root, docs, cfg, skipped)


def measure(root: str, docs: list[Document], config: Config,
            skipped: dict[str, int] | None = None
            ) -> tuple[DesignReport, list[Document]]:
    """Scope, measure and filter — the half of a scan that follows the parse.

    Split out because the TUI parses with its own progress callback and would
    otherwise have to repeat this, which is how a scan run from the interface
    starts differing from a scan run from a test.
    """
    measured = scope.select(docs, config.pages)
    report = apply_config(analyze(root, measured, skipped), config)
    scope_note = scope.note(config.pages, docs, measured)
    if scope_note:
        report.notes.insert(0, scope_note)
    return report, measured


def source_files(root: str, config: Config | None = None) -> list[SourceFile]:
    """Raw eligible files — used by the transformer, which edits text."""
    cfg = config if config is not None else Config.load(root)
    return [sf for sf in iter_files(root) if not cfg.path_ignored(sf.rel_path)]
