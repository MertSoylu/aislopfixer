"""AI-generated Markdown/docs structure tells (``.md`` / ``.mdx`` content files).

README/CLAUDE/LICENSE-style meta docs are already skipped by the scanner, so this
targets prose content files. Matches inside fenced code blocks are ignored
(tutorials legitimately show these shapes as examples):

* **emoji-prefixed headers** — ``## 🚀 Features`` (AUTO: strip the leading emoji).
* **boilerplate sections** — bare ``## Conclusion`` / ``## Key Takeaways`` /
  ``## TL;DR`` headings (end-anchored, so "## Conclusion of the war" is fine).
* **bold-lead bullet lists** — a run of ``- **Term:** explanation`` items; only
  flagged as a whole list (≥4 bullets, ≥75% bold-lead), never a lone bullet.
* **checkmark bullet lists** — ``- ✅ Fast`` decorations (≥3 per file; AUTO strip).
  GitHub task-list checkboxes ``- [ ]`` / ``- [x]`` never match.
* **scaffolding lead-ins** — ``Here is a breakdown of …`` announcing a list
  (lead-in and scaffolding noun must co-occur within ~40 chars).
"""

from __future__ import annotations

import re

from ..context import _MD_FENCE, file_kind, in_any, prose_regions
from ..models import Category, Finding, Fixability, Severity, SourceFile
from ..registry import file_rule
from ..util import build_finding

_I = re.IGNORECASE

_EMOJI = (
    "[\U0001f000-\U0001faff\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff✅✨⭐❤]"
)

_EMOJI_HEADER = re.compile(r"(?m)^#{1,6}[ \t]+(" + _EMOJI + r"(?:️)?[ \t]*)")
_BOILERPLATE = re.compile(
    r"(?im)^#{1,6}[ \t]+"
    r"(?:Conclusion|Key Takeaways?|Final Thoughts?|TL;?DR|In Summary|Wrapping Up)"
    r"[ \t]*$"
)
_CHECK_BULLET = re.compile(r"(?m)^[ \t]*[-*+][ \t]+([✅✔☑✨⭐](?:️)?[ \t])")
_SCAFFOLD = re.compile(
    r"(?i)\b(?:here(?:'s| is| are)|below (?:is|are|you'll find)|"
    r"let's (?:dive|take a look))\b[^.\n]{0,40}\b"
    r"(?:breakdown|overview|rundown|step-by-step|comprehensive|"
    r"everything you need|deep dive|walkthrough)\b"
)

# Bullet-list run detection for the bold-lead listicle shape.
_BULLET_LINE = re.compile(r"^[ \t]*[-*+][ \t]+\S")
_BOLD_LEAD = re.compile(
    r"^[ \t]*[-*+][ \t]+\*\*[^*\n]{1,40}?\*\*[ \t]*[:：][ \t]+\S"
    r"|^[ \t]*[-*+][ \t]+\*\*[^*\n]{1,40}?[:：]\*\*[ \t]+\S"
)
_CHECK_COUNT_GATE = 3
_BOLD_RUN_MIN = 4
_BOLD_RATIO = 0.75


@file_rule
class MarkdownTellRule:
    category = Category.CODE_SLOP

    def scan(self, sf: SourceFile) -> list[Finding]:
        if file_kind(sf.rel_path) != "md":
            return []
        text = sf.text
        fences = [(m.start(), m.end()) for m in _MD_FENCE.finditer(text)]

        def in_fence(p: int) -> bool:
            return any(a <= p < b for a, b in fences)

        out: list[Finding] = []

        for m in _EMOJI_HEADER.finditer(text):
            if in_fence(m.start()):
                continue
            out.append(
                build_finding(
                    sf,
                    rule_id="md.emoji_header",
                    category=self.category,
                    severity=Severity.INFO,
                    message="Decorative emoji in heading — AI docs signature",
                    start=m.start(1),
                    end=m.end(1),
                    fixability=Fixability.AUTO,
                    suggested_fix="Remove the decorative emoji",
                    replacement="",
                )
            )

        for m in _BOILERPLATE.finditer(text):
            if in_fence(m.start()):
                continue
            out.append(
                build_finding(
                    sf,
                    rule_id="md.boilerplate_section",
                    category=self.category,
                    severity=Severity.INFO,
                    message="Boilerplate AI section heading",
                    start=m.start(),
                    end=m.end(),
                    fixability=Fixability.MANUAL,
                    suggested_fix="Cut or rewrite this filler section",
                )
            )

        checks = [m for m in _CHECK_BULLET.finditer(text) if not in_fence(m.start())]
        if len(checks) >= _CHECK_COUNT_GATE:
            for m in checks:
                out.append(
                    build_finding(
                        sf,
                        rule_id="md.checkmark_bullets",
                        category=self.category,
                        severity=Severity.INFO,
                        message="Checkmark-emoji bullet — AI feature-list decoration",
                        start=m.start(1),
                        end=m.end(1),
                        fixability=Fixability.AUTO,
                        suggested_fix="Remove the decorative emoji",
                        replacement="",
                    )
                )

        regions = prose_regions(text, "md")
        for m in _SCAFFOLD.finditer(text):
            if in_fence(m.start()) or not in_any(regions, m.start(), m.end()):
                continue
            out.append(
                build_finding(
                    sf,
                    rule_id="md.scaffolding_leadin",
                    category=self.category,
                    severity=Severity.INFO,
                    message="Listicle scaffolding lead-in",
                    start=m.start(),
                    end=m.end(),
                    fixability=Fixability.MANUAL,
                    suggested_fix="Drop the announcement and show the content",
                )
            )

        out.extend(self._bold_lead_runs(sf, fences))
        return out

    def _bold_lead_runs(self, sf: SourceFile, fences: list[tuple[int, int]]) -> list[Finding]:
        """Flag the start of any bullet run that is mostly ``- **Term:** …``."""
        text = sf.text
        out: list[Finding] = []
        run: list[tuple[int, bool]] = []  # (line_start_offset, is_bold_lead)
        offset = 0

        def in_fence(p: int) -> bool:
            return any(a <= p < b for a, b in fences)

        def flush() -> None:
            if len(run) >= _BOLD_RUN_MIN:
                bold = sum(1 for _, b in run if b)
                if bold / len(run) >= _BOLD_RATIO:
                    start = run[0][0]
                    out.append(
                        build_finding(
                            sf,
                            rule_id="md.bold_lead_list",
                            category=self.category,
                            severity=Severity.INFO,
                            message=(
                                f"Bold-lead bullet list ({bold}/{len(run)} items) "
                                "— AI feature-list shape"
                            ),
                            start=start,
                            end=start,
                            fixability=Fixability.MANUAL,
                            suggested_fix="Rewrite as prose or plain bullets",
                        )
                    )
            run.clear()

        for line in text.splitlines(keepends=True):
            stripped = line.rstrip("\n")
            if _BULLET_LINE.match(stripped) and not in_fence(offset):
                run.append((offset, bool(_BOLD_LEAD.match(stripped))))
            else:
                flush()
            offset += len(line)
        flush()
        return out
