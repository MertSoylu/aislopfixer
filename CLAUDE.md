# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A terminal TUI (Python + [Textual](https://textual.textualize.io/)) that answers
one question about a local web project: **how many independent design decisions
does it contain, and how much of it is a copy of itself?** It then derives a
project-specific design system and rewrites the source onto it. Fully offline,
deterministic, no API keys.

The real application lives in **`src/aislopfixer/` (Python)**; `bin/cli.js` is
only an npm launcher that builds a private venv under `~/.aislopfixer/venv-<version>/`
and `exec`s `python -m aislopfixer`. When developing, ignore the launcher.

**This is not a linter.** It does not detect typos, security holes, hallucinated
imports or broken code — ESLint and friends already do that, and v1.0 deleted
those rules on purpose. It detects *design* slop: the template that current
models converge on even when every individual line is correct.

## Commands

```bash
pip install -e ".[dev]"                  # dev install (textual + pytest + pytest-asyncio)
aislopfixer ./bench/cases/slop_saas      # run the TUI against a corpus case
aislopfixer ./monorepo --pages "app/(x)"  # measure one site inside a repo
python -m aislopfixer <dir>              # module form (same thing)
pytest                                   # full suite (185 tests)
pytest tests/test_measure.py -k rhythm    # one file / one test
python -m bench.run                      # calibration table + separation margin
python -m bench.field                    # clone 15 public repos, write bench/field.md
python -m bench.field --no-fetch         # re-scan the clone cache only
python -m bench.field --transform        # also build/check a patch per repo
python -m bench.impact                   # predicted vs actual drop, writes bench/impact.md
node scripts/clean.mjs                   # strip __pycache__/*.pyc (npm prepack)
```

`bench.field` is the open circuit: the corpus can only prove the measurement is
*consistent*, because we wrote every page in it. It clones into
`~/.cache/aislopfixer-field` (never into the repo) and writes the table with its
own failures listed. It is a calibration table, not a gate.

pytest config lives in `pyproject.toml`: `asyncio_mode = "auto"`,
`testpaths = ["tests"]`, `pythonpath = ["src"]`. Tests run from the repo root
without installing; `aislopfixer` on the PATH requires `pip install -e .` first.
TUI tests use Textual's async pilot driver.

## The central idea

A generated landing page uses a *large number of classes* drawn from a *tiny
number of decisions*:

```html
<section class="py-20 bg-white">
  <div class="max-w-7xl mx-auto px-4 text-center">
    <h2 class="text-4xl font-bold text-gray-900 mb-4">Features</h2>
```

Seven classes, roughly one and a half decisions — every value is one the
framework already chose. No token in that block is forbidden; the slop is in
the *distribution*. That is why the engine counts distributions, not matches.

**Two headline axes**, and both are needed:

* **Decision density** — what share of the project's own vocabulary was
  *chosen* rather than taken from the framework. Normalized against the
  observed vocabulary, never against page size: see "The target is the
  vocabulary, not the page" below.
* **Repetition** — how much of the project is a copy of itself.

Repetition alone cannot be the score: a real design system repeats on purpose.
Decision density alone cannot be it either: a small, plain, honest page has few
decisions and is not a template. `template_score = (100 − decisions) × (0.55 +
0.45 × repetition)` plus a small capped bonus for the template's own signature
tells (`analyze.TEMPLATE_TELLS`).

## Architecture

Pipeline: **parse → measure → derive a system → plan → preview → apply → re-measure.**

