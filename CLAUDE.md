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
aislopfixer . --check --fail-on risky         # gate CI on the Impact axis, not severity
pytest                                        # full suite (418 tests)
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
├── prompter.py            # findings → markdown fix brief, structured by Impact
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
│   └── rules/             # accessibility, ai_leaks, buzzwords, codegen, copy_slop,
│                          #   design_slop, duplicates, imports, landing_tells,
│                          #   markdown_tells, merge_conflicts, placeholders,
│                          #   prose_tells, secrets, security
├── screens/               # splash → path → scan → results → summary (+ base, modal)
└── widgets/               # animations, counters, logo, stats, guard (too-small overlay)
```

### Rules self-register at import time
A rule is a class decorated with `@file_rule` (runs once per file, has `scan(sf)`) or `@cross_rule` (runs once over all files, has `scan_all(files)` — e.g. duplicate detection). The decorator appends an instance to `FILE_RULES`/`CROSS_RULES`. **`engine/rules/__init__.py` imports every rule module**, and `runner.py` imports the `rules` package — that import chain is what populates the registry. A rule module that isn't listed in `rules/__init__.py` is invisible.

Most rules subclass `PatternRule` with a list of `Pattern` dataclasses (regex + fixability + severity + optional guard fn). Exceptions override `scan()` directly — e.g. `BuzzwordRule` consults `prose_regions()` so buzzwords only flag in human-visible text, never in code identifiers; `AILeakRule` splits STRONG (auto-delete) vs SOFT (manual review).

### Code-aware masking (string/comment context)
`context.code_masks(text, ext)` is a tolerant single-pass lexer (not a parser) returning `(string_spans, comment_spans)` for JS/TS/CSS-like files. It also recognizes JS regex literals (expression-position `/…/`, marked as string-like spans so their `//` never reads as a comment). `code_masks` and `prose_regions` are `lru_cache`d on the full text — treat the returned lists as immutable; `pipeline.scan_project()` clears both caches after each scan. `Pattern` exposes three flags built on it, judged by where a match **starts** (`context.point_in`): `exclude_strings` (drop matches starting inside a string/template literal), `exclude_comments` (drop matches in comments), `comments_only`. This is why `eval(` inside a `"…"` string or a `// …` comment is *not* flagged while a real call is — prefer these flags over bespoke guard functions for "ignore this in strings/comments". `PatternRule.scan` computes the masks once per file, only when some active pattern needs them. **Caveat:** the fence rule (`codegen.markdown_fence`) must *not* set `exclude_strings` — the fence is backticks, which the lexer reads as a template literal. The same comment spans double as a prose source: `prose_regions(text, "code", ext)` returns comment spans, so `AILeakRule`/`BuzzwordRule` (which pass `ext_of(sf.rel_path)`) also mine code comments.

### Confidence is centralized, not per-rule
Rules generally do **not** set `Finding.confidence`. `runner._backfill_confidence()` calls `scoring.score_finding()` for any finding left at 0. `scoring.py` resolves confidence via a longest-prefix `RULE_OVERRIDE` table (e.g. `ai_leak.strong → 0.97`), falling back to `CAT_PRIOR[category] × SEV_W[severity]`. `file_score` is an **impact-weighted** noisy-OR: findings noisy-OR within their own `Impact` class, each class is capped at its `_IMPACT_CEILING` (POLISH 0.40, RISKY 0.85, BROKEN 1.0), and the classes then noisy-OR together. A flat noisy-OR made the headline a *volume* meter — 13 buzzwords and three injection vulns both scored 100/100 — so the ceiling is what keeps the number meaningful; **POLISH alone can never pass 40**. `project_score` is a self-weighted mean (Σs²/Σs) so one sloppy file dominates. A rule *may* pin its own confidence (pass `confidence=` to `build_finding`, which sets `Finding.pinned`) — scoring then never backfills, resets or corroboration-boosts that value. **When you add a rule whose strength isn't captured by category+severity, add a prefix to `RULE_OVERRIDE`.**

