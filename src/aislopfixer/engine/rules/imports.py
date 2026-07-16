"""Import-graph rules: hallucinated packages, phantom symbols, unused imports.

Hallucinated dependencies are one of the best-documented failure modes of
modern code generators ("slopsquatting"), and the same failure shows up one
level down: importing a *symbol* the target module never exports, or leaving
imports behind that nothing uses. All three are fully offline checks.

* ``import.undeclared`` — a bare specifier that resolves to no package in any
  ``package.json`` between the file and the scan root (monorepo-aware; Node
  built-ins, tsconfig ``paths``, bundler aliases and baseUrl dirs skipped).
* ``import.missing_export`` — ``import { X } from './util'`` where the scanned
  ``./util`` module demonstrably does not export ``X`` (or a default import
  from a module with no default). Verification bails on anything it cannot
  enumerate: ``export *``, CommonJS ``module.exports``, destructured exports,
  non-JS targets (``.vue``/``.svelte``/``.css``…).
* ``import.unused`` — an imported binding that never appears again in the
  file. Weak signal (INFO), but a very common generated-code leftover.
"""

from __future__ import annotations

import json
import os
import posixpath
import re

from ..models import Category, Fixability, Severity, SourceFile, Finding
from ..registry import cross_rule, file_rule
from ..util import build_finding

_JS_EXT = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".vue", ".svelte", ".astro"}
# Targets whose exports we can enumerate with confidence (no SFC magic).
_VERIFIABLE_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")

# Static import, export-from and require()/import() specifiers. The clause
# between the keyword and ``from`` may span lines (Prettier wraps long imports)
# but never contains quotes or semicolons — that bound keeps the lazy match
# from running away across statements.
_SPECIFIERS = (
    re.compile(r"(?m)^[ \t]*import\s+(?:type\s+)?(?:[^'\";]*?\s+from\s+)?(['\"])([^'\"\n]+)\1"),
    re.compile(r"(?m)^[ \t]*export\s+(?:type\s+)?[^'\";]*?\s+from\s+(['\"])([^'\"\n]+)\1"),
    re.compile(r"\b(?:require|import)\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)"),
)

# Full import statement with a bindings clause (skips side-effect imports).
_IMPORT_STMT = re.compile(
    r"(?m)^[ \t]*import\s+(?:type\s+)?([^'\";]+?)\s+from\s+(['\"])([^'\"\n]+)\2"
)

_NODE_BUILTINS = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads",
    "zlib", "test",
})

# Specifier prefixes that are never a registry package.
_SKIP_PREFIXES = (
    ".", "/", "\\", "~", "#", "$", "@/", "node:", "bun:", "deno:", "npm:",
    "jsr:", "data:", "http://", "https://", "file:", "virtual:", "astro:",
    "vite:", "sveltekit:", "\0",
)

_DEP_KEYS = (
    "dependencies", "devDependencies", "peerDependencies",
    "optionalDependencies", "bundledDependencies",
)

# Tolerant JSONC cleanup for tsconfig files: line comments and trailing commas.
_JSONC_LINE_COMMENT = re.compile(r"(?m)^\s*//[^\n]*$|(?<=[,{[\s])//[^\n]*$")
_JSONC_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_JSONC_TRAILING_COMMA = re.compile(r",(\s*[}\]])")

# ------------------------------------------------------------ export scraping
_EXPORT_DECL = re.compile(
    r"(?m)^[ \t]*export\s+(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(?:const|let|var|function\*?|class|type|interface|enum|namespace)\s+"
    r"([A-Za-z_$][\w$]*)"
)
_EXPORT_BRACE = re.compile(r"(?m)^[ \t]*export\s+(?:type\s+)?\{([^}]*)\}")
_EXPORT_DEFAULT = re.compile(
    r"\bexport\s+default\b|\bexport\s*\{[^}]*\bas\s+default\b|\bexport\s*=\s*"
)
# Shapes we cannot enumerate — verification must bail on the whole module.
_EXPORT_OPAQUE = re.compile(
    r"(?m)^[ \t]*export\s+\*"                       # export * [as ns] from …
    r"|\bmodule\.exports\b|(?<![\w.$])exports\.[A-Za-z_$]"  # CommonJS
    r"|^[ \t]*export\s+(?:const|let|var)\s*[\[{]"    # export const { a, b } = …
)


def _package_name(spec: str) -> str:
    """``@scope/pkg/sub`` -> ``@scope/pkg``;  ``pkg/sub`` -> ``pkg``."""
    parts = spec.split("/")
    if spec.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _read_json(path: str) -> dict | None:
    try:
        raw = open(path, encoding="utf-8-sig").read()
    except OSError:
        return None
    for attempt in (raw, _strip_jsonc(raw)):
        try:
            data = json.loads(attempt)
        except ValueError:
            continue
        return data if isinstance(data, dict) else None
    return None


