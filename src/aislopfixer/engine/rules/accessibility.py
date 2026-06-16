"""Detect accessibility and meta-tag slop in markup."""

from __future__ import annotations

import re

from ..context import file_kind
from ..models import Category, Fixability, Severity, SourceFile, Finding
from ..registry import file_rule
from ..util import build_finding

_IMG = re.compile(r"<img\b[^>]*?>", re.I | re.S)
_ALT = re.compile(r"\balt\s*=\s*(['\"])(.*?)\1", re.I | re.S)
# Any alt binding counts as present: quoted alt="", JSX/Svelte alt={expr},
# Vue :alt/v-bind:alt (\b covers the colon) and Angular [alt]="expr".
_HAS_ALT = re.compile(r"(?:\balt|\[alt\])\s*=", re.I)
_EMPTY_HEADING = re.compile(r"<h([1-6])\b[^>]*>\s*</h\1>", re.I)
_HTML_TAG = re.compile(r"<html\b[^>]*>", re.I)
_HAS_HTML = re.compile(r"<html\b", re.I)
_HAS_HEAD = re.compile(r"<head\b", re.I)
_HAS_LANG = re.compile(r"\blang\s*=", re.I)
_TITLE = re.compile(r"<title\b[^>]*>\s*(.*?)\s*</title>", re.I | re.S)
_META_DESC = re.compile(r"<meta\b[^>]*name\s*=\s*['\"]description['\"][^>]*>", re.I)
_META_CONTENT = re.compile(r"content\s*=\s*(['\"])(.*?)\1", re.I | re.S)

_GENERIC_ALT = {
    "image", "img", "photo", "picture", "placeholder", "alt text",
    "logo", "icon", "banner", "thumbnail",
}


def _insert_attr_template(tag: str, head_len: int, attr: str) -> str:
    """A PROMPT ``replace_template`` that inserts ``attr`` into a full tag.

    The whole tag is the finding's anchor (``matched_text``), so relocation after
    a prior edit can never land on the wrong element — unlike a bare ``<img``
    anchor, which every image shares. Literal braces in the tag (JSX ``src={x}``)
    are doubled so ``str.format`` leaves them intact and only fills ``{value}``.
    """
    def esc(s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    return esc(tag[:head_len]) + attr + esc(tag[head_len:])


@file_rule
class AccessibilityRule:
    category = Category.ACCESSIBILITY

    def scan(self, sf: SourceFile) -> list[Finding]:
        # Accessibility tells only mean something in markup. Pure code/CSS/Markdown
        # files only carry HTML inside string literals (e.g. an email template in
        # a .js file), where document-level checks produce nothing but noise.
        kind = file_kind(sf.rel_path)
        if kind not in ("html", "jsx"):
            return []

        text = sf.text
        out: list[Finding] = []

        for m in _IMG.finditer(text):
            tag = m.group(0)
            am = _ALT.search(tag)
            if _HAS_ALT.search(tag) is None:  # truly missing — JSX alt={...} counts as present
                out.append(
                    build_finding(
                        sf,
                        rule_id="a11y.img_no_alt",
                        category=self.category,
                        severity=Severity.WARNING,
                        message="<img> missing alt attribute",
                        start=m.start(),
                        end=m.end(),  # whole tag is the anchor (unique relocation)
                        fixability=Fixability.PROMPT,
                        suggested_fix="Add a descriptive alt attribute",
                        replace_template=_insert_attr_template(tag, 4, ' alt="{value}"'),
                        prompt_label="alt text",
                    )
                )
            elif am is not None:  # quoted alt="..."; JSX alt={expr} can't be judged
                val = am.group(2).strip()
                if val.lower() in _GENERIC_ALT:
                    vs = m.start() + am.start(2)
                    ve = m.start() + am.end(2)
                    out.append(
                        build_finding(
                            sf,
                            rule_id="a11y.img_generic_alt",
                            category=self.category,
                            severity=Severity.INFO,
                            message=f"Generic alt text: {val!r}",
                            start=vs,
                            end=ve,
                            fixability=Fixability.PROMPT,
                            suggested_fix="Describe the image specifically",
                            replace_template="{value}",
                            prompt_label="alt text",
                        )
                    )

        for m in _EMPTY_HEADING.finditer(text):
            out.append(
                build_finding(
                    sf,
                    rule_id="a11y.empty_heading",
                    category=self.category,
                    severity=Severity.WARNING,
                    message="Empty heading element",
                    start=m.start(),
                    end=m.end(),
                    fixability=Fixability.PROMPT,
                    suggested_fix="Add content or remove the empty heading",
                    replace_template="{value}",
                    prompt_label="heading content",
                )
            )

        # Document-level checks apply to real HTML documents only. A JSX root
        # (Next.js layout/_document) renders <html>/<head> too, but its title,
        # description and lang come from the framework's metadata API, not markup.
        if kind == "html" and (_HAS_HTML.search(text) or _HAS_HEAD.search(text)):
            if _TITLE.search(text) is None:
                out.append(
                    build_finding(
                        sf,
                        rule_id="a11y.no_title",
                        category=self.category,
                        severity=Severity.WARNING,
                        message="HTML document has no <title>",
                        start=0,
                        end=0,
                        fixability=Fixability.MANUAL,
                        suggested_fix="Add a <title> in <head>",
                    )
                )
            mm = _META_DESC.search(text)
            if mm is None:
                out.append(
                    build_finding(
                        sf,
                        rule_id="a11y.no_meta_desc",
                        category=self.category,
                        severity=Severity.INFO,
                        message='Missing <meta name="description">',
                        start=0,
                        end=0,
                        fixability=Fixability.MANUAL,
                        suggested_fix="Add a meta description",
                    )
                )
            else:
                cm = _META_CONTENT.search(mm.group(0))
                desc = cm.group(2).strip() if cm else ""
                if len(desc) < 20:
                    out.append(
                        build_finding(
                            sf,
                            rule_id="a11y.weak_meta_desc",
                            category=self.category,
                            severity=Severity.INFO,
                            message="Meta description is empty or too short",
                            start=mm.start(),
                            end=mm.end(),
                            fixability=Fixability.MANUAL,
                            suggested_fix="Write a 50-160 character description",
                        )
                    )

        ht = _HTML_TAG.search(text) if kind == "html" else None
        if ht is not None and not _HAS_LANG.search(ht.group(0)):
            out.append(
                build_finding(
                    sf,
                    rule_id="a11y.no_lang",
                    category=self.category,
                    severity=Severity.INFO,
                    message="<html> missing lang attribute",
                    start=ht.start(),
                    end=ht.end(),  # whole tag is the anchor (unique relocation)
                    fixability=Fixability.PROMPT,
                    suggested_fix='Add a language, e.g. lang="en"',
                    replace_template=_insert_attr_template(ht.group(0), 5, ' lang="{value}"'),
                    prompt_label="language code (e.g. en)",
                )
            )
        return out