```
src/aislopfixer/
├── cli.py / __main__.py   # argparse → TUI. No headless mode by design.
├── app.py                 # Textual App; owns report, docs, system, undo state
├── scanner.py             # walk dir → SourceFile (ext/ignore/size/minified filter)
├── config.py              # .aislopfixer.toml: ignore globs, disabled observations,
│                          #   `pages` (the site inside a repo — see design/scope.py)
├── store.py               # .aislopfixer/{state.json, report.md}
├── theme.py / styles.tcss # colors/icons + Textual CSS
├── editor.py              # resolve $EDITOR/code and open a file:line position
├── screens/               # splash → path → scan → report → system → summary
├── widgets/               # animations, counters, logo, guard (too-small overlay)
└── design/
    ├── models.py          # Axis, Origin, Decl, Element, Document, Observation,
    │                      #   AxisScore, DesignReport
    ├── parse/
    │   ├── markup.py      # tolerant HTML/JSX/Vue/Svelte/Astro/MDX element scanner
    │   ├── expr.py        # class expressions: evaluate, and where they may be edited
    │   ├── classes.py     # Tailwind class → (axis, prop, value, origin)
    │   ├── css.py         # CSS → rules, custom props; shipped values → their keys
    │   ├── theme.py       # tailwind.config / @theme → the keys the project redefined
    │   ├── styles.py      # CSS Modules (styles.card) and CSS-in-JS (styled.div`…`)
    │   ├── components.py  # component definitions (JSX functions and SFC files)
    │   └── lexer.py       # string/comment masking (was engine/context.py)
    ├── render.py          # authored tree → the tree the browser actually gets
    ├── metrics/           # vocabulary · rhythm · layout · repetition · palette ·
    │                      #   content · tells · states · contrast · sections · util
    ├── analyze.py         # combine metrics → DesignReport
    ├── scope.py           # root vs scope: which site inside a repo is measured
    ├── system/            # archetypes · derive · color · emit · preview
    ├── transform/         # classmap · plan · apply · wire · verify
    ├── project.py         # load_documents / scan_project / apply_config
    └── brief.py           # report → markdown brief for a coding agent
```

### Two trees, and which metric reads which

`render.render_documents` builds a second, **virtual** tree per page: component
usages are replaced by what they render, `{children}`/`<slot>` is spliced in at
the hole, and a loop over an array whose length can be *read from the source*
(`items.map`, `v-for`, `{#each}`) repeats its child that many times.

* **Rendered tree** — rhythm, layout, repetition, contrast, and the size the
  decision target is scaled against. A page that puts eighty elements on screen
  is a page of that size whether it wrote them once or eight times.
* **Authored tree** — vocabulary (decision density), palette, copy, state
  coverage. Writing `py-20` once inside a wrapper is *one decision* however many
  bands it produces, and a `dark:` written once covers every render.

That split is what closes the component blind spot: `slop_saas`, `slop_react`
and `slop_vue` are the same design in three stacks and now land within 1.2
points of each other. `bench/cases.py` pins that with `twin_of` / `TWIN_MARGIN`
— a componentised template that scores *better* than its copy-pasted twin is a
hole in the measurement, not a better page.

Nothing in the expansion guesses: an unreadable array repeats once, an unknown
component is emitted as-is, and recursion/nesting/array length are capped so
hitting a cap **under**-reports.

### Class expressions are evaluated, not scraped

`parse/expr.py` reads `className={…}`, Vue's `:class`, and Svelte's `class:`
directives. With no bindings it returns the union of every branch; given the
props a component was called with, a decidable condition collapses to the
branch that renders. Two rules keep it honest:

* a token welded to an interpolation (`` `py-${n}` ``) yields **nothing** — a
  partial token is not a class;
* a condition's operand (`tone === "muted"`) is not a class either.

The same module tells the transformer *where* it may write: `rewritable()`
returns the plain-text spans (string bodies, whole tokens of a template's
static text) and counts what it had to leave alone; `conditional_regions()`
marks the parts that only render under a condition, so a class the element
*gains* never lands inside a branch.

`Element.classes` is everything that reaches the element; `Element.attr_classes`
is only what the rewritable attribute itself says. The transform uses the
latter — copying a `class:active` directive's name into the static list would
turn a conditional class into a permanent one.

### Origin is what separates a decision from a default

`design/parse/classes.py` decodes every utility into a `Decl` carrying an
`Origin`:

| Origin | Example | Weight | Meaning |
|---|---|---:|---|
| `DEFAULT` | `py-20`, `text-xl`, `bg-gray-100` | 0.25 | the framework chose |
| `LITERAL` | a raw CSS value in a stylesheet | 1.0 | someone typed it |
| `ARBITRARY` | `text-[2.75rem]`, `bg-(--brand)` | 1.0 | someone looked at the screen |
| `TOKEN` | `bg-surface`, `rounded-panel` | 1.5 | someone built a system |

**Unknown utilities are dropped, never guessed at.** A wrong axis moves a score
for a reason nobody can verify.

Two decoding traps, both regression-tested:

* `text-` is three utilities wearing one prefix (size / colour / alignment).
  `_decode_text` disambiguates; a colour handler that claimed `text-4xl` would
  stop the type mapping from ever seeing it.