def _strip_jsonc(raw: str) -> str:
    raw = _JSONC_BLOCK_COMMENT.sub("", raw)
    raw = _JSONC_LINE_COMMENT.sub("", raw)
    return _JSONC_TRAILING_COMMA.sub(r"\1", raw)


def _parse_named(clause: str) -> list[str]:
    """Original (pre-``as``) names inside an import/export brace clause."""
    names: list[str] = []
    for tok in clause.split(","):
        tok = tok.strip()
        if not tok:
            continue
        tok = re.sub(r"^type\s+", "", tok)
        orig = tok.split(" as ")[0].strip() if " as " in tok else tok
        if re.fullmatch(r"[A-Za-z_$][\w$]*|default", orig):
            names.append(orig)
    return names


def _exported_names(text: str) -> tuple[set[str], bool, bool]:
    """``(names, has_default, opaque)`` for a verifiable JS/TS module."""
    if _EXPORT_OPAQUE.search(text):
        return set(), False, True
    names: set[str] = set()
    for m in _EXPORT_DECL.finditer(text):
        names.add(m.group(1))
    for m in _EXPORT_BRACE.finditer(text):
        for tok in m.group(1).split(","):
            tok = tok.strip()
            if not tok:
                continue
            tok = re.sub(r"^type\s+", "", tok)
            exported = tok.split(" as ")[-1].strip() if " as " in tok else tok
            if re.fullmatch(r"[A-Za-z_$][\w$]*", exported):
                names.add(exported)
    return names, bool(_EXPORT_DEFAULT.search(text)), False


