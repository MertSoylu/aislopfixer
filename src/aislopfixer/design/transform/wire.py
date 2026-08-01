"""Connect the emitted token file to the project so the rewrite takes effect.

Rewriting ``bg-blue-600`` to ``bg-accent`` is only half a change: if nothing
loads the token file, the page renders with no accent at all. So wiring is part
of the transform, not an instruction left to the user — and it goes through the
same :class:`~aislopfixer.design.transform.plan.Edit` path as every class
rewrite, which means the same backup, the same diff preview and the same undo.

Two wirings are handled because two are safe: a ``<link>`` before ``</head>`` in
an HTML page, and an ``@import`` after the Tailwind import in a stylesheet.
A JS/TS entry point is deliberately left alone — the import order there is
bundler-specific and a wrong insertion breaks the build rather than the design.
For those projects the TUI shows the one line to add.
"""

from __future__ import annotations

import os
import re

from ..models import Document
from ..system.emit import SYSTEM_CSS, SYSTEM_DIR
from .plan import Edit, Plan

_HEAD_CLOSE = re.compile(r"</head\s*>", re.I)
_TW_IMPORT = re.compile(r"""@import\s+["']tailwindcss["'][^;]*;""")
_ALREADY = re.compile(re.escape(SYSTEM_DIR) + r"[/\\]" + re.escape(SYSTEM_CSS))


def _href(root: str, from_file: str) -> str:
    """POSIX-style relative path from a source file to the token stylesheet."""
    target = os.path.join(root, SYSTEM_DIR, SYSTEM_CSS)
    rel = os.path.relpath(target, os.path.dirname(os.path.join(root, from_file)))
    return rel.replace(os.sep, "/")


def plan_wiring(root: str, docs: list[Document]) -> Plan:
    """Edits that make the project load the token file."""
    plan = Plan()
    css_done = False
    for doc in docs:
        if _ALREADY.search(doc.text):
            return Plan()          # already wired by an earlier run
    for doc in docs:
        if doc.kind == "style" and not css_done:
            m = _TW_IMPORT.search(doc.text)
            if m is not None:
                href = _href(root, doc.rel_path)
                plan.edits.append(Edit(
                    file=doc.rel_path, abs_path=doc.abs_path,
                    start=m.end(), end=m.end(), old="",
                    new=f'\n@import "{href}";',
                    line=1 + doc.text.count("\n", 0, m.end()),
                    kind="token", note="Sistem dosyası bağlandı", wiring=True,
                ))
                plan.files.add(doc.rel_path)
                css_done = True
                continue
        if doc.kind != "markup" or not doc.rel_path.lower().endswith((".html", ".htm")):
            continue
        m = _HEAD_CLOSE.search(doc.text)
        if m is None:
            continue
        indent = _indent_before(doc.text, m.start())
        href = _href(root, doc.rel_path)
        plan.edits.append(Edit(
            file=doc.rel_path, abs_path=doc.abs_path,
            start=m.start(), end=m.start(), old="",
            new=f'<link rel="stylesheet" href="{href}">\n{indent}',
            line=1 + doc.text.count("\n", 0, m.start()),
            kind="token", note="Sistem dosyası bağlandı", wiring=True,
        ))
        plan.files.add(doc.rel_path)
    return plan


def _indent_before(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    return text[line_start:pos] if text[line_start:pos].isspace() else ""
