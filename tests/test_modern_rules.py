"""Tests for the modern-AI-mistake rules: undeclared imports, empty catch,
token-in-storage, postMessage wildcard and current-generation prose tells."""

import json
import os

from aislopfixer.engine.models import SourceFile
from aislopfixer.engine.runner import run_cross_rules, run_file_rules


def sf(text: str, name: str = "app.js") -> SourceFile:
    return SourceFile(abs_path=name, rel_path=name, text=text)


def ids(findings):
    return [f.rule_id for f in findings]


# ------------------------------------------------------------ empty catch
def test_empty_catch_flagged():
    f = run_file_rules(sf("try { risky(); } catch (e) {}\n"))
    assert "codegen.empty_catch" in ids(f)


def test_empty_catch_comment_body_not_flagged():
    # A comment in the body documents intent — deliberate suppression, not slop
    # (same convention as eslint no-empty: a comment makes the block non-empty).
    f = run_file_rules(sf("try { x(); } catch (err) {\n  // ignore\n}\n"))
    assert "codegen.empty_catch" not in ids(f)


def test_empty_catch_block_comment_body_not_flagged():
    f = run_file_rules(sf("try { x(); } catch { /* quota errors are fine */ }\n"))
    assert "codegen.empty_catch" not in ids(f)


def test_empty_catch_is_info_severity():
    from aislopfixer.engine.models import Severity

    f = run_file_rules(sf("try { risky(); } catch (e) {}\n"))
    hits = [x for x in f if x.rule_id == "codegen.empty_catch"]
    assert hits and hits[0].severity is Severity.INFO


def test_empty_promise_catch_flagged():
    f = run_file_rules(sf("fetchData().catch(() => {});\n"))
    assert "codegen.empty_catch" in ids(f)


def test_handled_catch_not_flagged():
    f = run_file_rules(sf("try { x(); } catch (e) { report(e); }\n"))
    assert "codegen.empty_catch" not in ids(f)


def test_optional_binding_empty_catch_flagged():
    f = run_file_rules(sf("try { x(); } catch {}\n"))
    assert "codegen.empty_catch" in ids(f)


# ---------------------------------------------------- token in web storage
def test_token_in_localstorage_flagged():
    f = run_file_rules(sf("localStorage.setItem('accessToken', token);\n"))
    assert "security.token_in_storage" in ids(f)


def test_jwt_in_sessionstorage_flagged():
    f = run_file_rules(sf('sessionStorage.setItem("jwt", res.jwt);\n'))
    assert "security.token_in_storage" in ids(f)


def test_theme_in_localstorage_not_flagged():
    f = run_file_rules(sf("localStorage.setItem('theme', 'dark');\n"))
    assert "security.token_in_storage" not in ids(f)


def test_author_key_not_flagged():
    # 'author' must not trip the 'auth' stem.
    f = run_file_rules(sf("localStorage.setItem('authorName', name);\n"))
    assert "security.token_in_storage" not in ids(f)


# ------------------------------------------------------ postMessage('*')
def test_postmessage_wildcard_flagged():
    f = run_file_rules(sf("window.parent.postMessage(payload, '*');\n"))
    assert "security.postmessage_wildcard" in ids(f)


def test_postmessage_exact_origin_not_flagged():
    f = run_file_rules(sf("win.postMessage(data, 'https://app.example');\n"))
    assert "security.postmessage_wildcard" not in ids(f)


# --------------------------------------------------------- prose tells
def test_not_just_contrast_flagged():
    f = run_file_rules(
        sf("<p>This is not just a dashboard — it's a command center.</p>\n",
           "landing.html")
    )
    assert "prose.not_just_contrast" in ids(f)


def test_whether_youre_flagged():
    f = run_file_rules(
        sf("<p>Whether you're a startup or an enterprise, we scale.</p>\n",
           "landing.html")
    )
    assert "prose.whether_youre" in ids(f)


