"""Project configuration — ``.aislopfixer.toml`` at the scanned root.

Optional; every key has a default. Loaded once per scan by
:func:`aislopfixer.design.project.load_documents`.

```toml
# .aislopfixer.toml
ignore = ["legacy/**", "third_party/**"]   # path globs to skip entirely
disable = ["copy.cta_pair"]                # observation ids to leave out
pages = ["app/(marketing)"]                # measure only this site in the repo
```
"""

from __future__ import annotations

import fnmatch
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = ".aislopfixer.toml"


@dataclass
class Config:
    disable: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    # Path prefixes of the *site* to measure inside a larger repository. Unlike
    # ``ignore`` this does not stop anything being read: components and
    # stylesheets outside it are still parsed, and the pages under it are still
    # expanded with them. See :mod:`aislopfixer.design.scope`.
    pages: tuple[str, ...] = ()

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

        return cls(
            disable=str_list("disable"),
            ignore=str_list("ignore"),
            pages=str_list("pages"),
        )

    def with_pages(self, pages) -> "Config":
        """A copy scoped to ``pages``; the command line wins over the file."""
        from dataclasses import replace as _replace

        from .design.scope import normalise

        found = normalise(pages)
        return _replace(self, pages=found) if found else self

    def observation_disabled(self, obs_id: str) -> bool:
        """True when an observation id matches a ``disable`` prefix."""
        return any(obs_id.startswith(p) for p in self.disable)

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
