"""Detect AI-pasted code slop in source files.

Code files (``.js/.ts/.jsx/.vue/.svelte/.css`` …) escape every prose-based rule
because :func:`prose_regions` returns ``[]`` for them. They still leak the most
recognizable machine tells, and this rule covers them:

* **elision markers** — ``// ... existing code ...``, ``// rest of the component
  remains unchanged`` — a handoff that real code was dropped from a paste. The
  flagship tell; ERROR but MANUAL, because the code is *missing* and cannot be
  auto-completed.
* **not-implemented stubs** — ``throw new Error('Not implemented')``,
  ``raise NotImplementedError`` — a punted function body.
* **fill-in-the-blank stub comments** — ``// your code here``, ``// implement me``.
* **leftover debug** — a bare ``debugger;`` line (AUTO delete) and throwaway
  ``console.log('here')`` breadcrumbs from a fixed junk-string whitelist.
* **restate-the-code comments** — ``// Initialize the variable`` — redundant
  narration of the next line; weak INFO signal, useful only in aggregate.

Every pattern is anchored to a real comment/statement shape and gated so that
JS spread/rest, identifiers, string contents and template-literal examples are
never flagged. ``#`` is deliberately *not* treated as a comment opener: none of
the scanned web extensions use ``#`` line comments, and accepting it would
misfire on Markdown headings.
"""

from __future__ import annotations

import re

from ..context import file_kind
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule
from ..util import build_finding

_I = re.IGNORECASE

# Comment openers present in real web files (no ``#`` — that is a Markdown head).
_OPEN = r"(?://+|/\*|\*|<!--)"
_NOUN = (
    r"(?:code|file|implementation|component|function|methods?|logic|markup|"
    r"html|template|imports?|props?|styles?|content|stuff)"
)

_ELISION = re.compile(
    r"(?im)^[ \t]*" + _OPEN + r"\s*(?:"
    # (A) ellipsis + elision keyword
    r"(?:\.{3}|…)\s*\(?\s*(?:the\s+)?(?:rest|remaining|existing|previous|more|"
    r"other|same|unchanged|omitted|truncated|snip|and\s+so\s+(?:on|forth))\b"
    # (B) "rest/remainder of [the] <noun>"
    r"|(?:rest|remainder)\s+of\s+(?:the\s+)?" + _NOUN + r"\b"
    # (C) "<noun> [remains|is] unchanged|omitted|the same"
    r"|" + _NOUN + r"\s+(?:remains?|stays?|is)?\s*(?:unchanged|omitted|the\s+same)\b"
    # (D) "[keep [the]] existing <noun>" — tightened: must end the comment or be
    #     followed by an elision qualifier, so "// existing code is in utils.js"
    #     (a real cross-reference) does not fire.
    r"|(?:keep\s+(?:the\s+)?)?existing\s+" + _NOUN
    + r"(?:[ \t]*$|\s+(?:unchanged|omitted|remains?))"
    # (E) "truncated/omitted/... for brevity"
    r"|(?:truncated|omitted|abbreviated|snipped)\s+for\s+brevity\b"
    # (F) "same as above/before"
    r"|same\s+as\s+(?:above|before)\b"
    r")"
)

_STUB_BODY = re.compile(
    r"throw\s+new\s+Error\s*\(\s*['\"`]\s*"
    r"(?:not[ _]implemented|unimplemented|todo|implement\s+(?:me|this))\b[^)]*\)"
    r"|\braise\s+NotImplementedError\b",
    _I,
)

_STUB_COMMENT = re.compile(
    r"(?im)^[ \t]*(?://+|/\*|\*)\s*(?:"
    r"your\s+(?:code|logic|implementation|stuff)\s+(?:here|goes\s+here)"
    r"|(?:add|insert|put|write|implement)\s+your\s+(?:own\s+)?"
    r"(?:code|logic|implementation|here)"
    r"|(?:add|insert|write)\s+(?:your\s+)?(?:logic|code|implementation)\s+here"
    r"|implement\s+(?:me|this|here)\b"
    r"|TODO:\s*implement\b"
    r"|fill\s+(?:this\s+)?in\b"
    r"|placeholder\s+(?:implementation|function|logic|code)\b"
    r")"
)

# A bare Markdown code fence on its own line is never valid JS/TS/CSS/HTML — it
# is the residue of pasting a model's ```lang … ``` block straight into a file.
_FENCE = re.compile(r"(?m)^[ \t]*`{3,}[A-Za-z0-9+#.-]*[ \t]*$")