* Side and corner selectors are part of the utility *name*, not its value.
  `border-b` once decoded as border-width `"b"` — an unknown value, therefore a
  project `TOKEN` — which credited every page that draws a hairline with having
  built a design system. See `BARE` and the `rounded-<corner>-` prefixes.

### The project's own config decides what "default" means

`parse/theme.py` reads `tailwind.config.{js,ts,mjs,cjs}` and v4 `@theme` blocks
and records the scale keys the project **redefined**. `decode_class` then marks
those keys `TOKEN` instead of `DEFAULT` — key by key, so a project that wrote
its own `fontSize.lg` gets credit for `text-lg` while `text-4xl` beside it is
still a default. Without it the tool was hardest on the most careful projects:
`bench/cases/clean_config` scores 47.8 on typography blind and 100 with the
config read, and every type class on that page is a name Tailwind also ships.

The config is loaded once in `project.load_documents` from the same in-memory
pass that reads everything else, carried on `Document.theme`, and folded into
`decode_class`'s cache key. A project-blind cache would hand one project's
decisions to the next one scanned in the same process.

### Two dialects, one vocabulary

A generated page written in raw CSS is the same generated page. `parse/css.py`
therefore normalizes a literal onto the utility it equals: `padding: 5rem 0`
becomes `padding-y=20` with `Origin.DEFAULT`, `#4f46e5` becomes `indigo-600`,
`repeat(3, 1fr)` becomes `3`, `text-align: center` becomes `text-center`. Only
*exact* matches convert — `max-width: 1200px` is not `80rem`, so it stays
authored. `classes.STOCK_HEX` is deliberately partial and says so: a miss
under-credits the framework, a wrong entry would accuse a project.

Symmetry has to run both ways, and the clean-side twin pair (`clean_utility` /
`clean_css` — the same design in utilities and in raw CSS) is what proved it did
not. Three holes, all closed, all worth 8 points between two halves of one page:

* `py-[2.5rem]` is `py-10`. The stylesheet path always converted a shipped value
  to its key and `DEFAULT`; the utility path never did, so the same value was a
  decision in a class list and a default in CSS. `classes._shipped` now runs the
  escape hatch through the *same* `css.stock_key`. What the hatch is for
  survives: `text-[2.75rem]` matches no step and stays `ARBITRARY`.
* `padding-top: 2.5rem; padding-bottom: 2.5rem` is `py-[2.5rem]` — one decision
  written twice. `css.rule_decls` folds the pairs in `_AXIS_PAIRS` when the two
  values are **equal**, and the joint name is a CSS property `_PROP_MAP` knows
  (`padding-block`, not `padding-y`): an invented prop matches nothing and
  silently deletes the declaration.
* An **external** stylesheet reached no element at all. Only same-file `<style>`
  blocks were indexed, so a plain HTML page with a `site.css` measured as a page
  with no declarations — every structural metric reading an unstyled document.
  `parse.resolve_stylesheets` is the cross-file pass, with the same
  single-class-selector approximation and for the same reason.

`parse/styles.py` closes the other half of React: `styles.card` is followed
through its import to the `.module.css` rule, and `` styled.div`…` `` is read as
a component definition with a known tag and known declarations, which
`components.resolve` then wires to every usage. What cannot be read — a value
behind `${…}`, an import that resolves to no file — is **counted** and reaches
`DesignReport.notes`, the report screen and the brief. `slop_styled` scores
within 0.6 points of its HTML twin; before this it measured as eleven empty tags.

### The target is the vocabulary, not the page

`vocabulary.score_axes` scores an axis as `weighted decisions / (VOCAB_TARGET ×
distinct entries)`. That ratio has the same meaning at forty elements and at ten
thousand, which is the whole point: an earlier version scaled the target by
element count and **saturated it at 120 elements**, so any project bigger than a
demo page scored itself designed simply by using more defaults. `bench/field.md`
recorded the cost — eight landing-page templates, all eight graded "designed".

Two consequences worth stating:

* **Using more of the framework never helps.** A project with 250 stock spacing
  values has 250 entries and 250 × 0.25 of weight; its score is the same as a
  project with 12. Volume is not evidence.
