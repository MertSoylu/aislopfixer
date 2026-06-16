# aislopfixer

Terminal TUI (Textual) that finds/fixes AI slop in local web projects. Fully offline, rule-based.

## Run

```bash
pip install -e .            # basic
pip install -e ".[dev]"     # +pytest/pytest-asyncio
aislopfixer ./sample        # CLI entry: aislopfixer.cli:main
python -m aislopfixer ./sample
```

## Test

```bash
pytest                      # asyncio_mode=auto, testpaths=tests, sys.path includes src/
pytest test_rules.py -k "test_ai_leak"  # single test
```

## Architecture

```
src/aislopfixer/
├── cli.py             # argparse entrypoint
├── __main__.py        # python -m support
├── app.py             # Textual App, screen orchestration (splash→path→scan→results→summary)
├── scanner.py         # walks dir, filters by ext/ignore/meta, yields SourceFile
├── fixer.py           # apply AUTO/PROMPT/MANUAL fixes, backups (.aislopfixer.bak), annotate
├── allowlist.py       # .aislopfixerignore.json — user-confirmed false positives survive scans
├── theme.py           # colors, icons, shimmer gradient
├── styles.tcss        # Textual CSS
├── engine/
│   ├── models.py      # SourceFile, Finding, enums (Category, Fixability, Severity, Status)
│   ├── runner.py      # orchestrates rules, dedupes by (file,start,end), strips self-annotations
│   ├── registry.py    # @file_rule / @cross_rule decorators — rules self-register at import
│   ├── pattern_rule.py# base class for regex rules (Pattern + PatternRule)
│   ├── context.py     # file_kind(), prose_regions() — only flag buzzwords in human-visible text
│   └── rules/         # ai_leaks, placeholders, buzzwords, duplicates, accessibility
├── screens/           # SplashScreen, PathScreen, ScanScreen, ResultsScreen, SummaryScreen, modal
└── widgets/           # animations, counters, logo
```

## Key conventions

- Rules self-register via `@file_rule`/`@cross_rule` in `registry.py` at import time. `runner.py` imports `rules` package to trigger registration.
- `PlaceholderRule` subclasses `PatternRule` with a list of `Pattern` dataclasses each defining regex, fixability, severity, guard function.
- `AILeakRule` splits into STRONG (auto-delete line) and SOFT (manual review only).
- `BuzzwordRule` overrides `scan()` to check `prose_regions()` first — buzzwords in code identifiers are ignored.
- Dedup: `runner._dedupe()` collapses findings with same `(file, start, end)` — keeps first.
- Self-annotation filter: lines containing `aislopfixer:` are never re-flagged.
- Scanner skips: hidden dirs (`.git`), `node_modules`, `dist`, `build`, `.next`, `vendor`, `__pycache__`, `.turbo` etc. Also skips repo-meta files by stem: `README`, `CLAUDE`, `AGENTS`, `LICENSE`, `CONTRIBUTING`, `CHANGELOG`, etc.
- Max scanned file size: 2MB (`MAX_BYTES`). Extensions: `.html .htm .jsx .tsx .js .ts .mjs .cjs .vue .svelte .astro .md .mdx .css`.
- Allowlist persisted to `<project>/.aislopfixerignore.json`. Keyed by `(rule_id, matched_text)` not line number — survives edits. Cross-file suppression.
- Fix types: `AUTO` (delete/replace without input), `PROMPT` (user supplies value via `replace_template`), `MANUAL` (flag only).
- `fixer.py` relocates findings after prior edits (`_locate()` finds current offset by matched_text).
- Backup file: `<file>.aislopfixer.bak`, created once per file (idempotent).
- `diff_preview()` outputs unified diff before applying.

## Flow

1. `SplashScreen` → if `initial_path` is valid dir, skip to scan; else `PathScreen`.
2. `PathScreen` → user enters/confirms path.
3. `ScanScreen` → runs `scan_all()` (file rules + cross rules), transitions to results.
4. `ResultsScreen` → tree (left) + detail panel (right). Keybindings: `f` fix, `s` skip, `a` annotate, `p` fix all auto, `q` summary/modal.
5. `SummaryScreen` → per-category counts.

## Release

Version lives in 3 places: `package.json`, `pyproject.toml`, `src/aislopfixer/__init__.py`. Keep in sync. Update version in README.md badges too.

## Dependencies

- Python ≥3.11, setuptools build backend, `textual>=0.80`.
- Dev: `pytest>=8`, `pytest-asyncio>=0.23`.
