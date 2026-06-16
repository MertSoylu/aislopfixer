"""Detect placeholder text, dummy data and dead links."""

from __future__ import annotations

import re

from ..models import Category, Fixability, Severity, SourceFile
from ..pattern_rule import Pattern, PatternRule
from ..registry import file_rule

_I = re.IGNORECASE

# Markup file kinds where an ``href`` is a real link attribute. A CSS attribute
# selector (``a[href="#"]``) or a ``"#"`` string in JS is not a dead link.
_MARKUP = frozenset({"html", "jsx"})

# ----------------------------------------------------- bracket placeholder gate
# A bracketed token is a *placeholder* only if it reads as human prose
# ("[Your Company Name]", "[Insert Date]"). Framework/code brackets must be
# left alone: route params ([id], [city], [username], [tag], [slug]), Angular
# bindings ([checked], [disabled]), index access ([0], [i]), spread ([...slug]),
# regex char-classes ([a-z], [^>]), destructuring ([a, b]), attribute
# selectors ([type="text"]) and markdown refs/footnotes ([1], [^1]).
_REJECT_CHARS = set('=<>|/\\{}$`"():;#&*+~%')
_RANGE = re.compile(r"[a-z]-[a-z]|[A-Z]-[A-Z]|[0-9]-[0-9]")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")  # JS identifier (camelCase incl.)
_INSTRUCTION = {
    "your", "insert", "enter", "add", "replace", "edit", "change", "update",
    "put", "include", "describe", "write", "fill", "example", "sample",
    "tbd", "placeholder", "todo", "company", "client", "business", "brand",
}


def _is_prose_placeholder(m: re.Match, sf: SourceFile) -> bool:
    # Markdown link syntax, not a placeholder: a closing ``]`` immediately
    # followed by ``(`` (inline link ``[Read More](/x)``), ``[`` (reference link
    # ``[text][ref]``) or ``:`` (link definition ``[Getting Started]: /x``).
    # Use a set, not ``in "([:"``: an empty slice (match at EOF) is a substring
    # of every string and would wrongly reject a trailing ``[Placeholder]``.
    if sf.text[m.end():m.end() + 1] in {"(", "[", ":"}:
        return False
    inner = m.group(0)[1:-1].strip()
    if len(inner) < 2:
        return False
    if any(c in _REJECT_CHARS for c in inner):      # attrs, regex, jsx expr, paths
        return False
    if "..." in inner:                              # spread: [...slug]
        return False
    if inner[0] in "^@.-":                          # footnote/at/leading punct
        return False
    if _RANGE.search(inner):                        # regex char-class range
        return False
    if inner.replace(",", "").replace(" ", "").replace(".", "").isdigit():
        return False                                # numeric refs: [1], [3, 4]
    words = inner.split()
    if len(words) < 2:                              # bareword token -> code, not slop
        return False
    if "," in inner:                                # destructuring / ident list
        toks = [t.strip() for t in inner.split(",") if t.strip()]
        if toks and all(_IDENT.fullmatch(t) for t in toks):
            return False
    first = re.sub(r"[^a-z]", "", words[0].lower())
    if first in _INSTRUCTION:                       # "[Your ...]", "[Insert ...]"
        return True
    return any(ch.isupper() for ch in inner)        # Title/Sentence-case prose