_DEBUGGER = re.compile(r"(?m)^[ \t]*debugger\s*;?\s*$")

_DEBUG_LOG = re.compile(
    r"(?im)^[ \t]*console\.(?:log|debug|info)\(\s*"
    r"(?:(['\"`])\s*(?:here|test(?:ing)?|hello(?:\s+world)?|debug|asdf+|qwerty|"
    r"foo|bar|baz|aa+|xxx+|=+|-+|\*+|\?+)\s*\1|\d+)?\s*\)\s*;?\s*$"
)

# Empty catch block: whitespace only. The try/catch-everything habit of
# generated code, with the error silently swallowed — failures vanish. A body
# holding a comment is exempt: `catch { /* quota errors are fine */ }` is a
# documented decision (same convention eslint's no-empty applies).
_EMPTY_CATCH = re.compile(
    r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}"
    r"|\.catch\s*\(\s*(?:\([^)]*\)|[\w$]+)\s*=>\s*\{\s*\}\s*\)"
    r"|\.catch\s*\(\s*function\s*\([^)]*\)\s*\{\s*\}\s*\)"
)

# Same disease, thin disguise: the catch body only logs, or only returns a
# literal default — the failure is still invisible to the caller/user.
_LOG_ONLY_CATCH = re.compile(
    r"\bcatch\s*\(\s*[\w$]+\s*\)\s*\{\s*console\.(?:log|warn|error|debug)\s*\([^()]*\)\s*;?\s*\}"
    r"|\.catch\s*\(\s*console\.(?:log|warn|error|debug)\s*\)"
    r"|\.catch\s*\(\s*(?:\(\s*[\w$]*\s*\)|[\w$]+)\s*=>\s*console\.(?:log|warn|error|debug)\s*\([^()]*\)\s*\)"
)
_CATCH_RETURN_DEFAULT = re.compile(
    r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*"
    r"return(?:\s+(?:null|undefined|false|true|0|-1|\[\s*\]|\{\s*\}|''|\"\"|``))?\s*;?\s*\}"
    r"|\.catch\s*\(\s*(?:\(\s*[\w$]*\s*\)|[\w$]+)\s*=>\s*(?:null|undefined|false|\[\s*\]|\(\s*\{\s*\}\s*\))\s*\)"
)

# A catch that does not even *bind* the error and returns a boolean is asking
# "did that throw?" — a capability probe, which is the correct implementation of
# feature detection rather than a swallowed failure:
#
#     try { window.localStorage.setItem("__probe__", "1"); return true; }
#     catch { return false; }
#
# _EMPTY_CATCH exempts a documented catch for exactly this reason; without the
# same escape here the canonical localStorage probe was reported RISKY at 62%.
_PROBE_CATCH = re.compile(r"\bcatch\s*\{\s*return\s+(?:false|true)\s*;?\s*\}")


def _not_a_probe(m: re.Match, sf: SourceFile) -> bool:
    return _PROBE_CATCH.fullmatch(m.group(0)) is None

_RESTATE = re.compile(
    r"(?im)^[ \t]*//+\s*(?:"
    r"(?:initialize|define|declare|create|set|setup|set\s+up)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?:variable|constant|const|array|object|function|"
    r"state|counter|variables?)"
    r"|(?:import|require)\s+(?:the\s+)?"
    r"(?:dependencies|modules|libraries|packages|imports)"
    r"|(?:return|returns)\s+the\s+(?:result|value|response|data)"
    r"|(?:loop|iterate)\s+(?:over|through)\s+(?:the\s+|each\s+)?\w+"
    r"|increment\s+(?:the\s+)?(?:counter|count|index|i)"
    r"|(?:call|invoke|execute|run)\s+the\s+(?:function|method|callback)"
    r"|export\s+the\s+(?:component|module|function|default)"
    r"|(?:add|attach)\s+(?:an?\s+)?event\s+listener"
    r")\s*$"
)


# ------------------------------------------------------------ comment density
# Line-by-line ``//`` narration is the strongest aggregate tell of generated
# code. Block comments (JSDoc) are documentation and never counted; tool
# directives and ruler lines are excluded.
_COMMENT_ONLY_LINE = re.compile(r"^\s*//")
_COMMENT_DIRECTIVE = re.compile(
    r"^\s*//\s*(?:eslint|@ts-|ts-(?:ignore|expect)|prettier|biome|tslint|"
    r"@vite|@jsx|@__PURE__|-{3,}|={3,}|#|/)"
)
_DENSITY_MIN_LINES = 30      # ignore small files — ratios are meaningless there
_DENSITY_MIN_COMMENTS = 12
_DENSITY_RATIO = 0.35


