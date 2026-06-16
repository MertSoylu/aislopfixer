"""Project-local allowlist of user-confirmed false positives.

When the user marks a finding as "not slop", its ``(rule_id, matched_text)``
signature is persisted to ``<root>/.aislopfixer/allowlist.json``. Every later scan
of the same project drops any finding matching a stored signature, so legitimate
content the user has already vetted (framework tokens like ``[id]``/``[city]``,
a phrase that only *looks* like a buzzword, an intentional duplicate block) is
never re-flagged. The signature is the matched text, not a line number, so the
suppression survives edits and applies everywhere the same token appears.

The file used to live at ``<root>/.aislopfixerignore.json``; that legacy location
is still read (and transparently migrated on the next save) so existing projects
keep their vetted signatures.
"""

from __future__ import annotations

import json
from pathlib import Path

from .engine.models import Finding

FILENAME = ".aislopfixer/allowlist.json"
LEGACY_FILENAME = ".aislopfixerignore.json"


def _signature(rule_id: str, value: str) -> tuple[str, str]:
    return (rule_id, value)


class Allowlist:
    """Loads, queries and persists the per-project false-positive allowlist."""

    def __init__(self, root: str) -> None:
        self.path = Path(root) / FILENAME
        self._legacy = Path(root) / LEGACY_FILENAME
        self._entries: list[dict] = []
        self._keys: set[tuple[str, str]] = set()
        self._load()

    # --------------------------------------------------------------- load / save
    def _load(self) -> None:
        for src in (self.path, self._legacy):
            try:
                data = json.loads(src.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for e in data.get("entries", []):
                rid, val = e.get("rule_id", ""), e.get("value", "")
                key = _signature(rid, val)
                if key not in self._keys:
                    self._entries.append(e)
                    self._keys.add(key)

    def _save(self) -> None:
        data = {"version": 1, "entries": self._entries}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass  # best-effort; a read-only project just won't persist

    # -------------------------------------------------------------------- query
    def contains(self, f: Finding) -> bool:
        return _signature(f.rule_id, f.matched_text) in self._keys

    def filter(self, findings: list[Finding]) -> list[Finding]:
        """Drop findings the user already confirmed as not-slop."""
        return [f for f in findings if not self.contains(f)]

    # ------------------------------------------------------------------- mutate
    def add(self, f: Finding) -> bool:
        """Record a finding's signature as a confirmed false positive.

        Returns True if newly added, False if it was already present.
        """
        key = _signature(f.rule_id, f.matched_text)
        if key in self._keys:
            return False
        self._keys.add(key)
        self._entries.append(
            {
                "rule_id": f.rule_id,
                "value": f.matched_text,
                "category": f.category.value,
                "message": f.message,
            }
        )
        self._save()
        return True

    def __len__(self) -> int:
        return len(self._keys)