@file_rule
class PlaceholderRule(PatternRule):
    category = Category.PLACEHOLDER
    patterns = [
        Pattern(
            id="placeholder.lorem",
            regex=re.compile(r"\blorem ipsum[^<>\n]*", _I),
            severity=Severity.WARNING,
            fixability=Fixability.AUTO,
            message="Lorem ipsum placeholder text",
            suggested_fix="Remove the placeholder text",
            replacement="",
        ),
        Pattern(
            id="placeholder.bracket",
            regex=re.compile(r"\[[^\[\]\n]{2,60}\]"),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="Bracketed placeholder needs a real value",
            suggested_fix="Replace with real content",
            replace_template="{value}",
            prompt_label="Replacement value",
            guard=_is_prose_placeholder,
        ),
        Pattern(
            id="placeholder.example_domain",
            regex=re.compile(r"https?://(?:www\.)?example\.(?:com|org|net)[^\s\"'<>)]*", _I),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="example.com placeholder URL",
            suggested_fix="Replace with the real URL",
            replace_template="{value}",
            prompt_label="Real URL",
        ),
        Pattern(
            id="placeholder.email",
            regex=re.compile(
                r"\b[\w.+-]+@(?:example\.(?:com|org|net)|yourdomain\.com|"
                r"domain\.com|test\.com|sample\.com|company\.com|email\.com)\b",
                _I,
            ),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="Placeholder email address",
            suggested_fix="Replace with a real email",
            replace_template="{value}",
            prompt_label="Real email",
        ),
        Pattern(
            id="placeholder.phone",
            regex=re.compile(
                r"(?:\+?1[\s.-]?)?\(?555\)?[\s.-]?\d{3}[\s.-]?\d{4}"
                r"|123[\s.-]?456[\s.-]?7890"
                r"|\+?1234567890"
            ),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="Placeholder phone number",
            suggested_fix="Replace with a real phone number",
            replace_template="{value}",
            prompt_label="Real phone",
        ),
        Pattern(
            id="placeholder.name",
            regex=re.compile(r"\bjohn doe\b|\bjane doe\b", _I),
            severity=Severity.INFO,
            fixability=Fixability.PROMPT,
            message="Placeholder person name",
            suggested_fix="Replace with a real name",
            replace_template="{value}",
            prompt_label="Real name",
        ),
        Pattern(
            id="placeholder.company",
            regex=re.compile(r"\bAcme(?:\s+(?:Corp(?:oration)?|Inc|Co|LLC|Company))?\b"),
            severity=Severity.INFO,
            fixability=Fixability.PROMPT,
            message="Placeholder company name ('Acme')",
            suggested_fix="Replace with the real company name",
            replace_template="{value}",
            prompt_label="Real company name",
        ),
        Pattern(
            id="placeholder.address",
            regex=re.compile(
                r"\b1?23\s+(?:Main|Anywhere|Elm)\s+(?:St|Street|Ave|Avenue|Rd|Road)\b",
                _I,
            ),
            severity=Severity.INFO,
            fixability=Fixability.PROMPT,
            message="Placeholder street address",
            suggested_fix="Replace with a real address",
            replace_template="{value}",
            prompt_label="Real address",
        ),
        Pattern(
            id="placeholder.todo",
            regex=re.compile(r"\b(?:TODO|FIXME|XXX|HACK)\b[:\s][^\n]*"),
            severity=Severity.INFO,
            fixability=Fixability.MANUAL,
            message="Unfinished TODO/FIXME marker",
            suggested_fix="Resolve or remove this marker",
        ),
        Pattern(
            id="placeholder.image",
            regex=re.compile(
                r"https?://(?:via\.placeholder\.com|placehold\.(?:it|co)|"
                r"picsum\.photos|placekitten\.com|dummyimage\.com|loremflickr\.com)"
                r"[^\s\"'<>)]*",
                _I,
            ),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="Placeholder image source",
            suggested_fix="Replace with a real image URL",
            replace_template="{value}",
            prompt_label="Real image URL",
        ),
        Pattern(
            id="placeholder.dead_href",
            regex=re.compile(r"href\s*=\s*([\"'])(#!?|)\1"),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="Dead link (empty or '#' href)",
            suggested_fix="Point this link to a real URL",
            replace_template='href="{value}"',
            prompt_label="Real URL",
            group=0,
            kinds=_MARKUP,
        ),
        Pattern(
            id="placeholder.void_href",
            regex=re.compile(r"javascript:void\(0\);?", _I),
            severity=Severity.WARNING,
            fixability=Fixability.PROMPT,
            message="Placeholder javascript:void(0) link",
            suggested_fix="Point this link to a real URL",
            replace_template="{value}",
            prompt_label="Real URL",
            kinds=_MARKUP,
        ),
    ]
