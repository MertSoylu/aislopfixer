# aislopfixer — Design Spec

**Date:** 2026-06-13
**Status:** Approved

## Summary

`aislopfixer` is a terminal TUI tool that scans local web project source folders
(React/HTML/Vue/Svelte/Astro/etc.) for AI-generated "slop" — placeholder junk,
AI self-reference leaks, generic buzzword filler, duplicate content, and
accessibility/meta defects — using **offline rule-based detection** (no network,
no LLM API). It presents findings in a heavily animated, high-design TUI, then
drives **interactive fixes** (auto / prompt / skip) with file backups.

Goals: top-tier visual design and animation; high performance (fast scan, smooth
60fps-feel UI); fully offline and deterministic.

## Decisions (locked)

| Topic | Decision |
|-------|----------|
| Input | Local source folder; all web languages via raw-text + lightweight tag scan |
| Detection | Heuristic/rules only — offline, deterministic, no API |
| Action | Report + interactive fix |
| Stack | Python 3.11+, Textual (+ bundled Rich) |
| Slop categories | AI leaks; placeholders/dummy/dead-links; buzzwords; duplicates + a11y/meta |
| Fix mechanics | Mix: auto-fix clear junk, prompt for real values, skip unsafe |
| Export | TUI only (no report files) |
| Rule engine | Pluggable rule registry (self-registering rule classes) |
| Backups | ON by default — `<file>.aislopfixer.bak` before first edit per file |

## Architecture

### Components

1. **CLI entry** (`cli.py`, `__main__.py`) — `aislopfixer [path]`. Path optional;
   TUI prompts if omitted. Parses args, launches Textual app.

2. **File walker** (`scanner.py`) — recursive walk. Ignores `node_modules`, `.git`,
   `dist`, `build`, `.next`, `out`, `vendor`, `.cache`, `coverage`. Selects text
   files by extension: `.html .htm .jsx .tsx .js .ts .vue .svelte .astro .md .mdx .css`.
   Reads UTF-8 text; binary/unreadable files skipped and counted. Yields
   `SourceFile{path, text, rel_path}`.

3. **Rule engine** (`engine/`):
   - `registry.py` — decorator-based self-registration; collects all rules.
   - `models.py` — `Finding`, `FixAction`, `Severity`, `Category`, `Fixability`.
   - `rules/`:
     - `ai_leaks.py` — regex phrase list: "As an AI language model", "Certainly!
       Here is", "I hope this helps", "As of my last knowledge update",
       "I cannot", "I'm sorry, but", "Feel free to", "I'm just an AI", etc.
     - `placeholders.py` — lorem ipsum, `[Your Company Name]`/`[Insert ...]`,
       `example.com`, dummy emails (`john@example.com`), dummy phones
       (`+1234567890`, `555-...`), `TODO`/`FIXME`, placeholder image hosts
       (`via.placeholder.com`, `picsum.photos`, `placehold.it`), dead links
       (`href="#"`, empty href, `javascript:void(0)` used as nav), `John Doe`.
     - `buzzwords.py` — phrase list + density score: "cutting-edge", "seamless",
       "revolutionize", "in today's fast-paced world", "unlock the power of",
       "take it to the next level", "game-changer", "leverage", "synergy",
       "elevate your", "best-in-class". Flags individual hits + high-density blocks.
     - `duplicates.py` — split text into normalized blocks (paragraphs / JSX text
       nodes), hash, report blocks repeated within/across files above a length
       threshold.
     - `accessibility.py` — lightweight tag scan: `<img>` missing `alt` or
       `alt="image"`/`alt="img"`; missing/generic `<meta name="description">`;
       missing `<title>`; empty headings (`<h1></h1>`).
   - Detection operates on **raw text + regex/tag matching only** — no
     per-framework AST. Keeps multi-language support simple and fast.

4. **Finding model** — fields: `file`, `line`, `col`, `category`, `severity`
   (`info|warning|error`), `rule_id`, `message`, `snippet` (surrounding source),
   `suggested_fix` (text or description), `fixability` (`auto|prompt|manual`).

