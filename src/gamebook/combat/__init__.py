"""Combat lifecycle: open a fight, resolve rounds, flee, conclude.

Stateless with respect to the UI: the harness decides ``use_luck`` per round and
this module just applies the rules and persists state. Depends on the ``regras``
core and ``dominio`` types; the ``StorageBackend`` is injected and referenced only
for typing (no runtime storage coupling).
"""

from gamebook.combate.implementation import CombatService
from gamebook.combate.interfaces import (
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
