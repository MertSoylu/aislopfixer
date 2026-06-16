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

from ..models import Category, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule

_I = re.IGNORECASE

# Keep a match only if it sits OUTSIDE a template literal: an even number of
# unescaped backticks precede it. Defends against `// ...` shown inside a `...`.
_BACKTICK = re.compile(r"(?<!\\)`")


def _outside_template(m: re.Match, sf: SourceFile) -> bool:
    return len(_BACKTICK.findall(sf.text[: m.start()])) % 2 == 0


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

_DEBUGGER = re.compile(r"(?m)^[ \t]*debugger\s*;?\s*$")

_DEBUG_LOG = re.compile(
    r"(?im)^[ \t]*console\.(?:log|debug|info)\(\s*"
    r"(?:(['\"`])\s*(?:here|test(?:ing)?|hello(?:\s+world)?|debug|asdf+|qwerty|"
    r"foo|bar|baz|aa+|xxx+|=+|-+|\*+|\?+)\s*\1|\d+)?\s*\)\s*;?\s*$"
)

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


@file_rule
class CodeGenRule(PatternRule):
    category = Category.CODE_SLOP
    patterns = [
        Pattern(
            id="codegen.elision",
            regex=_ELISION,
            severity=Severity.ERROR,
            fixability=Fixability.MANUAL,
            message="Elision marker — real code was dropped from this paste",
            suggested_fix="Restore the omitted code; this file is incomplete",
            guard=_outside_template,
        ),
        Pattern(
            id="codegen.stub_body",
            regex=_STUB_BODY,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Not-implemented stub — function body was never written",
            suggested_fix="Implement the function body",
            guard=_outside_template,
        ),
        Pattern(
            id="codegen.stub_comment",
            regex=_STUB_COMMENT,
            severity=Severity.WARNING,
            fixability=Fixability.MANUAL,
            message="Fill-in-the-blank stub comment standing in for real logic",
            suggested_fix="Replace with the actual implementation",
            guard=_outside_template,
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
            guard=_outside_template,
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
            guard=_outside_template,
        ),
        Pattern(
            id="codegen.restate_comment",
            regex=_RESTATE,
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Comment merely restates the next line of code",
            suggested_fix="Delete the redundant comment or explain *why*, not *what*",
            guard=_outside_template,
        ),
    ]
