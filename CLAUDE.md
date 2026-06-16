# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A terminal TUI (Python + [Textual](https://textual.textualize.io/)) that finds and fixes AI-generated "slop" in local web projects — fully offline, rule-based, no API keys. The real application lives in **`src/aislopfixer/` (Python)**; `bin/cli.js` is only an npm launcher.

The npm package (`@mertsoylu/aislopfixer`) exists so users can `npm i -g` without managing Python: on first run `bin/cli.js` locates a host Python ≥ 3.11, builds a private venv under `~/.aislopfixer/venv-<version>/`, `pip install`s this package into it, then `exec`s `python -m aislopfixer`. When developing, ignore the launcher and work against the Python package directly.

## Commands

```bash
pip install -e ".[dev]"                       # dev install (textual + pytest + pytest-asyncio)
aislopfixer ./sample                          # run the TUI against a folder
python -m aislopfixer ./sample                # module form (same thing)
pytest                                        # full suite (117 tests)
pytest tests/test_rules.py -k test_ai_leak    # one file / one test
node scripts/clean.mjs                         # strip __pycache__/*.pyc (runs as npm prepack)
```

- pytest config lives in `pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]`. So **tests run from the repo root without installing** the package; `aislopfixer`/`python -m aislopfixer` do require `pip install -e .` first.
- TUI/screen tests use Textual's async pilot driver (hence `asyncio_mode=auto`).
- Tests that exercise the rule set call `registry.reset()` to clear the global rule lists before re-importing — keep that in mind when adding tests that touch registration.

## Architecture

Pipeline: **scan files → run rules → score → filter against per-project memory → present in TUI → apply fixes → persist outcomes + report.**

```
src/aislopfixer/
├── cli.py / __main__.py   # argparse entry → AISlopFixerApp(initial_path=...).run()
├── app.py                 # Textual App; owns the Store; orchestrates screens
├── scanner.py             # walk dir → SourceFile list (ext/ignore/size filtering)
├── fixer.py               # apply AUTO/PROMPT/MANUAL fixes, backups, diff preview, annotate
├── allowlist.py           # .aislopfixer/allowlist.json — user-confirmed false positives
├── store.py               # .aislopfixer/{allowlist,ledger}.json + report.md (project memory)
├── theme.py / styles.tcss # colors/icons + Textual CSS
├── engine/
│   ├── models.py          # SourceFile, Finding, enums: Category/Severity/Fixability/Status
│   ├── registry.py        # @file_rule / @cross_rule decorators; FILE_RULES / CROSS_RULES
│   ├── runner.py          # runs rules, dedupes, collapses repeats, backfills confidence
│   ├── scoring.py         # per-finding confidence + file/project slop scores
│   ├── context.py         # file_kind(), prose_regions(), on_annotation_line()
│   ├── pattern_rule.py    # Pattern dataclass + PatternRule base for regex rules
│   └── rules/             # accessibility, ai_leaks, buzzwords, codegen, duplicates,
│                          #   markdown_tells, placeholders, prose_tells
├── screens/               # splash → path → scan → results → summary (+ base, modal)
└── widgets/               # animations, counters, logo, stats, guard (too-small overlay)
```

### Rules self-register at import time
A rule is a class decorated with `@file_rule` (runs once per file, has `scan(sf)`) or `@cross_rule` (runs once over all files, has `scan_all(files)` — e.g. duplicate detection). The decorator appends an instance to `FILE_RULES`/`CROSS_RULES`. **`engine/rules/__init__.py` imports every rule module**, and `runner.py` imports the `rules` package — that import chain is what populates the registry. A rule module that isn't listed in `rules/__init__.py` is invisible.

Most rules subclass `PatternRule` with a list of `Pattern` dataclasses (regex + fixability + severity + optional guard fn). Exceptions override `scan()` directly — e.g. `BuzzwordRule` consults `prose_regions()` so buzzwords only flag in human-visible text, never in code identifiers; `AILeakRule` splits STRONG (auto-delete) vs SOFT (manual review).