5. **Fixer** (`fixer.py`) — applies a `FixAction` to file text:
   - `auto` — delete/replace the flagged span (clear junk: AI leaks, lorem ipsum).
   - `prompt` — UI collects a replacement value; substitute into span.
   - `manual`/skip — no-op (record as skipped).
   - **Safety:** before first write to a file, copy to `<file>.aislopfixer.bak`.
     Computes and surfaces a unified-diff preview prior to applying. Line/col
     offsets recomputed after each edit to keep multi-fix-per-file correct.

6. **TUI app** (`app.py`, `screens/`, `widgets/`, `styles.tcss`):

   **Screen flow:**
   - **Splash** — animated ASCII logo, typewriter + glow/gradient reveal; auto
     advance or any-key.
   - **Path** — target folder input (prefilled from CLI arg), live validation.
   - **Scan** — spinner, live progress bar (files done/total), rolling
     current-file line, animated per-category finding counters, ambient
     "radar/wave" pulse. Scan runs in a worker so UI stays responsive.
   - **Results** — findings grouped by category & file; severity color-coded;
     count-up counters; selecting a finding opens a detail pane (code snippet +
     suggested fix).
   - **Fix** — per finding: `[F]ix / [S]kip / [A]nnotate`; modal value-prompt when
     needed; diff preview; animated success check. Batch "fix all auto" action.
   - **Summary** — animated stats: found / fixed / skipped; per-category bars.

   **Animation/design language:** gradient accent palette, smooth screen
   transitions (Textual CSS), reactive count-up counters, pulsing/scan effects,
   success checkmark flourishes, consistent spacing and a strong typographic
   header. Target a polished, "premium" feel.

### Data flow

```
path → walker → engine (all rules per file) → Findings
     → Results screen → user fix actions → fixer (backup + write) → Summary
```

### Performance

- Scan runs off the UI thread (Textual worker / thread) — UI never blocks.
- Rules compiled once (precompiled regex); single pass over each file's text
  where possible.
- Findings streamed to the UI incrementally (counters update live) rather than
  one big post-scan dump.
- Large-file guard: skip files over a size cap (configurable, default ~2 MB).

### Error handling

- Invalid/missing path → error screen with retry.
- Unreadable/binary files → skipped, counted, shown in summary.
- Zero findings → celebratory "clean" empty state.
- Fix write failure → non-blocking toast; backup retained; finding stays open.

## Testing (pytest)

- **Rules** — per-rule unit tests: slop snippet input → expected `Finding`(s);
  clean input → none. Covers each category.
- **Fixer** — apply auto/prompt fixes → expected output text; backup file created;
  multi-fix offset correctness.
- **Walker** — ignore-dir and extension filtering; binary skip.
- **TUI** — Textual `pilot` tests for screen flow (splash→path→scan→results) and
  key bindings; light coverage.

## Project layout

```
aislopfixer/
  pyproject.toml
  README.md
  src/aislopfixer/
    __init__.py
    __main__.py
    cli.py
    app.py
    styles.tcss
    scanner.py
    fixer.py
    screens/
      __init__.py
      splash.py
      path.py
      scan.py
      results.py
      summary.py
    widgets/
      __init__.py
      counter.py        # animated count-up counter
      finding_tree.py   # grouped findings tree
      diff_view.py      # unified-diff preview
      logo.py           # animated ASCII logo
    engine/
      __init__.py
      registry.py
      models.py
      rules/
        __init__.py
        ai_leaks.py
        placeholders.py
        buzzwords.py
        duplicates.py
        accessibility.py
  tests/
    test_rules_*.py
    test_fixer.py
    test_scanner.py
    test_tui.py
```

## Out of scope (YAGNI)

- Live URL crawling / network fetch.
- LLM/API-based factual checking.
- Report file export (MD/JSON).
- Per-framework AST parsing.
- Config file / custom rule authoring UI (registry is code-level for now).
