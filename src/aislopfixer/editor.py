"""Open a source position in whatever editor this machine actually has.

Every observation already carries ``file:line``, and until now the only thing a
reader could do with it was retype it. Opening it is a one-key job, but it is
one key with two traps:

* a *terminal* editor (``vim``, ``nano``) shares this process's terminal, so it
  has to be run with the TUI suspended or both end up drawing at once;
* a *windowed* editor (``code``, ``subl``) must be launched detached, or the
  TUI blocks until the user closes their editor.

So the resolver reports which kind it found, and refuses to guess when it finds
nothing: the caller falls back to the clipboard and says so, because silently
doing nothing is indistinguishable from a broken key.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys

__all__ = ["EditorCommand", "resolve"]

# Editors that draw in this terminal. Anything here needs App.suspend().
TERMINAL = frozenset({"vim", "nvim", "vi", "nano", "emacs", "helix", "hx",
                      "micro", "kak", "joe", "ne"})
# Tried in order when neither $VISUAL nor $EDITOR is set.
WINDOWED = ("code", "codium", "code-insiders", "cursor", "zed", "subl", "idea")


class EditorCommand:
    """An argv ready to run, plus whether it needs the terminal to itself."""

    __slots__ = ("argv", "terminal", "name")

    def __init__(self, argv: list[str], terminal: bool, name: str) -> None:
        self.argv, self.terminal, self.name = argv, terminal, name


def _position_args(program: str, path: str, line: int) -> list[str]:
    """How this editor spells "…and put the cursor on line N"."""
    stem = os.path.splitext(os.path.basename(program))[0].lower()
    if stem in ("code", "codium", "code-insiders", "cursor", "zed"):
        return ["-g", f"{path}:{line}"]
    if stem in ("subl", "sublime_text", "atom"):
        return [f"{path}:{line}"]
    if stem in ("idea", "pycharm", "webstorm"):
        return ["--line", str(line), path]
    if stem in TERMINAL:
        return [f"+{line}", path]
    # An editor nobody here knows: open the file and skip the line. A wrong
    # position flag is a launch failure, and a launch failure reads as "the key
    # does nothing".
    return [path]


def resolve(path: str, line: int) -> EditorCommand | None:
    """The command that opens ``path`` at ``line``, or ``None`` if there is none.

    ``$VISUAL`` and ``$EDITOR`` win, in that order and with their own arguments
    respected, because a machine that set them has already answered this
    question. Only then do the common windowed editors get tried.
    """
    line = max(1, int(line))
    for var in ("VISUAL", "EDITOR"):
        raw = os.environ.get(var, "").strip()
        if not raw:
            continue
        try:
            parts = shlex.split(raw, posix=sys.platform != "win32")
        except ValueError:
            continue
        if not parts or shutil.which(parts[0]) is None:
            continue
        stem = os.path.splitext(os.path.basename(parts[0]))[0].lower()
        return EditorCommand(
            parts + _position_args(parts[0], path, line),
            terminal=stem in TERMINAL,
            name=stem,
        )
    for program in WINDOWED:
        found = shutil.which(program)
        if found is None:
            continue
        return EditorCommand([found] + _position_args(program, path, line),
                             terminal=False, name=program)
    return None


def launch_detached(command: EditorCommand) -> None:
    """Start a windowed editor without waiting for it."""
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command.argv, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **kwargs)