* **A redefined scale is one decision, not N** (`vocabulary.decision_group`).
  Ten shades of `--color-brand-*`, or a `fontSize` scale rewritten key by key,
  fold into a single entry worth `TOKEN + log(n)` — more than one value, because
  a considered ramp *is* more work, and far less than ten. Both sides of the
  ratio fold, so a project that builds a ramp is neither credited ten times nor
  asked to clear a target ten times larger. Every landing kit ships a config;
  without this, shipping one bought a full axis.

`AXIS_FLOOR` is the only absolute in the formula, and it exists so three
authored values do not read as a type system.

### Structural decisions count even when every value is a default

`vocabulary.structural_decisions()` adds weight for things no value table can
see: band variety, container variety, split gaps, grid-count variety, column
asymmetry, a container break, alignment variety. Without them a careful page
built entirely from stock utilities scored the same as a generated one — and
those are exactly the properties the repetition metrics punish the absence of,
so the two axes stay symmetric.

Each bonus is a **share of the axis goal**, capped, never an absolute count —
for the same reason the goal itself is a ratio. Four distinct band rhythms is
variety on a five-band page and monotony on a forty-band site, and a count-based
bonus put every large repository at the cap, designed and generated alike.
`_variety` reads a *system* rather than entropy: `breadth` against
`ENOUGH = 3` (three band rhythms is what the prescription asks for, so a
five-band page using three is finished, not 60% finished) times `spread`
(1 − dominant share, so three hundred identical grids and six stragglers is not
a system of grids).

### Where a structure signal has to be about the band

Two bugs of the same shape, both fixed and both worth not repeating:
`w-full` is not a container break — it means "fill your parent", which nearly
every block element already does, and counting it gave `nuxt-website` 3478
escapes. And a break made *inside a card* is not a statement about the page's
column, so `layout.band_breaks` only looks within reach of a band.

### An unused axis is excluded, not scored zero

`AxisScore.measured` is False when a project never touches that axis. A page
with no shadows and no animation has not *failed* material and motion, it has
declined them, and restraint is not slop. Both headline means skip unmeasured
axes (`analyze.analyze` → `live`).

### Provenance is not repetition

`palette.analyze` deliberately does **not** feed stock-palette share into the
repetition score. Using the shipped ramp already costs the project on decision
density; counting it twice made a plain hand-written page read as repetitive as
a generated one. Repetition on the colour axis means hue collapse only.

### Repetition must cross a boundary to count

Three identical cards side by side are a list, not slop — a design system is
supposed to repeat. `repetition.clusters` only reports a shape used across
multiple **sections** or multiple files. The boundary is the section, not the
parent: four catalogue entries in one grid have four different parent wrappers
and are still a list, while the same shape serving as a feature, a price *and*
a quote is a crossing between bands. Page-skeleton similarity and canonical
section order (`metrics/sections.py`) are measured separately, and the section
classifier checks for an `h1` *before* the feature vocabulary, because a
generated hero almost always says "Everything you need to …".

A band is also the **outermost** stripe: once one is found, nothing inside it is
another one (`Document.sections`). Without that, an `<article>` card in a grid
read as a peer of the band containing it. That rule needs a second half: when
the grid's wrapper is a plain `<div>` there is no enclosing band to hide behind,
so a run of three or more sibling `<article>`s is dropped as a list
(`Document._drop_lists`). Nine testimonial cards were arriving as nine top-level
bands, and the page's skeleton read `features → content`.

### A route is a layout plus a page

Next.js App Router splits one page across two files that do not import each
other: the nav and footer live in `layout.tsx`, the bands in `page.tsx`. Read
separately, the canonical sequence hero → features → testimonials → cta → footer
never appears in one document, and the tool's strongest structural tell went
silent on exactly the projects it was written for. `sections.routes` resolves the
pairing the way the framework does — every `layout.*` from the scan root down to
the page's own directory — and returns **two** role lists per route:

* the *composed* one, chrome included, for canonical order: nav → hero → … →
  footer is the shape;
* the *page's own* one for page-to-page similarity, because every route in an
  App Router project shares one layout by construction and comparing the
  composed lists reported two unrelated pages as 91% the same page.

`{children}` is found by the **last** match past the first element — a
`function Layout({ children })` parameter is a destructuring pattern, not the
hole, and matching it first put the whole layout after the page.

### A coverage measure only speaks about a claim