@cross_rule
class UndeclaredImportRule:
    category = Category.CODE_SLOP

    def __init__(self) -> None:
        self._manifest_cache: dict[str, frozenset[str]] = {}
        self._alias_cache: dict[str, frozenset[str]] = {}

    # ------------------------------------------------------------- manifests
    def _declared_in(self, directory: str) -> frozenset[str]:
        """Package names declared by ``<directory>/package.json`` (or empty)."""
        if directory in self._manifest_cache:
            return self._manifest_cache[directory]
        names: set[str] = set()
        data = _read_json(os.path.join(directory, "package.json"))
        if data is not None:
            for key in _DEP_KEYS:
                deps = data.get(key)
                if isinstance(deps, dict):
                    names.update(deps)
                elif isinstance(deps, list):  # bundledDependencies may be a list
                    names.update(d for d in deps if isinstance(d, str))
            if isinstance(data.get("name"), str):
                names.add(data["name"])  # self-imports resolve via "exports"
        result = frozenset(names) if data is not None else frozenset()
        # Distinguish "no manifest" from "manifest with no deps" via sentinel.
        self._manifest_cache[directory] = result if data is not None else _NO_MANIFEST
        return self._manifest_cache[directory]

    def _aliases_in(self, directory: str) -> frozenset[str]:
        """Alias prefixes from tsconfig/jsconfig ``compilerOptions.paths``."""
        if directory in self._alias_cache:
            return self._alias_cache[directory]
        prefixes: set[str] = set()
        for name in ("tsconfig.json", "jsconfig.json"):
            data = _read_json(os.path.join(directory, name))
            if not data:
                continue
            paths = (data.get("compilerOptions") or {}).get("paths") or {}
            if isinstance(paths, dict):
                for key in paths:
                    prefixes.add(key.rstrip("*").rstrip("/"))
        self._alias_cache[directory] = frozenset(prefixes)
        return self._alias_cache[directory]

    # ----------------------------------------------------------------- scan
    def scan_all(self, files: list[SourceFile]) -> list[Finding]:
        # Fresh disk state per scan — a user who fixes package.json and rescans
        # must see the finding disappear.
        self._manifest_cache.clear()
        self._alias_cache.clear()
        by_rel = {sf.rel_path.replace("\\", "/"): sf for sf in files}
        export_cache: dict[str, tuple[set[str], bool, bool]] = {}
        out: list[Finding] = []
        for sf in files:
            ext = os.path.splitext(sf.rel_path)[1].lower()
            if ext not in _JS_EXT:
                continue
            # Phantom-symbol verification needs only the scanned file set.
            out.extend(self._scan_symbols(sf, by_rel, export_cache))
            # Undeclared-package verification needs a package.json chain.
            root = self._root_of(sf)
            if root is None:
                continue
            chain = self._dir_chain(os.path.dirname(sf.abs_path), root)
            declared: set[str] = set()
            aliases: set[str] = set()
            saw_manifest = False
            for d in chain:
                names = self._declared_in(d)
                if names is not _NO_MANIFEST:
                    saw_manifest = True
                    declared.update(names)
                aliases.update(self._aliases_in(d))
            if not saw_manifest:
                continue  # nothing to check against (CDN/plain projects)
            out.extend(self._scan_packages(sf, root, declared, aliases))
        return out

    # -------------------------------------------------- undeclared packages
    def _scan_packages(
        self, sf: SourceFile, root: str, declared: set[str], aliases: set[str]
    ) -> list[Finding]:
        out: list[Finding] = []
        seen: set[str] = set()
        for rx in _SPECIFIERS:
            for m in rx.finditer(sf.text):
                spec = m.group(2)
                if self._skip(spec, root, declared, aliases):
                    continue
                pkg = _package_name(spec)
                if pkg in seen:
                    continue
                seen.add(pkg)
                out.append(
                    build_finding(
                        sf,
                        rule_id="import.undeclared",
                        category=self.category,
                        severity=Severity.ERROR,
                        message=(
                            f"Import of undeclared package {pkg!r} — not in any "
                            "package.json (possibly hallucinated)"
                        ),
                        start=m.start(2),
                        end=m.end(2),
                        fixability=Fixability.MANUAL,
                        suggested_fix=(
                            "Verify the package really exists, then install and "
                            "declare it — or remove the import"
                        ),
                    )
                )
        return out

    def _skip(
        self, spec: str, root: str, declared: set[str], aliases: set[str]
    ) -> bool:
        spec = spec.split("?", 1)[0].strip()  # drop vite suffixes (?raw, ?url)
        if not spec or spec.startswith(_SKIP_PREFIXES):
            return True
        pkg = _package_name(spec)
        if not pkg or pkg in declared or pkg in _NODE_BUILTINS:
            return True
        if any(spec == a or spec.startswith(a + "/") for a in aliases if a):
            return True
        # baseUrl-style local module: first segment is a real dir/file at root.
        seg = pkg
        for base in (root, os.path.join(root, "src")):
            if os.path.isdir(os.path.join(base, seg)):
                return True
            for e in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
                if os.path.isfile(os.path.join(base, seg + e)):
                    return True
        return False

    # ---------------------------------------------------- phantom symbols
    def _scan_symbols(
        self,
        sf: SourceFile,
        by_rel: dict[str, SourceFile],
        export_cache: dict[str, tuple[set[str], bool, bool]],
    ) -> list[Finding]:
        out: list[Finding] = []
        importer_dir = posixpath.dirname(sf.rel_path.replace("\\", "/"))
        for m in _IMPORT_STMT.finditer(sf.text):
            clause, spec = m.group(1).strip(), m.group(3)
            if not spec.startswith("."):
                continue
            target = self._resolve(importer_dir, spec, by_rel)
            if target is None:
                continue
            key = target.rel_path
            if key not in export_cache:
                export_cache[key] = _exported_names(target.text)
            names, has_default, opaque = export_cache[key]
            if opaque or (not names and not has_default):
                continue  # can't enumerate, or a script with no exports at all
            for missing, is_default in self._missing(clause, names, has_default):
                span = self._name_span(sf.text, m, missing) or (m.start(3), m.end(3))
                what = (
                    f"{spec!r} has no default export"
                    if is_default
                    else f"{missing!r} is not exported by {spec!r}"
                )
                out.append(
                    build_finding(
                        sf,
                        rule_id="import.missing_export",
                        category=self.category,
                        severity=Severity.ERROR,
                        message=f"{what} — possibly hallucinated symbol",
                        start=span[0],
                        end=span[1],
                        fixability=Fixability.MANUAL,
                        suggested_fix=(
                            "Check the target module: fix the name, add the "
                            "export, or remove the import"
                        ),
                    )
                )
        return out

    @staticmethod
    def _missing(
        clause: str, names: set[str], has_default: bool
    ) -> list[tuple[str, bool]]:
        """``(name, is_default_import)`` pairs the target does not provide."""
        out: list[tuple[str, bool]] = []
        brace = re.search(r"\{([^}]*)\}", clause)
        head = clause[: brace.start()] if brace else clause
        head = head.strip().rstrip(",").strip()
        if head and not head.startswith("*"):  # default import (namespaces always ok)
            if re.fullmatch(r"[A-Za-z_$][\w$]*", head) and not has_default:
                out.append((head, True))
        if brace:
            for orig in _parse_named(brace.group(1)):
                if orig == "default":
                    if not has_default:
                        out.append((orig, True))
                elif orig not in names:
                    out.append((orig, False))
        return out

    @staticmethod
    def _name_span(text: str, stmt: re.Match, name: str) -> tuple[int, int] | None:
        m = re.search(rf"\b{re.escape(name)}\b", stmt.group(1))
        if m is None:
            return None
        base = stmt.start(1)
        return base + m.start(), base + m.end()

    @staticmethod
    def _resolve(
        importer_dir: str, spec: str, by_rel: dict[str, SourceFile]
    ) -> SourceFile | None:
        """Resolve a relative specifier to a scanned, verifiable module."""
        base = posixpath.normpath(posixpath.join(importer_dir, spec))
        candidates = [base]
        # NodeNext TS style: ./util.js in source actually means ./util.ts
        stem, ext = posixpath.splitext(base)
        if ext in (".js", ".mjs", ".cjs"):
            candidates += [stem + e for e in (".ts", ".tsx", ".mts", ".cts")]
        candidates += [base + e for e in _VERIFIABLE_EXT]
        candidates += [posixpath.join(base, "index") + e for e in _VERIFIABLE_EXT]
        for cand in candidates:
            sf = by_rel.get(cand)
            if sf is not None:
                if os.path.splitext(cand)[1].lower() in _VERIFIABLE_EXT:
                    return sf
                return None  # resolved to .vue/.css/… — not verifiable
        return None

    # ------------------------------------------------------------- plumbing
    @staticmethod
    def _root_of(sf: SourceFile) -> str | None:
        """Scan root recovered from ``abs_path`` minus ``rel_path``."""
        ap, rp = sf.abs_path, sf.rel_path
        if not ap.endswith(rp) or len(ap) == len(rp):
            return None
        root = ap[: len(ap) - len(rp)].rstrip("/\\")
        return root if root and os.path.isdir(root) else None

    @staticmethod
    def _dir_chain(start: str, root: str) -> list[str]:
        """Directories from the file's own up to (and including) the root."""
        chain: list[str] = []
        d = start or root
        root_norm = os.path.normcase(os.path.normpath(root))
        for _ in range(64):  # hard stop against symlink loops
            chain.append(d)
            if os.path.normcase(os.path.normpath(d)) == root_norm:
                break
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return chain


