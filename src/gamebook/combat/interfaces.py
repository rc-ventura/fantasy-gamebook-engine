"""Combat lifecycle contracts: result value objects + the ``CombatEngine`` protocol.

This module is part of the combat *interface* surface. It depends only on
``domain`` value objects (``Combat``, ``Enemy``) and defines the result types the
engine returns to a harness. It must never import a concrete storage backend.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from gamebook.domain.models import Combat, Enemy


class LuckUse(BaseModel):
    """Whether luck was tested this round and how it landed."""

    roll: int
    success: bool


class RoundOutcome(BaseModel):
    """The full result of one resolved combat round, after damage is applied."""

    hero_as: int
    enemy_as: int
    hitter: Literal["hero", "enemy", "tie"]
    damage_applied: int
    hero_stamina: int
    enemy_stamina: int
    luck_used: LuckUse | None = None
    ended: bool = False
    winner: Literal["hero", "enemy"] | None = None


class FleeResult(BaseModel):
    """The result of fleeing: a fixed 2 damage and the combat ends.

    ``hero_alive`` distinguishes a safe escape from a fatal one — it is ``False``
    when the 2 flee-damage dropped the hero to 0 stamina.
    """

    damage_taken: int = 2
    hero_stamina: int
    ended: bool = True
    hero_alive: bool = True


class FinalResult(BaseModel):
    """The summary handed back when a combat is concluded."""

    winner: Literal["hero", "enemy"] | None
    hero_final_stamina: int
    luck_spent: int
    rounds: int
    drops: list[str] | None = None


@runtime_checkable
class CombatEngine(Protocol):
    """The combat lifecycle: start a fight, resolve rounds, flee, and conclude."""

    def start_combat(self, enemies: list[Enemy], flee_allowed: bool) -> Combat:
        """Create and persist a fresh combat; return its initial state."""
        ...

    def resolve_round(self, combat_id: str, use_luck: bool) -> RoundOutcome:
        """Resolve one exchange, apply damage, persist, and report the outcome."""
        ...

    def flee(self, combat_id: str) -> FleeResult:
        """Flee the combat (only if allowed), taking 2 damage; ends with no winner."""
        ...

    def end_combat(self, combat_id: str) -> FinalResult:
        """Conclude the combat, finalise the sheet, and remove the in-progress record."""
        ...


__all__ = [
    "LuckUse",
    "RoundOutcome",
    "FleeResult",
    "FinalResult",
    "CombatEngine",
]