`metrics/states.py` reports a *half-finished* dark mode and *uneven* focus
styling, never their absence. A project with no `dark:` anywhere has declined
the mode, and declining is a decision — the same rule that keeps an unused axis
out of the headline scores. Both measures also stand down when the stylesheet
does the work (`.dark`, `:focus-visible`), because counting utilities in that
project would measure the authoring style rather than the design.

`metrics/contrast.py` follows the same discipline from the other side: authored
colours are compared exactly, neutral framework shades through the ramp's own
luminance curve, and **everything else is skipped** — a chromatic pair, a
mixture of the two, or text with nothing declared underneath it. An
unverifiable accessibility claim is worse than none.

### A band nobody can name still has a shape

`sections.classify` is content-first, and when no vocabulary matched it returned
`content`. On a studio site that was two thirds of the bands. `STRUCTURAL` adds
five names read off the band's *shape* rather than its place in the landing
sequence — `gallery`, `list`, `statement`, `prose`, `contact` — from counts the
`Shape` dataclass takes once per band: media, text blocks, forms, links,
headings, equal sibling blocks, words.

They sit deliberately **outside** `CANONICAL`, so naming one neither extends the
template run nor breaks it — exactly the transparency `content` already had.
What they buy is everything else: a band the classifier can name gets its own
rhythm token in `classmap.BAND_FOR_ROLE` instead of the catch-all, and
`repetition._comparable` compares only *canonical* roles, so three pages that
are each hero → statement → list share a house style rather than a template.

The vocabularies are Turkish as well as English. A tool whose interface is
Turkish measuring only English pages is a blind spot with a flag on it, and
`bench/cases/slop_tr` pins it: the same generated template, every band named,
the full canonical sequence.

### The derived system

`design/system/` replaces a default with something that is not itself a
default. Six hand-written archetypes (`archetypes.py`) each take a position on
type, rhythm, edges, depth and alignment that the others do not.

* Selection is seeded from the project's identity (directory + package name,
  CRC32, avalanched before the modulo — a plain `seed % 6` gave sibling
  directories the same archetype). **Same project → same system, every run.**
* A project's own authored hue wins over the seed; a shipped `indigo-600` does
  not, because that is the thing being replaced.
* `neutral_hue` is **absolute, not an offset from the accent** — a relative
  neutral followed the accent around the wheel and turned Terminal's cool slate
  paper pink.
* Ramps are specified in **chroma, not saturation** (`color.py`). HSL
  saturation means less and less toward either lightness extreme, so a
  saturation-specified ramp loses its tint exactly where the largest areas of a
  page live. `_saturation_for` solves for the saturation that yields the target
  chroma.
* `emit.py` writes the tokens twice — inside `@theme` (Tailwind v4) and inside
  `:root` (plain CSS / v3) — so the file is correct without the tool having to
  be right about the stack.

### The transform

**Hard constraint: only class lists change. The element tree is never
touched.** No tags added, removed, wrapped or reordered. That is why the
transform is safe to run unattended: a class list is a string, so the output
always parses and the worst failure is a page that looks wrong, not a build
that does not run. Every layout change — including the full-bleed break and the
asymmetric grid — is expressed in classes an existing element can carry.

Other invariants:

* Elements whose class attribute is an **expression** (`className={cn(…)}`) are
  skipped *and counted*, never silently ignored.
* Edits apply **right to left** within a file so earlier offsets stay valid, and
  refuse to write when the span no longer matches (`apply_edits`).
* Files are read LF-normalised (matching parser offsets) and written back with
  their **original line endings and BOM** — a bare `write_text` would convert a
  repository to CRLF on Windows.
* One `.aislopfixer.bak` per file, plus an in-memory snapshot for `u`.
* The transform is **idempotent**: a second pass produces zero edits. Tested.
* Grid columns are dropped and re-added by `_additions` rather than replaced in
  place, because the rewriter re-applies the *original* variant to a handler's
  return value — which turned `md:grid-cols-3` into `md:md:grid-cols-12`.
* The plan takes an **axis filter** and the system screen exposes it (keys
  `1`–`5`, `0` for all). A colour-only plan produces nothing but `token` edits
  and a second pass produces zero. Applied axes are remembered in `state.json`,
  so the next run opens on the work that is left; `u` clears that.
* `d` writes the whole plan to `.aislopfixer/plan.diff` **without applying it**,
  from the same `Plan` and the same `apply_edits` as the write. It is a
  `git apply`-clean patch (tested against real `git`), and the token file is not
  in it — only `a` creates that.

