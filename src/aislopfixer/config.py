"""Project configuration — ``.aislopfixer.toml`` at the scanned root.

Optional; every key has a default, and CLI flags always win over the file.
Loaded once per scan inside :func:`aislopfixer.pipeline.scan_project`, so the
TUI and headless mode honor the same config.

```toml
# .aislopfixer.toml
disable = ["design.emoji_ui", "buzzword.delve"]  # rule-id prefixes to turn off
ignore = ["legacy/**", "third_party/**"]          # path globs to skip entirely
fail_on = "error"          # headless exit-code threshold (info|warning|error|never)
min_confidence = 0.5       # headless reporting floor, 0..1
```
"""

from __future__ import annotations

import fnmatch
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = ".aislopfixer.toml"

_VALID_FAIL_ON = {"info", "warning", "error", "never"}


@dataclass
class Config:
    disable: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    fail_on: str | None = None
    min_confidence: float | None = None

    @classmethod
    def load(cls, root: str) -> "Config":
        """Read ``<root>/.aislopfixer.toml``; missing file → all defaults."""
        path = Path(root) / CONFIG_NAME
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, tomllib.TOMLDecodeError) as exc:
            print(f"aislopfixer: ignoring bad {CONFIG_NAME}: {exc}", file=sys.stderr)
            return cls()

        def str_list(key: str) -> tuple[str, ...]:
            val = data.get(key, [])
            if isinstance(val, list) and all(isinstance(x, str) for x in val):
                return tuple(val)
            print(
                f"aislopfixer: {CONFIG_NAME}: {key!r} must be a list of strings",
                file=sys.stderr,
            )
            return ()

        fail_on = data.get("fail_on")
        if fail_on is not None and fail_on not in _VALID_FAIL_ON:
            print(
                f"aislopfixer: {CONFIG_NAME}: fail_on must be one of "
                f"{sorted(_VALID_FAIL_ON)}",
                file=sys.stderr,
            )
            fail_on = None

        min_conf = data.get("min_confidence")
        if min_conf is not None and not (
            isinstance(min_conf, (int, float)) and 0.0 <= min_conf <= 1.0
        ):
            print(
                f"aislopfixer: {CONFIG_NAME}: min_confidence must be 0..1",
                file=sys.stderr,
            )
            min_conf = None

        return cls(
            disable=str_list("disable"),
            ignore=str_list("ignore"),
            fail_on=fail_on,
            min_confidence=None if min_conf is None else float(min_conf),
        )

    def rule_disabled(self, rule_id: str) -> bool:
        return any(rule_id.startswith(p) for p in self.disable)

    def path_ignored(self, rel_path: str) -> bool:
        """Match ``rel_path`` (either separator) against the ignore globs.

        A glob matches the path itself or any parent directory, so a plain
        ``legacy`` entry skips the whole tree without needing ``legacy/**``.
        """
        if not self.ignore:
            return False
        norm = rel_path.replace("\\", "/")
        parts = norm.split("/")
        prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
        return any(
            fnmatch.fnmatch(candidate, pat)
            for pat in self.ignore
            for candidate in prefixes
        )
