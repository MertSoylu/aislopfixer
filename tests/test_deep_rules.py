"""Tests for the deep-analysis rules: phantom exports, unused imports,
fake API URLs, duplicated code blocks, comment density, widened catches."""

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_cross_rules, run_file_rules


def sf(text: str, name: str = "app.js") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings):
    return [f.rule_id for f in findings]


# ------------------------------------------------------- phantom exports
def test_missing_named_export_flagged():
    util = sf("export function formatDate(d) { return d.toISOString(); }\n", "util.ts")
    app = sf("import { formatDate, parseDate } from './util';\n", "app.ts")
    found = [f for f in run_cross_rules([util, app]) if f.rule_id == "import.missing_export"]
    assert len(found) == 1
    assert "parseDate" in found[0].message


def test_existing_named_export_not_flagged():
    util = sf("export const a = 1;\nexport function b() {}\n", "util.ts")
    app = sf("import { a, b } from './util';\n", "app.ts")
    assert "import.missing_export" not in ids(run_cross_rules([util, app]))


def test_alias_and_reexport_names_resolve():
    util = sf("const x = 1;\nexport { x as publicX };\n", "util.ts")
    app = sf("import { publicX as y } from './util';\n", "app.ts")
    assert "import.missing_export" not in ids(run_cross_rules([util, app]))


def test_missing_default_export_flagged():
    util = sf("export const helper = 1;\n", "util.ts")
    app = sf("import helper from './util';\n", "app.ts")
    found = [f for f in run_cross_rules([util, app]) if f.rule_id == "import.missing_export"]
    assert len(found) == 1
    assert "no default export" in found[0].message


def test_export_star_bails_out():
    barrel = sf("export * from './inner';\n", "index.ts")
    app = sf("import { anything } from './index';\n", "app.ts")
    assert "import.missing_export" not in ids(run_cross_rules([barrel, app]))


def test_commonjs_target_bails_out():
    util = sf("module.exports = { thing: 1 };\n", "util.js")
    app = sf("import { thing } from './util';\n", "app.js")
    assert "import.missing_export" not in ids(run_cross_rules([util, app]))


def test_unresolved_target_is_silent():
    app = sf("import { x } from './not-scanned';\n", "app.ts")
    assert "import.missing_export" not in ids(run_cross_rules([app]))


def test_nodenext_js_specifier_resolves_ts_source():
    util = sf("export const real = 1;\n", "util.ts")
    app = sf("import { fake } from './util.js';\n", "app.ts")
    found = [f for f in run_cross_rules([util, app]) if f.rule_id == "import.missing_export"]
    assert len(found) == 1


def test_type_export_satisfies_type_import():
    util = sf("export interface Config { a: number }\nexport type Mode = 'x';\n", "types.ts")
    app = sf("import type { Config, Mode } from './types';\n", "app.ts")
    assert "import.missing_export" not in ids(run_cross_rules([util, app]))


# --------------------------------------------------------- unused imports
def test_unused_import_flagged():
    f = run_file_rules(sf("import { useState, useEffect } from 'react';\n"
                          "export const n = useState(0);\n", "hook.ts"))
    found = [x for x in f if x.rule_id == "import.unused"]
    assert len(found) == 1
    assert "useEffect" in found[0].message


def test_used_imports_not_flagged():
    f = run_file_rules(sf("import { a } from './m';\nexport const b = a + 1;\n", "x.ts"))
    assert "import.unused" not in ids(f)


def test_react_default_import_never_flagged():
    f = run_file_rules(sf("import React from 'react';\n"
                          "export const el = <div>hi</div>;\n", "c.jsx"))
    assert "import.unused" not in ids(f)


def test_namespace_import_usage_detected():
    f = run_file_rules(sf("import * as path from 'path';\n"
                          "export const p = path.join('a', 'b');\n", "x.ts"))
    assert "import.unused" not in ids(f)


def test_component_used_in_vue_template_not_flagged():
    text = ("<script setup>\nimport Card from './Card.vue';\n</script>\n"
            "<template><Card /></template>\n")
    f = run_file_rules(sf(text, "Page.vue"))
    assert "import.unused" not in ids(f)


# ------------------------------------------------------------ fake API URLs
def test_fake_api_url_flagged():
    f = run_file_rules(sf("fetch('https://api.yourdomain.com/v1/users');\n"))
    assert "placeholder.fake_api" in ids(f)


def test_real_api_url_not_flagged():
    f = run_file_rules(sf("fetch('https://api.stripe.com/v1/charges');\n"))
    assert "placeholder.fake_api" not in ids(f)


# ------------------------------------------------------ duplicated code blocks
_HELPER = (
    "export function slugify(input) {\n"
    "  const lower = input.toLowerCase();\n"
    "  const trimmed = lower.trim();\n"
    "  const dashed = trimmed.replace(/\\s+/g, '-');\n"
    "  const cleaned = dashed.replace(/[^a-z0-9-]/g, '');\n"
    "  if (!cleaned) {\n"
    "    return 'untitled';\n"
    "  }\n"
    "  return cleaned;\n"
    "}\n"
)


def test_duplicated_code_block_across_files_flagged():
    cross = run_cross_rules([sf(_HELPER, "a.js"), sf(_HELPER, "b.js")])
    dup = [x for x in cross if x.rule_id == "duplicate.code_block"]
    assert len(dup) == 2