### Where the transform stops, it says so

The class-only constraint has a cost, and the tool has to name it rather than
let the user find it in a diff. `rhythm.shared_band_wrappers` reports
`space.shared_band_wrapper`: one `<Section>` wrapping six bands that serve six
roles means the rhythm fix lands once and every band gets the same value. It
reads the **authored** tree (the usages are what carry the roles), fires on
`slop_react` / `slop_vue` / `slop_styled` and stays silent on `slop_saas`, and
`brief.py` gives it its own heading — "the tool will never do this" and "the
tool has not done this yet" are different sentences.

### How much of the project the score covers

`DesignReport.coverage` (`models.Coverage`) reports how far the numbers reach:
markup files read, routes found, elements authored and rendered, and a census of
everything walked and *not* read, split by *why*: pages in a markup language
this tool does not parse (`.erb`, `.njk`, `.liquid`, Jekyll templates), **prose
pages** (`.md`) counted and deliberately not scanned, bundles, and **compiled
framework stylesheets**. The two page kinds are separate because they are not
the same gap — an unread `.erb` page has design in it the tool cannot see, an
unread `.md` page has none: the theme that renders it does, and that theme is
source the scan reads. Only the first kind drags confidence down. `.mdx` is
neither; its body is JSX and it is read like any other markup file, with the
markdown half (fenced code, autolinks) masked length-preservingly first.

A dot-directory is *not* automatically build output. `.vitepress/theme` holds a
whole site's design, and skipping it read `hono-website` as four markup files
with 42 elements — then blamed the gap on its `.md` pages.
`scanner.SOURCE_DOT_DIRS` is the short allowlist; the build cache *inside* those
is refused by `NESTED_IGNORE_DIRS`.

`landwind/output.css` is 49 KB of generated Tailwind, and reading it gave that
repository 154 colour values and 77 "tokens" nobody wrote; the scanner skips a
stylesheet that declares Tailwind's own `--tw-*` runtime properties or carries
its banner, and says so.

`analyze` also reports how far the *section classifier* reached — "12 bandın
7'si adlandırılamadı" — when it named under 70% of the bands. Not a verdict:
a page of bands nobody can name is usually a page that is not a template. It is
the width of the lens, so a reader can discount the structural half when the
lens is narrow.

Confidence is `tam` / `kısmi` / `yok`. `kısmi` means the scan never read a page
end to end while the repository has pages in a foreign language — a docs site
measured on its components. The score is still shown, and `DesignReport.verdict`
says out loud that it is about the fragment. A scan that saw nothing still
withholds the number entirely (`DesignReport.measured`).

Scanning `_layouts/` is deliberately **not** skipped: a Jekyll layout is HTML
with Liquid in it and the markup scanner reads it. Excluding the directory took
`tholman` from 65 elements to 1 — a scan that stopped seeing the site in order
to be tidy about where the site lives.

### What to fix first

`analyze.priorities` orders the work by how far closing each observation is
projected to move the template score, computed by re-running the *same* formula
(`_score_from`) rather than a second one that could drift. Two modelling choices
are stated in the docstring, not hidden: closing a `*.no_decisions` observation
means that axis reaching `DESIGNED_AT`, and closing anything else removes its
share of its axis's repetition. An axis-level entry is dropped when the axis
already has a concrete observation — the same job at two altitudes. `⚡` marks
what the transform closes by itself (`analyze.SELF_FIXABLE`) **and can reach**:
on a project with no class attribute anywhere the transform produces zero edits,
so the mark is withheld (`DesignReport.rewritable`). `bench.impact` caught the
tool promising a 165-point drop on `slop_styled`, whose score does not move at
all.

### Checking the transform's output, not just that it ran

`git apply`-clean and idempotent say nothing about whether the page got better,
and the tool's whole argument is the second claim. `transform/verify.py` holds
the two halves of it that can be checked at repository scale:

* `class_only` — **byte level**. Class values are masked and the rest of the
  file is compared before and after: element tree, text, whitespace, line
  endings. The constraint was in `classmap`'s docstring and had never been
  checked on anything bigger than a fixture, while `daisyui` takes 1 784 edits
  in one run. Wiring edits (`Edit.wiring`) are *excluded*, not tolerated — an
  invariant with a carve-out inside it proves nothing.
* `nonsense` — **semantic**. The same class twice, a variant that repeats the
  base it overrides, two values fighting on one property.

