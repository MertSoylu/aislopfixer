"""Detect image-accessibility slop in markup.

Deliberately narrow: generic document-level lint (missing <title>, meta
description, lang attribute, empty headings) is *not* AI slop — modern
scaffolds and generators get those right, and flagging them is SEO-linter
noise. What still ships broken is image alt text: images rendered from data
in generated JSX/HTML with no ``alt`` at all, or a lazy generic one
("image", "logo") that a model stamped in without looking at the picture.
"""

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
        # a .js file), where these checks produce nothing but noise.
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
        return out
