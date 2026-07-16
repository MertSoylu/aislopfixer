"""The one scan pipeline shared by the TUI and the headless CLI.

Both front-ends must see identical findings for the same project: walk the
tree, run per-file rules, drop what the project memory already resolved,
de-prioritize rules the user keeps dismissing, then run cross-file rules.
Keeping the sequence here means it cannot drift between the two.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from .config import Config
from .engine.context import code_masks, prose_regions
from .engine.models import Finding, SourceFile
from .engine.runner import run_cross_rules, run_file_rules
from .engine.scoring import reset_and_corroborate
from .scanner import iter_files
from .store import NOISY_DEMOTION, Store


def demote_noisy(findings: list[Finding], noisy: set[str]) -> None:
    """Scale down confidence of findings whose rule the user keeps dismissing."""
    if not noisy:
        return
    for f in findings:
        if f.rule_id in noisy:
            f.confidence *= NOISY_DEMOTION


def scan_project(
    path: str,
    store: Store | None = None,
    on_file: Callable[[SourceFile, list[Finding]], None] | None = None,
    on_cross_start: Callable[[], None] | None = None,
    config: Config | None = None,
) -> list[Finding]:
    """Scan ``path`` and return the filtered, demoted findings.

    ``on_file`` fires after each file (progress display); ``on_cross_start``
    fires once between the per-file pass and the cross-file pass. ``config``
    defaults to the project's ``.aislopfixer.toml`` (all-defaults if absent).

    After file + cross rules merge, confidences are recomputed and corroborated
    per file so cross-file tells (imports, duplicates) reinforce same-file
    authorship signals. Noisy-rule demotion runs last so it is not wiped.
    """
    cfg = config if config is not None else Config.load(path)
    noisy = store.noisy_rules() if store is not None else set()
    files: list[SourceFile] = []
    findings: list[Finding] = []

    def keep(fs: list[Finding]) -> list[Finding]:
        return [f for f in fs if not cfg.rule_disabled(f.rule_id)]

    try:
        for sf in iter_files(path):
            if cfg.path_ignored(sf.rel_path):
                continue
            file_findings = keep(run_file_rules(sf))
            if store is not None:
                file_findings = store.filter(file_findings)
            files.append(sf)
            findings.extend(file_findings)
            if on_file is not None:
                on_file(sf, file_findings)
        if on_cross_start is not None:
            on_cross_start()
        cross = keep(run_cross_rules(files))
        if store is not None:
            cross = store.filter(cross)
        findings.extend(cross)
    finally:
        # The lexer/prose caches key on full file texts — clearing here frees
        # up to 64 retained file bodies once the scan no longer needs them.
        code_masks.cache_clear()
        prose_regions.cache_clear()
    reset_and_corroborate(findings)
    demote_noisy(findings, noisy)
    return findings


def rescan_paths(
    root: str,
    rel_paths: set[str],
    store: Store | None = None,
    config: Config | None = None,
) -> list[Finding]:
    """Re-run the *file* rules on a few just-edited files.

    Used after applying automatic fixes: a fix can surface a finding that was
    masked by the slop it removed (strip ``## 🎯 Conclusion``'s emoji and the
    bare boilerplate heading appears). Same filtering/scoring as a full scan;
    cross-file rules are skipped — edits do not add imports or duplicates.
    """
    cfg = config if config is not None else Config.load(root)
    noisy = store.noisy_rules() if store is not None else set()
    findings: list[Finding] = []
    try:
        for rel in rel_paths:
            if cfg.path_ignored(rel):
                continue
            ap = os.path.join(root, rel)
            try:
                text = Path(ap).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue
            sf = SourceFile(abs_path=ap, rel_path=rel, text=text)
            fs = [f for f in run_file_rules(sf) if not cfg.rule_disabled(f.rule_id)]
            if store is not None:
                fs = store.filter(fs)
            findings.extend(fs)
    finally:
        code_masks.cache_clear()
        prose_regions.cache_clear()
    reset_and_corroborate(findings)
    demote_noisy(findings, noisy)
    return findings
