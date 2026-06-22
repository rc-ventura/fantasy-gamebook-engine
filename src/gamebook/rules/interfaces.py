"""Rules engine contracts: the ``RandomSource`` protocol and result types.

``rules`` is the pure, deterministic core of the engine. It knows nothing about
storage, the MCP server, or the AI. Randomness is supplied through the injected
``RandomSource`` protocol so tests can drive it with a seeded ``random.Random``
and get reproducible results.

These result models are intentionally tiny value objects; they only ever travel
*out* of the pure functions in ``implementation.py``.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from gamebook.domain.models import Attribute


@runtime_checkable
class RandomSource(Protocol):
    """A source of randomness. ``random.Random`` satisfies this out of the box."""

    def randint(self, a: int, b: int) -> int:
        """Return a random integer ``N`` such that ``a <= N <= b`` (inclusive)."""
        ...


class DiceResult(BaseModel):
    """The outcome of one dice expression: the individual rolls and their total."""

    rolls: list[int]
    total: int


class GeneratedAttributes(BaseModel):
    """Freshly generated starting attributes for a new hero."""

    skill: Attribute
    stamina: Attribute
    luck: Attribute


class LuckTestResult(BaseModel):
    """The outcome of a luck test; ``luck_after`` is always one less than before."""

    roll: int
    success: bool
    luck_after: int


class RoundResult(BaseModel):
    """The pure math of one combat exchange (no damage applied to state yet)."""

    hero_as: int
    enemy_as: int
    hitter: Literal["hero", "enemy", "tie"]
    base_damage: int  # 2 to the loser, 0 on a tie


__all__ = [
    "RandomSource",
    "DiceResult",
    "GeneratedAttributes",
    "LuckTestResult",
    "RoundResult",
]