Two adjustments ride on top of the base confidence: `scoring.corroborate()` boosts every finding in a file when ≥2 distinct AI-tell families (`_TELL_FAMILIES`: ai_leak, codegen, merge, secret, security, md.emoji, buzzword.density, import., design., copy.) co-occur there — weak signals reinforce; and `pipeline.demote_noisy()` halves the confidence of rules the project has dismissed ≥3× (`Store.noisy_rules`), so the tool learns what's noise *here*.

### Impact: application problems vs simple warnings
`Fixability` says *how* to fix (auto / ask for a value / by hand); **`Impact` says what is at stake**, and it is the axis the UI and the fix brief lead on. Three values (`engine/models.py`): `BROKEN` (the code does not work as written — merge markers, elision, stubs, hallucinated imports/symbols, a pasted chat fence), `RISKY` (it runs but ships a hazard — every `security.*`/`secret.*`, `ai_leak.strong`, swallowed catches, dead/placeholder links + emails + images, invented `design.fake_*` claims, `a11y.img_no_alt`) and `POLISH` (voice and aesthetics: `buzzword.*`, `copy.*`, `prose.*`, `md.*`, the aesthetic `design.*` tells, `import.unused`, `duplicate.*`, `placeholder.todo`, `ai_leak.soft`). **`BROKEN` + `RISKY` = "application problems"** (`Impact.is_application`); `POLISH` is the simple-warning tail.

Impact is resolved from a longest-prefix `IMPACT_OVERRIDE` table in `scoring.py` (same mechanism as `RULE_OVERRIDE`) and exposed as a **derived `Finding.impact` property**, not a stored field — unlike confidence (which rules pin and `corroborate`/`demote_noisy` adjust), nothing ever varies impact per finding, so computing it on read means it can never be stale or missed on a hand-built Finding. Anything unlisted is `POLISH`: a new rule is a simple warning until someone classifies it, which is the safe default since POLISH never inflates the "fix this" headline. `tests/test_scoring.py::test_every_registered_rule_has_a_deliberate_impact` fails if a table key stops matching a live rule id — a renamed rule would otherwise silently demote real defects to POLISH.

Why it exists: both an SQLi sink and the word "seamless" are `MANUAL`, so before this axis the brief listed them as peers and the results screen labelled both "manual review". On `sample/`, 25 of 41 findings were single-word buzzwords at 30% — an agent handed that brief rewrites adjectives and leaves the sink. **Anything user-facing that ranks or counts findings should lead on impact, not on the total.**

Impact is not just a label — three things gate on it, and a new rule inherits all three from its `IMPACT_OVERRIDE` entry: `file_score`'s per-class ceiling (above), `--fail-on broken|risky` (the CI gate — 19 POLISH rules carry `severity=warning`, so the severity gate reddened a build over adjectives while the brief told the agent to ignore them), and the brief's own structure (BROKEN/RISKY written out in full, POLISH rolled up).

### Runner post-processing (order matters)
`run_file_rules` does: collect → drop findings on our own annotation lines (`on_annotation_line`; zero-span doc-level findings are exempt) → **backfill confidence first** → `_dedupe` (by `(file,start,end)`; on a tie keeps the *strongest* by confidence-then-severity, not the first; zero-length spans never deduped) → `_collapse_repeats` (one finding per distinct value for `placeholder.{company,name,address}`) → `_drop_contained` (drop a finding strictly inside a larger *same-category* span; O(n²), skipped above `_CONTAINMENT_CAP=400`) → `corroborate`. Backfill moved ahead of dedupe specifically so dedupe can compare confidences.