@file_rule
class CodeGenRule(PatternRule):
    category = Category.CODE_SLOP

    def scan(self, sf: SourceFile) -> list[Finding]:
        out = super().scan(sf)
        if file_kind(sf.rel_path) in ("code", "jsx"):
            density = self._comment_density(sf)
            if density is not None:
                out.append(density)
        return out

    def _comment_density(self, sf: SourceFile) -> Finding | None:
        nonblank = 0
        comments = 0
        for line in sf.text.splitlines():
            if not line.strip():
                continue
            nonblank += 1
            if _COMMENT_ONLY_LINE.match(line) and not _COMMENT_DIRECTIVE.match(line):
                comments += 1
        if (
            nonblank < _DENSITY_MIN_LINES
            or comments < _DENSITY_MIN_COMMENTS
            or comments / nonblank < _DENSITY_RATIO
        ):
            return None
        return build_finding(
            sf,
            rule_id="codegen.comment_density",
            category=self.category,
            severity=Severity.INFO,
            message=(
                f"Comment-heavy file ({comments} of {nonblank} lines are "
                "// comments) — reads as AI line-by-line narration"
            ),
            start=0,
            end=0,
            fixability=Fixability.MANUAL,
            suggested_fix="Keep comments that explain *why*; delete the narration",
        )

    patterns = [
        Pattern(
            id="codegen.elision",
            regex=_ELISION,
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="Elision marker — real code was dropped from this paste",
            suggested_fix="Restore the omitted code; this file is incomplete",
            exclude_strings=True,
        ),
        Pattern(
            id="codegen.stub_body",
            regex=_STUB_BODY,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Not-implemented stub — function body was never written",
            suggested_fix="Implement the function body",
            exclude_strings=True,
        ),
        Pattern(
            id="codegen.stub_comment",
            regex=_STUB_COMMENT,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Fill-in-the-blank stub comment standing in for real logic",
            suggested_fix="Replace with the actual implementation",
            exclude_strings=True,
        ),
        Pattern(
            id="codegen.debugger",
            regex=_DEBUGGER,
            severity=Severity.ERROR,
            fixability=Fixability.AUTO,
            message="Leftover debugger statement",
            suggested_fix="Delete this line",
            replacement="",
            expand_line=True,
            exclude_strings=True,
        ),
        Pattern(
            id="codegen.debug_log",
            regex=_DEBUG_LOG,
            severity=Severity.WARNING,
            fixability=Fixability.AUTO,
            message="Throwaway debug console.log",
            suggested_fix="Delete this line",
            replacement="",
            expand_line=True,
            exclude_strings=True,
        ),
        Pattern(
            id="codegen.empty_catch",
            regex=_EMPTY_CATCH,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Empty catch block — the error is silently swallowed",
            suggested_fix="Handle the error (report/rethrow) or remove the try/catch",
            kinds=frozenset({"code", "jsx", "html"}),
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="codegen.catch_return_default",
            regex=_CATCH_RETURN_DEFAULT,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Catch returns a literal default — failure is silently masked",
            suggested_fix="Surface the error, or make the fallback explicit and logged",
            kinds=frozenset({"code", "jsx", "html"}),
            exclude_strings=True,
            exclude_comments=True,
            guard=_not_a_probe,
        ),
        Pattern(
            id="codegen.log_only_catch",
            regex=_LOG_ONLY_CATCH,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Catch only logs to console — the error goes nowhere useful",
            suggested_fix="Handle or rethrow; a console line is not error handling",
            kinds=frozenset({"code", "jsx", "html"}),
            exclude_strings=True,
            exclude_comments=True,
        ),
        Pattern(
            id="codegen.restate_comment",
            regex=_RESTATE,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Comment merely restates the next line of code",
            suggested_fix="Delete the redundant comment or explain *why*, not *what*",
            exclude_strings=True,
        ),
        Pattern(
            id="codegen.markdown_fence",
            regex=_FENCE,
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="Leftover Markdown code fence pasted from a chat — breaks this file",
            suggested_fix="Delete the ``` fence (and any chat text) pasted in by mistake",
            kinds=frozenset({"code", "html", "jsx"}),
            # No string masking here: the fence *is* backticks, which the lexer
            # would read as a template literal and wrongly suppress.
        ),
    ]