def test_different_logic_not_flagged():
    other = (
        "export function truncate(s, n) {\n"
        "  if (s.length <= n) {\n"
        "    return s;\n"
        "  }\n"
        "  const cut = s.slice(0, n - 1);\n"
        "  const safe = cut.trimEnd();\n"
        "  const suffix = '\\u2026';\n"
        "  const result = safe + suffix;\n"
        "  return result;\n"
        "}\n"
    )
    cross = run_cross_rules([sf(_HELPER, "a.js"), sf(other, "b.js")])
    assert "duplicate.code_block" not in ids(cross)


def test_shared_import_prologue_not_flagged():
    imports = "\n".join(
        f"import {{ mod{i} }} from './mod{i}';" for i in range(10)
    ) + "\n"
    cross = run_cross_rules([sf(imports, "a.ts"), sf(imports, "b.ts")])
    assert "duplicate.code_block" not in ids(cross)


def test_same_file_repeat_not_flagged():
    cross = run_cross_rules([sf(_HELPER + "\n" + _HELPER, "a.js")])
    assert "duplicate.code_block" not in ids(cross)


def _many_helpers() -> str:
    text = ""
    for name in ("slugify", "titleize", "dasherize"):
        text += _HELPER.replace("slugify", name) + "\n"
    return text


def test_copied_file_collapses_to_one_finding_per_file():
    # Two copies of a whole utility file share every block: that is ONE root
    # cause (a copied file), so report once per file, not once per block.
    text = _many_helpers()
    cross = run_cross_rules([sf(text, "a.js"), sf(text, "pages/b.js")])
    dup = [x for x in cross if x.rule_id == "duplicate.code_block"]
    assert len(dup) == 2
    assert all("3" in x.message for x in dup)


def test_test_files_exempt_from_code_duplicates():
    # Copy-pasted setup across *.test.js / *.spec.ts files is normal practice.
    cross = run_cross_rules([sf(_HELPER, "a.test.js"), sf(_HELPER, "b.test.js")])
    assert "duplicate.code_block" not in ids(cross)
    cross = run_cross_rules(
        [sf(_HELPER, "__tests__/a.js"), sf(_HELPER, "__tests__/b.js")]
    )
    assert "duplicate.code_block" not in ids(cross)


# ------------------------------------------------------------ comment density
def test_comment_density_flagged():
    lines = []
    for i in range(15):
        lines.append(f"// set the value for step {i}")
        lines.append(f"const v{i} = {i};")
    f = run_file_rules(sf("\n".join(lines) + "\n", "walk.js"))
    assert "codegen.comment_density" in ids(f)


def test_normal_comment_ratio_not_flagged():
    lines = ["// explains a genuinely tricky invariant"]
    lines += [f"const v{i} = {i};" for i in range(40)]
    f = run_file_rules(sf("\n".join(lines) + "\n", "calm.js"))
    assert "codegen.comment_density" not in ids(f)


def test_directive_comments_not_counted():
    lines = []
    for i in range(15):
        lines.append("// eslint-disable-next-line no-console")
        lines.append(f"console.info(report{i});")
    f = run_file_rules(sf("\n".join(lines) + "\n", "lint.js"))
    assert "codegen.comment_density" not in ids(f)


# ------------------------------------------------------------ widened catches
def test_log_only_catch_flagged():
    f = run_file_rules(sf("try { x(); } catch (e) { console.error(e); }\n"))
    assert "codegen.log_only_catch" in ids(f)


def test_promise_log_only_catch_flagged():
    f = run_file_rules(sf("load().catch(err => console.log(err));\n"))
    assert "codegen.log_only_catch" in ids(f)


def test_catch_return_null_flagged():
    f = run_file_rules(sf("try { return parse(s); } catch (e) { return null; }\n"))
    assert "codegen.catch_return_default" in ids(f)


def test_promise_catch_null_arrow_flagged():
    f = run_file_rules(sf("const data = await load().catch(() => null);\n"))
    assert "codegen.catch_return_default" in ids(f)


def test_catch_returning_variable_fallback_not_flagged():
    f = run_file_rules(sf("try { return fresh(); } catch (e) { return cached; }\n"))
    assert "codegen.catch_return_default" not in ids(f)


def test_catch_with_real_handling_not_flagged():
    f = run_file_rules(sf(
        "try { run(); } catch (e) { console.error(e); notifyUser(e); }\n"
    ))
    assert "codegen.log_only_catch" not in ids(f)
    assert "codegen.catch_return_default" not in ids(f)


# ------------------------------------------------------- multiline imports
def test_multiline_import_missing_export_flagged():
    # Prettier-wrapped imports span lines; the phantom-symbol check must still see them.
    util = sf("export function formatDate(d) { return d.toISOString(); }\n", "util.ts")
    app = sf(
        "import {\n  formatDate,\n  parseDate,\n} from './util';\n", "app.ts"
    )
    found = [f for f in run_cross_rules([util, app]) if f.rule_id == "import.missing_export"]
    assert len(found) == 1
    assert "parseDate" in found[0].message


def test_multiline_unused_import_flagged():
    f = run_file_rules(sf(
        "import {\n  useState,\n  useEffect,\n} from 'react';\n"
        "export const n = useState(0);\n", "hook.ts"))
    found = [x for x in f if x.rule_id == "import.unused"]
    assert len(found) == 1
    assert "useEffect" in found[0].message