The second one found two real defects rather than just counting them, and
`classmap.resolve` now fixes both: an installed token wins the property it was
put there to take (`tracking-display` beats the `tracking-tight` it replaced),
and a variant whose value equals its base is dropped (`text-blue-600
dark:text-blue-400` both map to the accent role — 23 no-ops on `landwind`).
Inside a `className={…}` expression the resolution is **not** run across
conditional spans: `cn(reverse ? "lg:order-2" : "lg:order-1")` is one decision
written twice, and resolving the branches against each other emptied one.

Fixing that exposed a third: the full-bleed candidate is found by its `w-full`,
which the rewrite then drops as a conflict — so each pass bled one more band.
`plan._bleed_candidate` returns an already-bleeding element rather than none, so
"one break per page" holds across runs and its `max-w-none` stops flip-flopping.

`bench.field --transform` reports before/after **measured** score per repo, the
invariant, and the leftover nonsense count. A repo whose score does not fall
stays in the table with the number that says so.

### Forecast the transform by running it, not by modelling it

`transform.preview` builds the same plan, applies the same edits **in memory**
and re-measures with the same pipeline — so the number the system screen shows
above `a` is the number the next scan will report, not a projection of it.
`bench/impact.md` pins that at zero difference on all seventeen corpus cases.

It replaced a model that was wrong by half. The ordering model
(`analyze.projected_score`) is still there and still answers its own question —
what a *person* closing one observation gets, which is why it assumes
`DESIGNED_AT` — and `bench/impact.md` keeps both columns so the gap between them
stays visible instead of being tuned away. The per-item drop is a **floor**.

`preview` must run the *same* resolution steps as `project.load_documents`, in
the same order. A step missing there is a preview promising a score the next
scan cannot produce — `bench/impact.md` caught `resolve_stylesheets` missing as
a 0.7-point drift on `clean_css`.

And where the measured gain is small the tool now declines to recommend itself:
the system screen offers `a` **disarmed** below `screens.system._WORTH_AT`
points, so the first press states the cost and the second one writes. On
`clean_config` the whole plan moves the score *up*; on `nuxt-website` it is 453
edits for 1.4 points. A warning printed beside a one-key write is not an offer
anybody can decline.

The preview deliberately does not count the emitted token file: it lands under
`.aislopfixer/`, which the scanner skips like every dot directory, so a preview
that counted it would promise a score the next run cannot produce. It also
reveals something worth showing the user before they press `a` — on a project
that already has a system, the tool's own is narrower and the score goes **up**.
The screen says so.

## Adding a metric (the common task)

1. Add a module in `design/metrics/` exposing `analyze(docs)` that returns
   observations plus its axis repetition contribution. Metrics never mutate
   documents and never talk to each other.
2. Wire it into `design/analyze.py`, and decide **which tree** it reads: the
   rendered one for anything structural, the authored one for anything that
   counts what a person wrote. Getting this backwards is the single easiest way
   to make a componentised project measure as a small one.
3. Every observation needs: a stable `id`, a `stat` (the measured number), a
   `detail` that says what was measured and why it matters, evidence with real
   file/line positions, and a `prescription`. **An observation with no
   prescription is noise** — `brief.py` drops it.
4. Add a labeled case to `bench/cases/` and its band to `bench/cases.py`.
   **Write the clean twin too**: the closest legitimate hand-made page that
   must stay silent. A metric that cannot separate its slop case from its clean
   twin is not a detector. Set `family="probe"` for a case that exists to pin
   one observation, so it stays out of the separation margin. `twin_of` links a
   pair that must land within `TWIN_MARGIN`; the clean side has one too
   (`clean_utility` / `clean_css`), and it is what caught the utility and CSS
   dialects scoring the same design differently.
5. If it is a signature tell of the template, add its id to
   `analyze.TEMPLATE_TELLS`.
6. If the measure has a cap or a sample limit, **report it** in the observation
   text. A silent truncation reads as "I looked at everything".

## Release checklist

1. Bump `version` in **`package.json`**, **`pyproject.toml`** and
   **`src/aislopfixer/__init__.py`** (all three must match).
2. Update the "Güncel sürüm" line in **`README.md`**.
3. `npm publish` and/or `git tag v<version> && git push --tags`.

## Notes