def test_plain_not_just_sentence_not_flagged():
    f = run_file_rules(
        sf("<p>The outage was not just in Europe. Asia saw it too.</p>\n",
           "post.html")
    )
    assert "prose.not_just_contrast" not in ids(f)


# ------------------------------------------------------ undeclared imports
def _project(tmp_path, deps: dict, files: dict) -> list[SourceFile]:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "demo", "dependencies": deps}), encoding="utf-8"
    )
    out = []
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        # Mirror the scanner: rel_path uses the OS separator, consistent with abs_path.
        out.append(
            SourceFile(
                abs_path=str(p),
                rel_path=os.path.relpath(str(p), str(tmp_path)),
                text=text,
            )
        )
    return out


def test_undeclared_import_flagged(tmp_path):
    files = _project(
        tmp_path,
        {"react": "^18.0.0"},
        {"app.jsx": "import React from 'react';\nimport pad from 'left-pad';\n"},
    )
    found = [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]
    assert len(found) == 1
    assert "left-pad" in found[0].message


def test_declared_relative_builtin_alias_skipped(tmp_path):
    files = _project(
        tmp_path,
        {"react": "^18.0.0"},
        {
            "src/app.ts": (
                "import React from 'react';\n"
                "import { x } from './util';\n"
                "import fs from 'node:fs';\n"
                "import path from 'path';\n"
                "import sub from 'fs/promises';\n"
                "import lib from '@/lib/api';\n"
            )
        },
    )
    assert not [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]


def test_scoped_subpath_resolves_to_scope_package(tmp_path):
    files = _project(
        tmp_path,
        {"@tanstack/react-query": "^5"},
        {"q.ts": "import { QueryClient } from '@tanstack/react-query/build';\n"},
    )
    assert not [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]


def test_no_manifest_means_silent(tmp_path):
    p = tmp_path / "main.js"
    text = "import chalk from 'chalk';\n"
    p.write_text(text, encoding="utf-8")
    files = [SourceFile(abs_path=str(p), rel_path="main.js", text=text)]
    assert not [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]


def test_devdependency_counts(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"vitest": "^2"}}), encoding="utf-8"
    )
    p = tmp_path / "a.test.ts"
    text = "import { test } from 'vitest';\n"
    p.write_text(text, encoding="utf-8")
    files = [SourceFile(abs_path=str(p), rel_path="a.test.ts", text=text)]
    assert not [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]


def test_tsconfig_paths_alias_skipped(tmp_path):
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"paths": {"components/*": ["src/components/*"]}}}',
        encoding="utf-8",
    )
    files = _project(
        tmp_path,
        {},
        {"page.tsx": "import { Button } from 'components/Button';\n"},
    )
    assert not [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]


def test_monorepo_child_manifest_unions_with_root(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^18"}}), encoding="utf-8"
    )
    pkg = tmp_path / "packages" / "web"
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text(
        json.dumps({"dependencies": {"zod": "^3"}}), encoding="utf-8"
    )
    p = pkg / "form.ts"
    text = "import { z } from 'zod';\nimport React from 'react';\n"
    p.write_text(text, encoding="utf-8")
    rel = os.path.relpath(str(p), str(tmp_path))
    files = [SourceFile(abs_path=str(p), rel_path=rel, text=text)]
    assert not [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]


def test_same_package_reported_once_per_file(tmp_path):
    files = _project(
        tmp_path,
        {},
        {"a.ts": "import x from 'ghost-lib';\nimport { y } from 'ghost-lib/extra';\n"},
    )
    found = [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]
    assert len(found) == 1


def test_multiline_undeclared_import_flagged(tmp_path):
    # A Prettier-wrapped import of a hallucinated package must still be caught.
    files = _project(
        tmp_path,
        {"react": "^18.0.0"},
        {"app.tsx": "import {\n  thing,\n} from 'totally-hallucinated-pkg';\n"},
    )
    found = [f for f in run_cross_rules(files) if f.rule_id == "import.undeclared"]
    assert len(found) == 1
    assert "totally-hallucinated-pkg" in found[0].message
