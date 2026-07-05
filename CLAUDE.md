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
aislopfixer . --check [--json|--sarif|--prompt] [--fix] # headless CI mode (see headless.py);
                                              #   exit 0 clean / 1 slop / 2 usage
pytest                                        # full suite (275 tests)
pytest tests/test_algorithm.py -k entropy     # one file / one test
PYTHONPATH=src python -m bench.run            # calibration: recall + clean-FP metrics
PYTHONPATH=src python scripts/shots.py        # regenerate README screenshots (shots/*.svg, live TUI)
node scripts/clean.mjs                         # strip __pycache__/*.pyc (runs as npm prepack)
```

- pytest config lives in `pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `pythonpath = ["src"]`. So **tests run from the repo root without installing** the package; `aislopfixer`/`python -m aislopfixer` do require `pip install -e .` first.
- TUI/screen tests use Textual's async pilot driver (hence `asyncio_mode=auto`).
- Tests that exercise the rule set call `registry.reset()` to clear the global rule lists before re-importing — keep that in mind when adding tests that touch registration.

## Architecture

Pipeline: **scan files → run rules → score → filter against per-project memory → present in TUI → apply fixes → persist outcomes + report.**

```
src/aislopfixer/
├── cli.py / __main__.py   # argparse entry → TUI, or headless via --check/--json/--sarif/--prompt/--fix
├── headless.py            # CI mode: text/JSON/SARIF/fix-brief output, exit codes, batch auto-fix
├── pipeline.py            # scan_project(): the one pipeline TUI + headless share
├── prompter.py            # findings → markdown fix brief for an AI coding assistant
├── config.py              # .aislopfixer.toml: disable prefixes, ignore globs,
│                          #   fail_on/min_confidence defaults (CLI flags win)
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
│   └── rules/             # accessibility, ai_leaks, buzzwords, codegen, design_slop,
│                          #   duplicates, imports, markdown_tells, merge_conflicts,
│                          #   placeholders, prose_tells, secrets, security
├── screens/               # splash → path → scan → results → summary (+ base, modal)
└── widgets/               # animations, counters, logo, stats, guard (too-small overlay)
```

### Rules self-register at import time
A rule is a class decorated with `@file_rule` (runs once per file, has `scan(sf)`) or `@cross_rule` (runs once over all files, has `scan_all(files)` — e.g. duplicate detection). The decorator appends an instance to `FILE_RULES`/`CROSS_RULES`. **`engine/rules/__init__.py` imports every rule module**, and `runner.py` imports the `rules` package — that import chain is what populates the registry. A rule module that isn't listed in `rules/__init__.py` is invisible.

Most rules subclass `PatternRule` with a list of `Pattern` dataclasses (regex + fixability + severity + optional guard fn). Exceptions override `scan()` directly — e.g. `BuzzwordRule` consults `prose_regions()` so buzzwords only flag in human-visible text, never in code identifiers; `AILeakRule` splits STRONG (auto-delete) vs SOFT (manual review).

### Code-aware masking (string/comment context)
`context.code_masks(text, ext)` is a tolerant single-pass lexer (not a parser) returning `(string_spans, comment_spans)` for JS/TS/CSS-like files. `Pattern` exposes three flags built on it, judged by where a match **starts** (`context.point_in`): `exclude_strings` (drop matches starting inside a string/template literal), `exclude_comments` (drop matches in comments), `comments_only`. This is why `eval(` inside a `"…"` string or a `// …` comment is *not* flagged while a real call is — prefer these flags over bespoke guard functions for "ignore this in strings/comments". `PatternRule.scan` computes the masks once per file, only when some active pattern needs them. **Caveat:** the fence rule (`codegen.markdown_fence`) must *not* set `exclude_strings` — the fence is backticks, which the lexer reads as a template literal. The same comment spans double as a prose source: `prose_regions(text, "code", ext)` returns comment spans, so `AILeakRule`/`BuzzwordRule` (which pass `ext_of(sf.rel_path)`) also mine code comments.

### Confidence is centralized, not per-rule
Rules generally do **not** set `Finding.confidence`. `runner._backfill_confidence()` calls `scoring.score_finding()` for any finding left at 0. `scoring.py` resolves confidence via a longest-prefix `RULE_OVERRIDE` table (e.g. `ai_leak.strong → 0.97`), falling back to `CAT_PRIOR[category] × SEV_W[severity]`. `file_score` is a noisy-OR; `project_score` is a self-weighted mean (Σs²/Σs) so one sloppy file dominates. A rule *may* pin its own confidence and the runner leaves it alone. **When you add a rule whose strength isn't captured by category+severity, add a prefix to `RULE_OVERRIDE`.**

Two adjustments ride on top of the base confidence: `scoring.corroborate()` boosts every finding in a file when ≥2 distinct AI-tell families (`_TELL_FAMILIES`: ai_leak, codegen, merge, secret, security, md.emoji, buzzword.density) co-occur there — weak signals reinforce; and `pipeline.demote_noisy()` halves the confidence of rules the project has dismissed ≥3× (`Store.noisy_rules`), so the tool learns what's noise *here*.

