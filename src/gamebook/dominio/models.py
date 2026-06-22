"""Shared domain models (persistent entities) for the gamebook engine.

These pydantic v2 models are the *common language* between modules: anything that
crosses a module boundary or gets stored is expressed with one of these types.
They carry **no behaviour** beyond validation — every cross-module invariant lives
here, so a malformed state object can never be constructed or loaded.

The schema is deliberately close to a future relational layout (Postgres in
Phase 2): scalar fields, simple lists, and small value objects (``Npc``,
``Enemy``) that map ~1:1 to tables/columns.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class Attribute(BaseModel):
    """A game attribute tracking its starting and current value.

    Invariant (enforced here, the single source of truth): ``initial >= 0`` and
    ``0 <= current <= initial``. ``current`` may equal ``initial`` (full) or drop
    to ``0`` (depleted) but never exceed ``initial`` (no over-healing) nor go
    negative.
    """

    initial: int = Field(ge=0)
    current: int

    @model_validator(mode="after")
    def _check_bounds(self) -> Attribute:
        if self.current < 0:
            raise ValueError(f"current must be >= 0, got {self.current}")
        if self.current > self.initial:
            raise ValueError(
                f"current ({self.current}) must not exceed initial ({self.initial})"
            )
        return self


class Npc(BaseModel):
    """A known non-player character: just a name and a free-form state label."""

    name: str
    state: str


class CharacterSheet(BaseModel):
    """The hero's full sheet — the central piece of persistent player state."""

    name: str
    skill: Attribute
    stamina: Attribute
    luck: Attribute
    inventory: list[str] = Field(default_factory=list)
    gold: int = Field(default=0, ge=0)
    provisions: int = Field(default=0, ge=0)
    conditions: list[str] = Field(default_factory=list)
    alive: bool = True


class World(BaseModel):
    """The mutable world state: where the hero is, what they've seen, story flags."""

    current_location: str = ""
    visited_locations: list[str] = Field(default_factory=list)
    known_npcs: list[Npc] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)
    turn: int = Field(default=0, ge=0)


class Event(BaseModel):
    """An append-only chronicle entry (a hard fact that happened on a turn)."""

    turn: int
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str  # ISO-8601 string


class Enemy(BaseModel):
    """An enemy *instance* inside a ``Combat``; ``stamina`` mutates as it takes hits."""

    name: str
    skill: int
    stamina: int


class Combat(BaseModel):
    """The persisted state of an in-progress (or just-ended) fight."""

    combat_id: str
    enemies: list[Enemy]
    round: int = 0
    flee_allowed: bool = True
    ended: bool = False
    winner: Literal["hero", "enemy"] | None = None


class ArchiveRecord(BaseModel):
    """A final-state record for the graveyard (death) or hall of fame (victory)."""

    name: str
    turns: int
    outcome: Literal["death", "victory"]
    location: str
    cause: str | None = None
    final_inventory: list[str] = Field(default_factory=list)


__all__ = [
    "Attribute",
    "Npc",
    "CharacterSheet",
    "World",
    "Event",
    "Enemy",
    "Combat",
    "ArchiveRecord",
]