- The UI is Turkish; code, identifiers and comments are English.
- `bench/cases/mid_human_tailwind` is the corpus's most important case: a real
  person's page built from nothing but Tailwind defaults. It must land in the
  middle. A change that pushes it up is a false positive even if every other
  case still passes.
- Reading files is the largest cost of a scan on a real repository, so
  `scanner.iter_files` reads them on a thread pool while keeping the walk's
  order — a scan whose output depends on disk timing cannot be diffed between
  runs. `decode_class` is `lru_cache`d for the same reason: a project draws
  thousands of class *uses* from a few hundred class *names*. A 1000-file
  Next.js-shaped repo scans in ~1.3 s; `tests/test_measure.py` fails the build
  above six. Three things keep it there and each was a real regression:
  `render_documents` does not expand a single-file component that lives under a
  `components/` directory (its pages already contain it, expanded, with the
  props they passed — on `nuxt-website` that was eighteen documents hitting the
  4 000-element cap); a file's `.map`/`{#each}` loops are found **once per
  document** rather than once per element, because a page's root element is the
  whole file; and `Document.sections` is cached on first read — it is pure over
  the element tree and every structural metric asks for it. That cache is reset
  in `render.render_documents`' `replace(...)`, since the rendered document has
  a different tree.
- Failure and empty states are deliberate: a crashed scan **stays on
  `ScanScreen`** with retry/new-folder/quit, because falling through to an
  empty — therefore clean-looking — report is a lie about the project. Same
  rule one level down: `DesignReport.measured` is False when the scan found no
  elements, and then `template_score` is **withheld** (0.0) with a verdict that
  says so. Zero decisions and zero repetition is what an *empty* measurement
  looks like, and the formula reads that as 55/100.
- **`bench/field.md` has three sides, not two.** All fifteen public
  repositories land right, up from six. The third side, `crafted`, exists
  because two of them — Cruip's commercial templates — kept measuring as
  designed and *are* designed: a `@theme` ramp with per-step leading, authored
  easing curves, full-bleed bands. What makes them templates is how many sites
  will **be** them, which is not a property of the source and not something this
  tool can measure. `bench/cases/crafted_kit` pins where such a page belongs and
  `field.py` reads that band from the corpus rather than restating a threshold,
  so the two cannot drift. This is the sanctioned move — "a case on the wrong
  side either fixes the measurement or joins the corpus" — not a relabelling:
  the claim is now testable and a Cruip repo drifting to 80 or to 5 would fail.
- `saas-starter` was the last wrong row for three releases and two things were
  wrong at once. The scan described the repository while the label described a
  route — that is what `--pages` fixes (`design/scope.py`): the whole tree is
  read, and only the documents the scope is *about* are measured, where "about"
  means under the given path **or** defining a component something in scope
  renders. `Project.subdir` could never do it, because moving the scan root
  leaves `components/` outside and component expansion collapses. And even
  scoped it does not read as generated, because it is not: shadcn/ui semantic
  colour roles behind custom properties, a radius scale keyed to `--radius`, its
  own font stack. Same argument as Cruip's, same side — it is now `crafted`.
- `bench/cases/slop_kit` and `clean_studio_large` are the size pair: multi-page
  App Router projects rendering 300 and 213 elements. They exist because the
  saturation bug survived two releases in a corpus whose largest case was 116
  elements. `tests/test_measure.py::test_decision_density_does_not_grow_with_size`
  pins the property directly.
- A screen's `on_mount` must not `query_one` a **nested** child. It can run
  before grandchildren are in the DOM, and the failure is a crash instead of a
  report — once in five full test runs, which is worse than always. Titles are
  set in `compose` (`screens.base.titled`) and widget focus is deferred with
  `call_after_refresh` for the same reason.
- There is no headless/CI mode and no exit-code gate. The template score is not
  a number a build should hang on; putting a threshold on it rewards gaming the
  measurement. What an agent needs is exported as a brief (`x`).
- **Deliberate non-goals**, unchanged: no LLM call (the measurement stays
  deterministic and offline; creative work is handed to an agent and the tool
  describes it), no CI gate or threshold, no attempt to measure "how many sites
  use this template", no DOM restructuring, no code-error rules (ESLint does
  those), no browser rendering or pixel diffing, and **no hand-tuning a score
  to make the field table look better** — a case on the wrong side either fixes
  the measurement, joins the corpus, or takes its own side and is pinned there.
