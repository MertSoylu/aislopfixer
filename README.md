# aislopfixer

> Find and fix **AI-generated slop** in web projects — hallucinated dependencies, security holes, swallowed errors, leftover chat residue and LLM marketing prose. Terminal UI + CI mode. Fully offline, rule-based, no API keys.

[![npm](https://img.shields.io/npm/v/@mertsoylu/aislopfixer.svg)](https://www.npmjs.com/package/@mertsoylu/aislopfixer)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Current version: 0.5.0** — [npm](https://www.npmjs.com/package/@mertsoylu/aislopfixer)

AI-generated code ships with a recognizable class of defects — and they are not the old "As an AI language model…" giveaways. Today's models hallucinate package imports that break your build (and invite [slopsquatting](https://en.wikipedia.org/wiki/Slopsquatting) attacks), wrap everything in `try/catch` and silently swallow the error, store JWTs in `localStorage`, build SQL with template literals, leave `// ... rest of the code ...` elision markers behind, and coat every landing page in "It's not just a tool — it's a game changer" prose.

**aislopfixer** scans your project for exactly this class of mistakes, ranks each finding by confidence, and lets you fix them one keystroke at a time — or gate your CI on them.

Everything runs **locally**. No network calls, no LLM, no telemetry. Deterministic rules you can read.

<p align="center">
  <img src="https://raw.githubusercontent.com/MertSoylu/aislopfixer/main/shots/3-results.svg" alt="aislopfixer results view" width="800">
</p>

---

## Install

```bash
npm install -g @mertsoylu/aislopfixer
aislopfixer ./path/to/project
```

Requires **Python ≥ 3.11** on your machine. On first run the npm launcher builds a small isolated Python environment under `~/.aislopfixer/` (needs internet once), then starts instantly thereafter.

## What it detects

Only mistakes that **current-generation models still make** — trivial lint is deliberately out of scope.

| Category | What | Why it matters |
|----------|------|----------------|
| 🧨 **Hallucinated imports** | `import x from 'pkg'` where `pkg` is in no `package.json` on the path to the root (monorepo-aware; Node built-ins, tsconfig `paths`, `@/`-style aliases all respected); named imports the target module demonstrably never exports; unused leftover imports | Build breaks; typo-squatted registry names are a supply-chain attack vector |
| 🔓 **Security** | XSS sinks (`innerHTML`, `dangerouslySetInnerHTML`, `v-html`), SQL built by interpolation/concat, command injection, `eval`, disabled TLS validation, wildcard CORS, weak crypto, `Math.random()` secrets, hardcoded real keys (AWS/GitHub/OpenAI/Stripe/…, JWTs, PEM blocks, high-entropy literals), tokens in `localStorage`, `postMessage(…, '*')` | Roughly half of generated snippets carry a known weakness; these are the concrete, offline-detectable shapes |
| 🕳️ **Swallowed errors** | `catch (e) {}` and `.catch(() => {})` — a body holding only a comment (`catch { /* quota errors are fine */ }`) is treated as a documented decision and left alone; log-only catches (`catch (e) { console.error(e) }`); catches that silently `return null`/`[]`/`{}` | The try/catch-everything habit makes failures vanish silently |
| ✂️ **Broken pastes** | Elision markers (`// ... existing code ...`), not-implemented stubs, `debugger;`, leftover ``` fences from chat, unresolved merge conflict markers | The file is literally incomplete or unparseable |
| 🔑 **Placeholder secrets** | `YOUR_API_KEY_HERE`, `sk-xxxx…`, `password: "changeme"` | Fails at runtime and normalizes hardcoding credentials |
| 🗑️ **Placeholders / dummy data** | lorem ipsum, `[Your Company Name]`, `example.com`, fake API endpoints (`api.yourdomain.com`), 555-phones, `href="#"`, placeholder images | Ships as-is embarrassingly often |
| 💬 **AI chat residue** | "As an AI language model…", "Certainly! Here is…", "I hope this helps" | Copy-pasted chat answers in production copy |
| 📢 **LLM prose tells** | "It's not just X — it's Y", "Whether you're … or …", "delve", "seamlessly", em-dash overuse, buzzword density, emoji-headed README sections, checkmark feature lists | The house style of machine marketing copy |
| 🗣️ **Template marketing copy** | Interchangeable SaaS microcopy ("No credit card required" + "Cancel anytime" + "Everything you need to…" — fires only when ≥2 co-occur), fabricated-testimonial phrasing ("completely transformed the way we work", "game-changer for our team") | Copy that could sit on any product's page — no product specificity |
| 🎨 **AI slop design** | The stock purple→pink hero gradient (Tailwind and raw CSS), gradient-clipped hero text, glassmorphism, decorative glow blobs (`rounded-full` + `blur-3xl`), invented social proof ("Trusted by 10,000+ developers"), fake stat strips ("99.9% uptime · 24/7 support · 10k+ users"), fabricated big-brand logo clouds, the stock pricing triad ("Most Popular" + per-month + Enterprise), placeholder avatar hosts, emoji-decorated UI copy, `<!-- Hero Section -->`-style scaffold recipes, and a composite "landing kit" score across 13 signal families | The instantly recognizable AI landing-page dialect — flagged on combined signals, so one intentional gradient stays quiet |
| 🖼️ **Image accessibility** | Missing or generic (`alt="image"`) alt text | The one a11y mistake generators still make |
| 📋 **Cross-file duplicates** | The same (or lightly reworded) marketing paragraph pasted across pages; the same helper function re-emitted into several files instead of imported once | Word/token-shingle Jaccard clustering |
| 💤 **Over-commenting** | Files where every other line is a `//` narration comment (directives like `eslint-disable` excluded) | The step-by-step-narrator habit of generated code |

Context-aware by construction: `eval(` inside a string or comment is not flagged, buzzwords only count in human-visible prose (never identifiers), `[id]`/`[a-z]`/`[...slug]` framework tokens are never "placeholders".

## Use it interactively (TUI)

```bash
aislopfixer ./my-site
```

### 1 · Point it at a project

Confirm the target folder (pre-filled from the command line), watch the scan run:

| Splash | Scan |
|--------|------|
| ![splash](https://raw.githubusercontent.com/MertSoylu/aislopfixer/main/shots/1-splash.svg) | ![scan](https://raw.githubusercontent.com/MertSoylu/aislopfixer/main/shots/2-scan.svg) |

### 2 · Triage the findings

![results — findings tree, confidence meters, source excerpt and fix preview](https://raw.githubusercontent.com/MertSoylu/aislopfixer/main/shots/3-results.svg)

Left: findings grouped by **category → file**, each file with a mini slop bar, each finding with its severity and fix-type icon. Right: the selected finding in full — confidence meter, the offending source lines with the match highlighted, and a preview of exactly what a fix would change. Handle each finding with one key (`?` shows this list in-app):

| Key | Action |
|-----|--------|
| `f` | fix selected finding (auto, or prompts you for the value) |
| `d` | preview the exact diff the fix would make |
| `p` | fix **all** safe automatic findings at once |
| `a` | annotate in source |
| `s` | skip (re-surfaces next scan) — on a category/file row: skip the whole branch |
| `i` | not slop — remembered forever — on a category/file row: the whole branch |
| `u` | undo the last fix/annotate (restores the file) |
| `x` | export — fix brief / JSON / SARIF |
| `1 2 3` / `0` | filter by severity / clear |
| `c` | cycle the confidence floor (all → 45 → 60 → 75%) |
| `h` | hide already-handled findings |
| `q` | summary |

Three fix types: **auto** deletes/replaces outright (chat residue, lorem ipsum, `debugger;`) — every touched file is backed up to `<file>.aislopfixer.bak` first; **prompt** asks you for the real value (URLs, emails, alt text) and inserts it; **manual** (security, hallucinated imports) is a judgement call — annotate, fix by hand, or export it (next step).

### 3 · Hand what's left to your AI assistant

![export picker — fix brief, JSON or SARIF](https://raw.githubusercontent.com/MertSoylu/aislopfixer/main/shots/5-export.svg)

Half the findings need judgement — exactly what a coding agent is good at once it's told *precisely* what's wrong and where. `x` opens the export picker:

- **`b` fix brief** (`fix-prompt.md`, also copied to the clipboard) — every open finding with exact location, source excerpt, per-rule fix guidance, and guardrails so the agent fixes only what was found without introducing new slop. Paste it into Claude Code, Cursor or Copilot; the brief ends by telling the agent to verify with `aislopfixer --check`. The detector stays deterministic — the AI only executes a vetted work order.
- **`j` JSON** (`findings.json`) / **`s` SARIF** (`findings.sarif`) — the same machine-readable output as `--json` / `--sarif`.

Everything lands in `.aislopfixer/`, which is never itself scanned.

### 4 · Summary

![summary — slop score, per-category bars, next steps](https://raw.githubusercontent.com/MertSoylu/aislopfixer/main/shots/4-summary.svg)

Slop score, severity breakdown, animated per-category fixed/found bars — plus where the report went and what to do next (`b` back · `r` rescan · `n` new folder · `q` quit).

### It learns your project

Everything you resolve or dismiss is remembered in `<project>/.aislopfixer/`:

- **allowlist** — "not slop" verdicts, keyed by content so they survive edits and apply across files;
- **ledger** — annotated/dismissed findings never come back (fixed spots stay quiet naturally: the text is gone, and a re-match is a new occurrence); skipped ones intentionally do;
- **noise demotion** — a rule you dismiss 3+ times gets its confidence halved in that project;
- **report.md** — human-readable snapshot after each scan.

## Use it in CI / pre-commit

```bash
aislopfixer . --check                    # print findings, exit 1 if any warning+
aislopfixer . --check --fail-on risky    # gate on application problems only ← recommended
aislopfixer . --check --fail-on broken   # only code that doesn't work gates the build
aislopfixer . --json                     # machine-readable output
aislopfixer . --sarif > slop.sarif       # SARIF 2.1.0 for GitHub code scanning
aislopfixer . --fix                      # apply safe auto-fixes, then report the rest
aislopfixer . --check --min-confidence 0.8
aislopfixer . --fix --prompt > fix-brief.md   # auto-fix the safe ones, brief your AI on the rest
```

`--fail-on` takes either axis. **Impact** — `risky` (any application problem) or `broken` (only code that does not work) — is what you usually want in CI: it gates on the same split the TUI and the fix brief lead on, so a page whose only sin is the word "seamless" never turns the build red. **Severity** — `info`/`warning`/`error` — still works, and `never` always exits 0.

Exit codes: `0` clean, `1` something tripped `--fail-on` (default `warning`), `2` usage error. The project's `.aislopfixer` memory applies in CI too — vetted false positives stay silent (disable with `--no-store`).

GitHub Actions — one step, PR annotations included via code scanning:

```yaml
- uses: mertsoylu/aislopfixer@main
  with:
    path: .
    fail-on: error
    sarif-file: slop.sarif        # optional
- uses: github/codeql-action/upload-sarif@v3   # optional, annotates the PR
  if: always()
  with: { sarif_file: slop.sarif }
```

pre-commit:

```yaml
repos:
  - repo: https://github.com/mertsoylu/aislopfixer
    rev: v0.3.0
    hooks:
      - id: aislopfixer
```

## Configuration

Optional `.aislopfixer.toml` at the project root — CLI flags always win:

```toml
disable = ["design.emoji_ui", "buzzword.delve"]  # rule-id prefixes to turn off
ignore = ["legacy/**", "third_party/**"]          # path globs to skip entirely
fail_on = "risky"        # exit-code gate: broken|risky (impact) or info|warning|error|never
min_confidence = 0.5     # headless reporting floor, 0..1
```

`disable` and `ignore` apply to the TUI and headless mode alike.

## Scoring

Every finding carries a confidence (0–1) from a per-rule table, falling back to category × severity. Weak signals **corroborate**: when several independent AI-authorship tells co-occur in one file (an elision marker + a stub + a debug log), every finding there gets boosted. The file score is an impact-weighted noisy-OR — findings accumulate within their impact class, and each class is capped, so a pile of buzzwords can never read like a shipped vulnerability. The project score is a self-weighted mean, so one sloppy file isn't diluted by fifty clean ones. Confidence gates bulk auto-fix (≥ 0.60) and is yours to threshold in CI.

## Supported files

`.html .htm .jsx .tsx .js .ts .mjs .cjs .vue .svelte .astro .md .mdx .css` — skips `node_modules`, build output, hidden dirs, repo-meta docs (README/LICENSE/CLAUDE/AGENTS…), files > 2 MB, and minified bundles (`*.min.js` or single-giant-line files).

## Architecture

```
src/aislopfixer/
├── cli.py            # entrypoint: TUI by default, --check/--json/--sarif/--prompt/--fix headless
├── headless.py       # CI mode: text/JSON/SARIF/fix-brief rendering, exit codes, batch auto-fix
├── pipeline.py       # the one scan pipeline both front-ends share
├── prompter.py       # findings → fix brief for an AI coding assistant
├── config.py         # .aislopfixer.toml: disable rules, ignore globs, thresholds
├── app.py            # Textual App, screen orchestration
├── scanner.py        # dir walk → SourceFile (ext/ignore/size filters)
├── fixer.py          # AUTO/PROMPT/MANUAL fixes, backups, diff preview
├── store.py          # .aislopfixer/ project memory (allowlist, ledger, report)
├── engine/
│   ├── runner.py     # run rules → dedupe → collapse → containment → corroborate
│   ├── scoring.py    # confidence + impact tables, impact-weighted file score
│   ├── context.py    # prose regions + string/comment masking (the FP killer)
│   └── rules/        # ai_leaks, placeholders, buzzwords, prose_tells, copy_slop,
│                     #   duplicates, accessibility, codegen, design_slop,
│                     #   landing_tells, markdown_tells, merge_conflicts,
│                     #   secrets, security, imports   (15 modules)
├── screens/          # splash → path → scan → results → summary
└── widgets/          # animations, counters, logo, stats
```

Rules self-register via `@file_rule` / `@cross_rule` decorators; most are declarative `Pattern` lists (regex + severity + fixability + string/comment masking flags + optional guard). Adding a detector is ~30 lines plus a test and a labeled bench case — `tests/test_bench.py` enforces 100% recall on the corpus and **zero** false positives on clean files.

## Development

```bash
pip install -e ".[dev]"
pytest                            # 275 tests
PYTHONPATH=src python -m bench.run  # calibration: recall + clean-FP metrics
PYTHONPATH=src python scripts/shots.py  # regenerate the README screenshots
```

Stack: Python ≥ 3.11, [Textual](https://textual.textualize.io/) ≥ 0.80.

## License

[MIT](LICENSE) © mertsoylu