### Confidence is centralized, not per-rule
Rules generally do **not** set `Finding.confidence`. `runner._backfill_confidence()` calls `scoring.score_finding()` for any finding left at 0. `scoring.py` resolves confidence via a longest-prefix `RULE_OVERRIDE` table (e.g. `ai_leak.strong → 0.97`), falling back to `CAT_PRIOR[category] × SEV_W[severity]`. `file_score` is a noisy-OR; `project_score` is a self-weighted mean (Σs²/Σs) so one sloppy file dominates. A rule *may* pin its own confidence and the runner leaves it alone. **When you add a rule whose strength isn't captured by category+severity, add a prefix to `RULE_OVERRIDE`.**

### Runner post-processing (order matters)
`run_file_rules` does: collect → drop findings on our own annotation lines (`on_annotation_line`) → `_dedupe` (by `(file,start,end)`, keep first; zero-length spans never deduped) → `_collapse_repeats` (one finding per distinct value for `placeholder.{company,name,address}`) → backfill confidence.

### Per-project memory (`<root>/.aislopfixer/`)
`Store` is the key piece **not** in the README/AGENTS architecture diagrams. It owns three files under a hidden `.aislopfixer/` folder (skipped by the scanner's own walk):
- `allowlist.json` — items the user marked "not slop".
- `ledger.json` — every resolved/skipped finding with status + timestamp.
- `report.md` — human-readable snapshot written after each scan.

`Store.filter()` (called in `screens/scan.py`) drops anything allowlisted **and** anything the ledger records as `FIXED`/`ANNOTATED`/`IGNORED` — keyed by `(rule_id, matched_text)`, so suppression **survives line edits and works cross-file**. `SKIPPED` findings deliberately re-surface ("skip" = later, not never). `screens/results.py` calls `store.record()` on each user action; `app.py` calls `store.write_report()`.

### Fixing model
Three fixabilities on `Finding`: `AUTO` (delete/replace via `replacement`), `PROMPT` (user value plugged into `replace_template`), `MANUAL` (flag only). `fixer.py` backs up each file to `<file>.aislopfixer.bak` once (idempotent), computes a unified diff before writing, and **relocates findings by `matched_text` after prior edits** so char offsets stay valid across a fix session.

### Scanner filtering
Extensions: `.html .htm .jsx .tsx .js .ts .mjs .cjs .vue .svelte .astro .md .mdx .css`. Skips hidden dirs, `node_modules`, `dist`, `build`, `.next`, `vendor`, `__pycache__`, `.turbo`, etc.; skips repo-meta files by stem (`README`, `CLAUDE`, `AGENTS`, `LICENSE`, `CONTRIBUTING`, `CHANGELOG`, …); skips files > 2 MB (`MAX_BYTES`). Lines containing `aislopfixer:` (our own annotations) are never re-flagged.

## Adding a detection rule (the common task)

1. Add (or extend) a module in `src/aislopfixer/engine/rules/`.
2. Decorate the rule class with `@file_rule` or `@cross_rule`.
3. Add the module to the import list in `engine/rules/__init__.py` (else it never registers).
4. If its confidence needs tuning, add a `rule_id`-prefix entry to `RULE_OVERRIDE` in `engine/scoring.py`.
5. Add tests under `tests/` (rule tests typically build `SourceFile`s and assert on findings; remember `registry.reset()`).

## Notes

- `Category` has **6** values (`AI_LEAK, PLACEHOLDER, BUZZWORD, DUPLICATE, ACCESSIBILITY, CODE_SLOP`) and there are **8** rule modules — the README/AGENTS.md diagrams predate `CODE_SLOP`, `scoring.py`, and `store.py`, so trust the code over those docs.
- `AGENTS.md` is the sibling agent-guidance doc and overlaps heavily with this file; keep the two in sync when conventions change.
- `fp_test.mjs` and `.aislop_blueprint_verify.json` at the repo root are scratch/verification artifacts, not part of the package.
