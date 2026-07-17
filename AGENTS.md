# aislopfixer

Terminal TUI (Textual) that finds/fixes AI slop in local web projects. Fully offline, rule-based.

## Run

```bash
pip install -e .            # basic
pip install -e ".[dev]"     # +pytest/pytest-asyncio
aislopfixer ./sample        # CLI entry: aislopfixer.cli:main
python -m aislopfixer ./sample
aislopfixer . --check       # headless CI mode (--json/--sarif/--prompt/--fix/--min-confidence)
aislopfixer . --check --fail-on risky   # CI gate on impact (broken|risky), not severity
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
- **`Impact` = what is at stake, orthogonal to `Fixability` = how to fix.** `BROKEN` (code doesn't work: merge markers, elision, stubs, hallucinated imports) / `RISKY` (runs but ships a hazard: `security.*`, `secret.*`, `ai_leak.strong`, swallowed catches, dead links, placeholder contact data, invented `design.fake_*` claims, `a11y.img_no_alt`) / `POLISH` (voice + aesthetics: `buzzword.*`, `copy.*`, `prose.*`, `md.*`, aesthetic `design.*`, `import.unused`, `duplicate.*`, `placeholder.todo`). `BROKEN + RISKY` = **application problems** (`Impact.is_application`). Resolved by longest-prefix `IMPACT_OVERRIDE` in `scoring.py`; a **derived property** on `Finding`, not a stored field (nothing varies it per finding, so it can't go stale). Unlisted ⇒ `POLISH`. **A new BROKEN/RISKY rule must add its prefix**, else it gets summarized rather than written out. Reason it exists: an SQLi sink and the word "seamless" are both `MANUAL` — the brief listed them as peers and the UI called both "manual review".
- Fix brief (`prompter.py`) is organized by impact: `## Broken` / `## Risky` get a full entry each; `POLISH` collapses to one rolled-up line per rule family (`_ROLLUP_FAMILIES` folds word-list families like `buzzword.` into one line). UI leads on the same split — never on the total. The Risky lead is generated from the families actually present (`_risky_lead`), never fixed prose — promising "a sink, a credential… an attacker will find" over seven placeholders and three missing alts sends the agent hunting a vuln that isn't there.
- Impact also gates `--fail-on broken|risky` (the CI gate) and `file_score`'s per-class ceiling. `file_score` is an **impact-weighted** noisy-OR: noisy-OR within a class, cap at `_IMPACT_CEILING` (POLISH 0.40 / RISKY 0.85 / BROKEN 1.0), then noisy-OR the classes. A flat noisy-OR made it a volume meter — 13 buzzwords and 3 injection vulns both scored 100/100.
- Severity is *not* a CI gate: 19 POLISH rules carry `severity=warning`, so `--fail-on warning` (the default) reddens a build over adjectives the brief just told the agent to ignore. Use `--fail-on risky`.
- **Design FP gates, deliberate:** `_KIT_PURPLE_ACCENT` matches purple as paint (`bg|text|from|to|via|fill|stroke`), never `border-`/`ring-`; `pricing` is not in `_KIT_STRONG`; `design.pricing_triad` needs corroboration from another landing tell. Without these, an ordinary human pricing page scored 82% / 92-slop. Pinned by `clean_human_pricing_page` + `clean_bare_pricing_triad` in `bench/corpus.py`.
- Same shape, same reason: `_GLASS_SURFACE` is paint (`bg-white/10`), never `border-white/10`, and blur + surface must share an element (`_glass_anchor`) — a sticky blurred header with a hairline border unlocked a `_KIT_STRONG` family and scored a hand-written shop page 82%. `_CSS_GRADIENT`'s two colour lists must stay **disjoint**: while `violet` sat in both, one stop satisfied both lookaheads and a rainbow was reported as a "purple→pink" gradient.
- **An AUTO fix may never delete more than the slop.** `ai_leak.strong` expands to the line only when the leak *owns* it (`_owns_its_line`), else MANUAL — it used to delete any line the leak sat on, taking a React `return` with it. `placeholder.lorem` matches the pseudo-Latin *run*, not `lorem ipsum` + the rest of the line, so prose *about* lorem ipsum survives. Both reported "no slop found — fixed automatically" while destroying the file.
- `fixer.py` relocates findings after prior edits (`_locate()` finds current offset by matched_text).
- `fixer.py` edits LF-normalized text but writes back the file's original line endings (`_read_text`/`_write_text`) — never a bare `write_text`, which would CRLF-rewrite whole files on Windows. `fixer.reanchor()` refreshes line/col/snippet of still-open findings after edits (called from headless `--fix` and every TUI fix/annotate path).
- Backup file: `<file>.aislopfixer.bak`, created once per file (idempotent).
- `diff_preview()` outputs unified diff before applying.

## Flow

1. `SplashScreen` → always `PathScreen` (pre-filled when a PATH arg was given — confirm with Enter).
2. `PathScreen` → user enters/confirms path.
3. `ScanScreen` → runs `pipeline.scan_project()` in a worker thread, transitions to results. A failed scan stays here with `r` retry / `n` new folder / `q` quit — it never falls through to an empty results screen.
4. `ResultsScreen` → tree (left) + detail panel (right). A hint line leads on the impact split ("N application problem(s) · M simple warning(s)"); tree leaves are sorted impact-first and tagged `BROKEN`/`RISKY` — `POLISH` is left untagged on purpose, since it is the bulk of any tree and an untagged row *is* the "just taste" signal. Keybindings: `f` fix, `d` diff preview (`DiffModal`), `s` skip, `a` annotate, `i` not slop (`s`/`i` on a category/file row act on the whole branch), `u` undo last fix/annotate, `p` fix all auto (fixpoint: re-scans touched files ≤3 passes), `x` export (AI fix brief / JSON / SARIF via `ExportModal`, which states what the brief covers), `c` confidence floor, `q` summary/modal.
5. `SummaryScreen` → per-category counts.

## Release

Version lives in 3 places: `package.json`, `pyproject.toml`, `src/aislopfixer/__init__.py`. Keep in sync. Update version in README.md badges too.

## Dependencies

- Python ≥3.11, setuptools build backend, `textual>=0.80`.
- Dev: `pytest>=8`, `pytest-asyncio>=0.23`.
