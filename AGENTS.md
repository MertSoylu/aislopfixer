# aislopfixer

Terminal TUI (Textual) that finds/fixes AI slop in local web projects. Fully offline, rule-based.

## Run

```bash
pip install -e .            # basic
pip install -e ".[dev]"     # +pytest/pytest-asyncio
aislopfixer ./sample        # CLI entry: aislopfixer.cli:main
python -m aislopfixer ./sample
aislopfixer . --check       # headless CI mode (--json/--sarif/--prompt/--fix/--fail-on/--min-confidence)
```

## Test

```bash
pytest                      # asyncio_mode=auto, testpaths=tests, sys.path includes src/
pytest test_rules.py -k "test_ai_leak"  # single test
```

## Architecture

```
src/aislopfixer/
├── cli.py             # argparse entrypoint (TUI default; --check/--json/--sarif/--prompt → headless)
├── headless.py        # CI mode: text/JSON/SARIF/fix-brief output, exit codes, batch auto-fix
├── pipeline.py        # scan_project() — the one pipeline TUI + headless share
├── prompter.py        # findings → fix brief for an AI coding assistant (--prompt, TUI `x`)
├── config.py          # .aislopfixer.toml: disable prefixes, ignore globs, thresholds
├── __main__.py        # python -m support
├── app.py             # Textual App, screen orchestration (splash→path→scan→results→summary)
├── scanner.py         # walks dir, filters by ext/ignore/meta, yields SourceFile
├── fixer.py           # apply AUTO/PROMPT/MANUAL fixes, backups (.aislopfixer.bak), annotate
├── allowlist.py       # .aislopfixer/allowlist.json — user-confirmed false positives survive scans
├── store.py           # .aislopfixer/{allowlist,ledger}.json + report.md — per-project memory
├── theme.py           # colors, icons, shimmer gradient
├── styles.tcss        # Textual CSS
├── engine/
│   ├── models.py      # SourceFile, Finding, enums (Category, Fixability, Severity, Status)
│   ├── runner.py      # orchestrates rules, dedupes by (file,start,end), strips self-annotations
│   ├── registry.py    # @file_rule / @cross_rule decorators — rules self-register at import
│   ├── pattern_rule.py# base class for regex rules (Pattern + PatternRule)
│   ├── context.py     # file_kind(), prose_regions() — only flag buzzwords in human-visible text
│   └── rules/         # ai_leaks, placeholders, buzzwords, copy_slop, duplicates,
│                      #   accessibility, codegen, design_slop, imports, landing_tells,
│                      #   markdown_tells, prose_tells, merge_conflicts, secrets,
│                      #   security  (15 modules;
│                      #   SECURITY = XSS/SQLi/secrets;
│                      #   design_slop = purple→pink gradient hero, fake social-proof
│                      #   stats, emoji-decorated UI copy, landing-kit composite;
│                      #   landing_tells = fake metric strips, pricing triad, section
│                      #   recipe, fake logo clouds, glow blobs (Category.DESIGN);
│                      #   copy_slop = ≥2-gated template microcopy + testimonial
│                      #   phrasing (Category.BUZZWORD);
│                      #   imports = hallucinated deps + phantom exports + unused;
│                      #   duplicates = prose AND near-identical code blocks; see CLAUDE.md)
├── screens/           # SplashScreen, PathScreen, ScanScreen, ResultsScreen, SummaryScreen, modal
└── widgets/           # animations, counters, logo
```

## Key conventions

- Rules self-register via `@file_rule`/`@cross_rule` in `registry.py` at import time. `runner.py` imports `rules` package to trigger registration.
- `PlaceholderRule` subclasses `PatternRule` with a list of `Pattern` dataclasses each defining regex, fixability, severity, guard function.
- `AILeakRule` splits into STRONG (auto-delete line) and SOFT (manual review only).
- `BuzzwordRule` overrides `scan()` to check `prose_regions()` first — buzzwords in code identifiers are ignored.
- Dedup: `runner._dedupe()` collapses findings with same `(file, start, end)` — keeps the strongest (confidence, then severity); zero-length spans never deduped.
- Self-annotation filter: lines containing `aislopfixer:` are never re-flagged.
- Scanner skips: hidden dirs (`.git`), `node_modules`, `dist`, `build`, `.next`, `vendor`, `__pycache__`, `.turbo` etc. Also skips repo-meta files by stem: `README`, `CLAUDE`, `AGENTS`, `LICENSE`, `CONTRIBUTING`, `CHANGELOG`, etc.
- Max scanned file size: 2MB (`MAX_BYTES`). Extensions: `.html .htm .jsx .tsx .js .ts .mjs .cjs .vue .svelte .astro .md .mdx .css`.
- Minified build artifacts skipped (`scanner._looks_minified`): `*.min.js`-style names, or js/css whose first 16 KB averages > 300 chars per line. Mirrored in `count_eligible` so progress totals match.
- Allowlist persisted to `<project>/.aislopfixer/allowlist.json` (legacy `.aislopfixerignore.json` is migrated on load). Keyed by `(rule_id, matched_text)` not line number — survives edits. Cross-file suppression.
- Fix types: `AUTO` (delete/replace without input), `PROMPT` (user supplies value via `replace_template`), `MANUAL` (flag only).
- `fixer.py` relocates findings after prior edits (`_locate()` finds current offset by matched_text).
- `fixer.py` edits LF-normalized text but writes back the file's original line endings (`_read_text`/`_write_text`) — never a bare `write_text`, which would CRLF-rewrite whole files on Windows. `fixer.reanchor()` refreshes line/col/snippet of still-open findings after edits (called from headless `--fix` and every TUI fix/annotate path).
- Backup file: `<file>.aislopfixer.bak`, created once per file (idempotent).
- `diff_preview()` outputs unified diff before applying.

## Flow

1. `SplashScreen` → always `PathScreen` (pre-filled when a PATH arg was given — confirm with Enter).
2. `PathScreen` → user enters/confirms path.
3. `ScanScreen` → runs `pipeline.scan_project()` in a worker thread, transitions to results. A failed scan stays here with `r` retry / `n` new folder / `q` quit — it never falls through to an empty results screen.
4. `ResultsScreen` → tree (left) + detail panel (right). Keybindings: `f` fix, `d` diff preview (`DiffModal`), `s` skip, `a` annotate, `i` not slop (`s`/`i` on a category/file row act on the whole branch), `u` undo last fix/annotate, `p` fix all auto (fixpoint: re-scans touched files ≤3 passes), `x` export (AI fix brief / JSON / SARIF via `ExportModal`), `c` confidence floor, `q` summary/modal.
5. `SummaryScreen` → per-category counts.

## Release

Version lives in 3 places: `package.json`, `pyproject.toml`, `src/aislopfixer/__init__.py`. Keep in sync. Update version in README.md badges too.

## Dependencies

- Python ≥3.11, setuptools build backend, `textual>=0.80`.
- Dev: `pytest>=8`, `pytest-asyncio>=0.23`.
