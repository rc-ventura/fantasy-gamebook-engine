"""Combat lifecycle: open a fight, resolve rounds, flee, conclude.

Stateless with respect to the UI: the harness decides ``use_luck`` per round and
this module just applies the rules and persists state. Depends on the ``rules``
core and ``domain`` types; the ``StorageBackend`` is injected and referenced only
for typing (no runtime storage coupling).
"""

from gamebook.combat.implementation import CombatService
from gamebook.combat.interfaces import (
    CombatEngine,
    FinalResult,
    FleeResult,
    LuckUse,
    RoundOutcome,
)

__all__ = [
    "CombatEngine",
    "CombatService",
    "LuckUse",
    "RoundOutcome",
    "FleeResult",
    "FinalResult",
]