### Per-project memory (`<root>/.aislopfixer/`)
`Store` is the key piece **not** in the README architecture diagram. It owns three files under a hidden `.aislopfixer/` folder (skipped by the scanner's own walk):
- `allowlist.json` — items the user marked "not slop".
- `ledger.json` — every resolved/skipped finding with status + timestamp.
- `report.md` — human-readable snapshot written after each scan.

`Store.filter()` (called from `pipeline.scan_project()`) drops anything allowlisted **and** anything the ledger records as `ANNOTATED`/`IGNORED` — keyed by `(rule_id, matched_text, file)`, so suppression is **per-file and survives line edits**; the allowlist alone is cross-file. `FIXED` is recorded but *not* suppressed: a fix removes the text, so a later match of the same signature is a different occurrence (or a revert) and must be reported. `SKIPPED` findings deliberately re-surface ("skip" = later, not never). `screens/results.py` calls `store.record()` on each user action; `app.py` calls `store.write_report()`.

### Fixing model
Three fixabilities on `Finding`: `AUTO` (delete/replace via `replacement`), `PROMPT` (user value plugged into `replace_template`), `MANUAL` (flag only). `fixer.py` backs up each file to `<file>.aislopfixer.bak` once (idempotent), computes a unified diff before writing, and **relocates findings by `matched_text` after prior edits** so char offsets stay valid across a fix session. Edits happen on LF-normalized, BOM-stripped text (offsets match the scanner's universal-newline + `utf-8-sig` reads) but are written back with the file's **original line endings and BOM** (`_read_text`/`_write_text`) — never use a bare `write_text` in `fixer.py`, it would rewrite whole files as CRLF on Windows. Bulk auto-fix (headless `--fix` and TUI `p`) runs to a bounded **fixpoint** (`MAX_FIX_PASSES`): fixing can unmask new findings (emoji header → bare boilerplate heading), so touched files are re-scanned and re-fixed until stable. `fixer.snapshot_file`/`restore_file` power the TUI's `u` undo. After edits, `fixer.reanchor()` recomputes line/col/snippet of still-open findings in touched files; headless `--fix` and every TUI fix/annotate path call it so reports and tree labels carry real positions. For what the tool can't fix itself, `prompter.py` renders the OPEN findings into a markdown **fix brief** for an AI coding assistant, **organized by `Impact`**: an intro naming the split, the ground rules, then `## 1. Broken` / `## 2. Risky` with a full entry per finding (location, source excerpt, per-rule guidance), then `## N. Simple warnings` where every POLISH finding collapses to **one rolled-up line per rule family** (count, files, example matches, one fix line) instead of one numbered entry each — word-list families (`buzzword.`, `copy.microcopy.`, `copy.testimonial.`, `prose.`, `ai_leak.soft`) roll up to the family via `_ROLLUP_FAMILIES`. That restructure cut the `sample/` brief from 476 lines to 159 without dropping information. It is exposed as `--prompt` headlessly (composes with `--fix`: auto-fix the safe ones, brief the agent on the rest) and as `x` on the results screen — an export picker (`ExportModal`) offering fix brief / JSON / SARIF / all, written into `.aislopfixer/` (brief also lands on the clipboard). Everything headless can emit is reachable in the TUI; `c` cycles a confidence floor mirroring `--min-confidence`.

### Scanner filtering
Extensions: `.html .htm .jsx .tsx .js .ts .mjs .cjs .vue .svelte .astro .md .mdx .css`. Skips hidden dirs, `node_modules`, `dist`, `build`, `.next`, `vendor`, `__pycache__`, `.turbo`, etc.; skips repo-meta files by stem (`README`, `CLAUDE`, `AGENTS`, `LICENSE`, `CONTRIBUTING`, `CHANGELOG`, …); skips files > 2 MB (`MAX_BYTES`); skips minified build artifacts (`*.min.js`-style names, or code/CSS whose head averages > 300 chars/line — `_looks_minified`, mirrored in `count_eligible` so progress totals stay exact). Lines containing `aislopfixer:` (our own annotations) are never re-flagged.

## Adding a detection rule (the common task)

1. Add (or extend) a module in `src/aislopfixer/engine/rules/`.
2. Decorate the rule class with `@file_rule` or `@cross_rule`.
3. Add the module to the import list in `engine/rules/__init__.py` (else it never registers).
4. If its confidence needs tuning, add a `rule_id`-prefix entry to `RULE_OVERRIDE` in `engine/scoring.py`.
5. **If it is an application problem, add a prefix to `IMPACT_OVERRIDE`** (also `engine/scoring.py`). Unlisted rules default to `POLISH`, so a `BROKEN`/`RISKY` rule that skips this step gets summarized in the fix brief instead of written out, and never reaches the headline count.
6. To keep a `Pattern` out of strings/comments, set `exclude_strings` / `exclude_comments` rather than writing a guard (see Code-aware masking).
7. Add tests under `tests/`, and a labeled case to `bench/corpus.py` (slop case with `expect` prefixes, or a `clean` case) — `tests/test_bench.py` then guards its recall and that nothing fires on clean input. **Write the clean twin too**: for anything design/copy-shaped, add the closest *legitimate human* page that must stay silent. A rule that cannot separate its slop case from its clean twin is not a detector — see `pricing_triad` / `clean_bare_pricing_triad`.

## Release checklist

When publishing a new version:
1. Bump `version` in **`package.json`**, **`pyproject.toml`** and **`src/aislopfixer/__init__.py`** (all three must match).
2. Update **`README.md`** — change the "Current version" line under the badges to reflect the new version.
3. Run `npm publish` and/or `git tag v<version> && git push --tags`.

## Notes

- `Category` has **8** values (`SECURITY, AI_LEAK, PLACEHOLDER, BUZZWORD, DUPLICATE, ACCESSIBILITY, CODE_SLOP, DESIGN`) and there are **15** rule modules. README/AGENTS.md are currently in sync with the code, but when they disagree, trust the code. `SECURITY` is the modern, serious class (XSS/SQLi/command-injection sinks, disabled TLS, weak crypto, hardcoded real keys — see `engine/rules/security.py`); `merge_conflicts` + `codegen.markdown_fence` report under `CODE_SLOP`; `secrets` (placeholder creds) reports under `PLACEHOLDER`; `landing_tells` (fake metric strips, pricing triad, section-scaffold recipe, fake logo clouds, glow blobs) reports under `DESIGN`; `copy_slop` (≥2-gated template microcopy, testimonial phrasing) reports under `BUZZWORD`. A new `Category` must also get a `CATEGORY_COLORS` + `CATEGORY_ICON` entry in `theme.py` (the results tree indexes them by category, so a missing entry is a `KeyError`).
- **Design gates that exist to stop false positives — don't "simplify" them back.** `design.landing_kit` needs ≥3 signal families *and* ≥1 from `_KIT_STRONG`; two things keep that gate real. (a) `_KIT_PURPLE_ACCENT` matches purple as the **paint** (`bg|text|from|to|via|fill|stroke`) and deliberately **not** `border-`/`ring-`: a lone `border-indigo-500` on a highlighted card is ordinary Tailwind, and counting it let one stray class unlock the kit — a hand-written pricing page scored 82% and 92/100 slop. (b) `pricing` is **not** in `_KIT_STRONG`, and `design.pricing_triad` fires only when the file carries another landing tell (`_pricing_triad(..., corroborated=)`): the "Most Popular" badge + per-month + Enterprise trio is how Stripe, Linear and every real pricing page is built, so alone it is a description, not a detection. `bench/corpus.py` pins both boundaries with `clean_human_pricing_page` and the `pricing_triad` / `clean_bare_pricing_triad` pair.
- `DuplicateRule` (cross-file) clusters prose blocks by word-shingle **Jaccard ≥ 0.85** (`engine/rules/duplicates.py`), so it catches near-duplicate copy lightly reworded per page, not just byte-identical blocks; the message says "Duplicate" vs "Near-duplicate" accordingly. Still cross-file, prose-only, INFO.
- Failure/empty states are deliberate, don't "simplify" them away: a crashed scan **stays on `ScanScreen`** with `r` retry / `n` new folder / `q` quit (it must never fall through to an empty — hence "clean-looking" — results screen), and `ResultsScreen`'s banner distinguishes "nothing to scan" (0 eligible files, via `app.files_scanned`) from a genuinely clean project.
- `AGENTS.md` is the sibling agent-guidance doc and overlaps heavily with this file; keep the two in sync when conventions change.
- `bench/` is the calibration harness: a labeled corpus (`bench/corpus.py`) + scorer (`bench/harness.py`). Run `python -m bench.run` (or `PYTHONPATH=src python -m bench.run`) for recall / clean-FP metrics; `tests/test_bench.py` enforces full recall and zero clean-file false positives.
