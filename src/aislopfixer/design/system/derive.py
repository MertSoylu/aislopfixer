"""Derive a concrete design system for one project.

Two requirements pull against each other here. The system must be *specific* —
if every project got the same replacement palette the tool would have swapped
one template for another — and it must be *deterministic*, because the
transformer writes these values into source files and a diff that changes
between runs cannot be reviewed.

Both are satisfied by seeding from the project's own identity: its directory
name and package name, hashed with CRC32 (stable across processes and
platforms, unlike ``hash()``). The seed picks an archetype and rotates its hue;
everything downstream is arithmetic. Re-running on the same project reproduces
the system exactly; a different project gets a different one.

Where the project already has a colour of its own — an authored hex, not a
shipped palette shade — that hue wins over the seed. A studio that chose its
red keeps its red; only the *system around it* is rebuilt.
"""

from __future__ import annotations

import json
import os
import re
import zlib
from dataclasses import dataclass, field

from ..models import DesignReport
from . import color as C
from .archetypes import ARCHETYPES, BY_KEY, Archetype

# Type-scale exponents per role, with clamps so a steep ratio (1.5) and a gentle
# one (1.2) both land on usable sizes instead of 8rem headings or 1.3rem ones.
_ROLE_STEPS: dict[str, tuple[float, float, float]] = {
    # role: (exponent, min rem, max rem)
    "display": (4.5, 2.75, 5.0),
    "section": (2.6, 1.75, 3.0),
    "title": (1.6, 1.2, 2.0),
    "lead": (0.9, 1.05, 1.5),
    "body": (0.0, 0.9, 1.15),
    "meta": (-0.8, 0.75, 0.95),
}


@dataclass
class DesignSystem:
    """A resolved, project-specific design system."""

    archetype: Archetype
    seed: int
    accent_hue: float
    inherited_hue: bool                 # True when the project's own hue was kept
    colors: dict[str, str] = field(default_factory=dict)
    sizes: dict[str, str] = field(default_factory=dict)
    leading: dict[str, str] = field(default_factory=dict)
    tracking: dict[str, str] = field(default_factory=dict)
    families: dict[str, str] = field(default_factory=dict)
    bands: dict[str, str] = field(default_factory=dict)
    measures: dict[str, str] = field(default_factory=dict)
    radii: dict[str, str] = field(default_factory=dict)
    shadows: dict[str, str] = field(default_factory=dict)
    durations: dict[str, str] = field(default_factory=dict)
    easings: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.archetype.name

    @property
    def doctrine(self) -> list[str]:
        return self.archetype.doctrine

    def summary(self) -> list[tuple[str, str]]:
        """``(label, value)`` rows for the TUI's system panel."""
        return [
            ("Arketip", f"{self.archetype.name} — {self.archetype.note}"),
            ("Yazı", f"{_first_family(self.families['display'])} / "
                     f"{_first_family(self.families['body'])}"),
            ("Ölçek", f"{self.archetype.ratio}× · "
                      f"{self.sizes['body']} → {self.sizes['display']}"),
            ("Aksan", f"{self.colors['accent']} "
                      f"({'projeden' if self.inherited_hue else 'türetildi'}, "
                      f"{self.accent_hue:.0f}°)"),
            ("Nötr", f"{self.colors['paper']} → {self.colors['ink']} "
                     f"(ton %{self.archetype.neutral_tint * 100:.0f})"),
            ("Ritim", " · ".join(self.bands[k] for k in
                                 ("open", "narrative", "dense", "close"))),
            ("Ölçüler", " · ".join(self.measures[k] for k in
                                   ("read", "narrow", "content", "wide"))),
            ("Biçim", f"panel {self.radii['panel']} · "
                      f"kontrol {self.radii['control']}"),
            ("Hareket", f"{self.durations['tint']} / {self.durations['move']}"),
        ]


def _first_family(stack: str) -> str:
    return stack.split(",")[0].strip().strip('"')


def project_seed(root: str) -> int:
    """A stable integer identity for a project directory."""
    name = os.path.basename(os.path.abspath(root)) or "project"
    pkg = ""
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8") as fh:
            pkg = str(json.load(fh).get("name", ""))
    except (OSError, ValueError):
        pkg = ""
    return zlib.crc32(f"{name}|{pkg}".encode())


_HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")


def inherited_hue(report: DesignReport) -> float | None:
    """The project's own accent hue, if it authored one.

    Only authored values count. A shipped ``indigo-600`` is the thing being
    replaced, so inheriting from it would keep the page exactly where it
    started.
    """
    hues: list[float] = []
    for value in report.palette.get("authored", []):
        for m in _HEX.finditer(value):
            hsl = C.hsl_of(m.group(0))
            if hsl and hsl[1] >= 0.25 and 0.15 <= hsl[2] <= 0.85:
                hues.append(hsl[0])
    if not hues:
        return None
    return sorted(hues)[len(hues) // 2]


def pick_archetype(seed: int, offset: int = 0) -> Archetype:
    """Deterministic archetype for a project; ``offset`` cycles it in the TUI.

    The seed is avalanched before the modulo. CRC32 values of similar short
    strings share low-order structure, and a plain ``seed % 6`` handed two
    sibling project directories the same archetype often enough to notice.
    """
    mixed = seed ^ (seed >> 13)
    mixed = (mixed * 0x9E3779B1) & 0xFFFFFFFF
    return ARCHETYPES[((mixed >> 11) + offset) % len(ARCHETYPES)]


def derive(root: str, report: DesignReport, *, archetype_key: str | None = None,
           offset: int = 0) -> DesignSystem:
    """Build the system this project should have."""
    seed = project_seed(root)
    arch = BY_KEY[archetype_key] if archetype_key in BY_KEY else pick_archetype(seed, offset)

    own = inherited_hue(report)
    if own is not None:
        hue, inherited = own, True
    else:
        # Rotate the archetype's hue by a seeded amount so two projects on the
        # same archetype still do not share a palette.
        hue, inherited = (arch.accent_hue + (seed % 47) - 23) % 360, False

    accent = C.ramp(hue, arch.accent_chroma)
    support = C.ramp((hue + arch.support_offset) % 360, arch.accent_chroma * 0.7)
    neutral = C.neutral_ramp(arch.neutral_hue, arch.neutral_tint)

    paper, ink = neutral[50], neutral[950]
    accent_main = C.readable_on(paper, [accent[600], accent[700], accent[800]], 4.5)
    colors = {
        "paper": paper,
        "shell": neutral[100],
        "sink": neutral[200],
        "rule": neutral[200],
        "ink": ink,
        "ink-muted": C.readable_on(paper, [neutral[700], neutral[800]], 4.5),
        "ink-faint": C.readable_on(paper, [neutral[500], neutral[600]], 3.0),
        "accent": accent_main,
        "accent-strong": accent[800],
        "accent-soft": accent[100],
        # Measured against the accent that was actually chosen, not against a
        # fixed stop: `accent` may have stepped down to 700 or 800 to clear its
        # own contrast target, and a foreground picked for 600 would then be
        # wrong on the colour the buttons really use.
        "on-accent": C.readable_on(accent_main, [neutral[50], neutral[950]], 4.5),
        "support": C.readable_on(paper, [support[700], support[800]], 4.5),
        "support-soft": support[100],
    }

    sizes = {
        role: f"{_clamp(arch.base_size * arch.ratio ** exp, lo, hi):.4g}rem"
        for role, (exp, lo, hi) in _ROLE_STEPS.items()
    }

    return DesignSystem(
        archetype=arch,
        seed=seed,
        accent_hue=hue,
        inherited_hue=inherited,
        colors=colors,
        sizes=sizes,
        leading={
            "display": f"{arch.display_leading}",
            "title": f"{(arch.display_leading + arch.body_leading) / 2:.2f}",
            "body": f"{arch.body_leading}",
        },
        tracking={"display": arch.display_tracking, "body": arch.body_tracking},
        families={
            "display": arch.display_family,
            "body": arch.body_family,
            "mono": arch.mono_family,
        },
        bands=dict(arch.bands),
        measures=dict(arch.measures),
        radii=dict(arch.radii),
        shadows=dict(arch.shadows),
        durations=dict(arch.durations),
        easings=dict(arch.easings),
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