_NO_MANIFEST: frozenset[str] = frozenset({"\0no-manifest\0"})


# --------------------------------------------------------------- unused imports
# Bindings the classic JSX runtime references invisibly (compiled output uses
# them even when the source text does not).
_JSX_RUNTIME_NAMES = frozenset({"React", "h", "Fragment"})


@file_rule
class UnusedImportRule:
    """Imported bindings that never appear again in the file."""

    category = Category.CODE_SLOP

    def scan(self, sf: SourceFile) -> list[Finding]:
        ext = os.path.splitext(sf.rel_path)[1].lower()
        if ext not in _JS_EXT:
            return []
        stmts = list(_IMPORT_STMT.finditer(sf.text))
        if not stmts:
            return []
        # Everything outside import statements is where a use must appear.
        rest = _IMPORT_STMT.sub("", sf.text)
        out: list[Finding] = []
        for m in stmts:
            for name, start, end in self._bindings(m):
                if name in _JSX_RUNTIME_NAMES or name.startswith("_"):
                    continue
                if re.search(rf"\b{re.escape(name)}\b", rest):
                    continue
                out.append(
                    build_finding(
                        sf,
                        rule_id="import.unused",
                        category=self.category,
                        severity=Severity.INFO,
                        message=f"Unused import {name!r} — nothing references it",
                        start=start,
                        end=end,
                        fixability=Fixability.MANUAL,
                        suggested_fix="Remove the unused binding",
                    )
                )
        return out

    @staticmethod
    def _bindings(m: re.Match) -> list[tuple[str, int, int]]:
        """Local binding names introduced by one import statement, with spans."""
        clause = m.group(1)
        base = m.start(1)
        out: list[tuple[str, int, int]] = []

        def local_of(tok: str) -> str:
            tok = re.sub(r"^type\s+", "", tok.strip())
            return tok.split(" as ")[-1].strip() if " as " in tok else tok

        brace = re.search(r"\{([^}]*)\}", clause)
        head = clause[: brace.start()] if brace else clause
        for part in head.split(","):
            part = part.strip()
            if not part:
                continue
            if part.startswith("*"):  # * as ns  ->  ns
                part = part.split()[-1]
            if re.fullmatch(r"[A-Za-z_$][\w$]*", part):
                sub = re.search(rf"\b{re.escape(part)}\b", clause)
                if sub:
                    out.append((part, base + sub.start(), base + sub.end()))
        if brace:
            for tok in brace.group(1).split(","):
                name = local_of(tok)
                if re.fullmatch(r"[A-Za-z_$][\w$]*", name):
                    sub = re.search(rf"\b{re.escape(name)}\b", clause)
                    if sub:
                        out.append((name, base + sub.start(), base + sub.end()))
        return out