### Runner post-processing (order matters)
`run_file_rules` does: collect → drop findings on our own annotation lines (`on_annotation_line`) → **backfill confidence first** → `_dedupe` (by `(file,start,end)`; on a tie keeps the *strongest* by confidence-then-severity, not the first; zero-length spans never deduped) → `_collapse_repeats` (one finding per distinct value for `placeholder.{company,name,address}`) → `_drop_contained` (drop a finding strictly inside a larger *same-category* span; O(n²), skipped above `_CONTAINMENT_CAP=400`) → `corroborate`. Backfill moved ahead of dedupe specifically so dedupe can compare confidences.

### Per-project memory (`<root>/.aislopfixer/`)
`Store` is the key piece **not** in the README/AGENTS architecture diagrams. It owns three files under a hidden `.aislopfixer/` folder (skipped by the scanner's own walk):
- `allowlist.json` — items the user marked "not slop".
- `ledger.json` — every resolved/skipped finding with status + timestamp.
- `report.md` — human-readable snapshot written after each scan.

`Store.filter()` (called from `pipeline.scan_project()`) drops anything allowlisted **and** anything the ledger records as `FIXED`/`ANNOTATED`/`IGNORED` — keyed by `(rule_id, matched_text)`, so suppression **survives line edits and works cross-file**. `SKIPPED` findings deliberately re-surface ("skip" = later, not never). `screens/results.py` calls `store.record()` on each user action; `app.py` calls `store.write_report()`.

### Fixing model
Three fixabilities on `Finding`: `AUTO` (delete/replace via `replacement`), `PROMPT` (user value plugged into `replace_template`), `MANUAL` (flag only). `fixer.py` backs up each file to `<file>.aislopfixer.bak` once (idempotent), computes a unified diff before writing, and **relocates findings by `matched_text` after prior edits** so char offsets stay valid across a fix session. For what the tool can't fix itself, `prompter.py` renders every OPEN finding into a markdown **fix brief** for an AI coding assistant (locations, source excerpts, per-rule guidance, anti-slop guardrails) — exposed as `--prompt` headlessly (composes with `--fix`: auto-fix the safe ones, brief the agent on the rest) and as `x` on the results screen — an export picker (`ExportModal`) offering fix brief / JSON / SARIF / all, written into `.aislopfixer/` (brief also lands on the clipboard). Everything headless can emit is reachable in the TUI; `c` cycles a confidence floor mirroring `--min-confidence`.

### Scanner filtering
Extensions: `.html .htm .jsx .tsx .js .ts .mjs .cjs .vue .svelte .astro .md .mdx .css`. Skips hidden dirs, `node_modules`, `dist`, `build`, `.next`, `vendor`, `__pycache__`, `.turbo`, etc.; skips repo-meta files by stem (`README`, `CLAUDE`, `AGENTS`, `LICENSE`, `CONTRIBUTING`, `CHANGELOG`, …); skips files > 2 MB (`MAX_BYTES`). Lines containing `aislopfixer:` (our own annotations) are never re-flagged.

## Adding a detection rule (the common task)

1. Add (or extend) a module in `src/aislopfixer/engine/rules/`.
2. Decorate the rule class with `@file_rule` or `@cross_rule`.
3. Add the module to the import list in `engine/rules/__init__.py` (else it never registers).
4. If its confidence needs tuning, add a `rule_id`-prefix entry to `RULE_OVERRIDE` in `engine/scoring.py`.
5. To keep a `Pattern` out of strings/comments, set `exclude_strings` / `exclude_comments` rather than writing a guard (see Code-aware masking).
6. Add tests under `tests/`, and a labeled case to `bench/corpus.py` (slop case with `expect` prefixes, or a `clean` case) — `tests/test_bench.py` then guards its recall and that nothing fires on clean input.

## Release checklist

When publishing a new version:
1. Bump `version` in **`package.json`**, **`pyproject.toml`** and **`src/aislopfixer/__init__.py`** (all three must match).
2. Update **`README.md`** — change the "Current version" line under the badges to reflect the new version.
3. Run `npm publish` and/or `git tag v<version> && git push --tags`.

## Notes

- `Category` has **8** values (`SECURITY, AI_LEAK, PLACEHOLDER, BUZZWORD, DUPLICATE, ACCESSIBILITY, CODE_SLOP, DESIGN`) and there are **13** rule modules. README/AGENTS.md are currently in sync with the code, but when they disagree, trust the code. `SECURITY` is the modern, serious class (XSS/SQLi/command-injection sinks, disabled TLS, weak crypto, hardcoded real keys — see `engine/rules/security.py`); `merge_conflicts` + `codegen.markdown_fence` report under `CODE_SLOP`; `secrets` (placeholder creds) reports under `PLACEHOLDER`. A new `Category` must also get a `CATEGORY_COLORS` + `CATEGORY_ICON` entry in `theme.py` (the results tree indexes them by category, so a missing entry is a `KeyError`).
- `DuplicateRule` (cross-file) clusters prose blocks by word-shingle **Jaccard ≥ 0.85** (`engine/rules/duplicates.py`), so it catches near-duplicate copy lightly reworded per page, not just byte-identical blocks; the message says "Duplicate" vs "Near-duplicate" accordingly. Still cross-file, prose-only, INFO.
- `AGENTS.md` is the sibling agent-guidance doc and overlaps heavily with this file; keep the two in sync when conventions change.
- `bench/` is the calibration harness: a labeled corpus (`bench/corpus.py`) + scorer (`bench/harness.py`). Run `python -m bench.run` (or `PYTHONPATH=src python -m bench.run`) for recall / clean-FP metrics; `tests/test_bench.py` enforces full recall and zero clean-file false positives.
