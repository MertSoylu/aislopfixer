"""Design-system derivation: turn a measurement into something to replace it with.

Detection without a proposal is only half the job — telling a project its
palette is unauthored is useless if the only alternative on offer is another
default. :mod:`archetypes` holds the hand-written positions a system can take,
:mod:`derive` picks and tunes one deterministically for a given project, and
:mod:`emit` writes it out as real code.
"""

from .archetypes import ARCHETYPES, BY_KEY, Archetype
from .derive import DesignSystem, derive, pick_archetype, project_seed
from .emit import detect_tailwind, token_css, wiring_hint, write_system

__all__ = [
    "ARCHETYPES", "BY_KEY", "Archetype", "DesignSystem", "derive",
    "pick_archetype", "project_seed", "detect_tailwind", "token_css",
    "wiring_hint", "write_system",
]
