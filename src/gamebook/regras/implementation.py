"""Pure rules engine implementation — deterministic functions, RNG injected.

Every function here is pure: given the same ``RandomSource`` sequence it returns
the same result. No I/O, no global state, no knowledge of storage or the AI.
"""

from __future__ import annotations

import re
from typing import Literal

from gamebook.dominio.models import Attribute
from gamebook.regras.interfaces import (
    DiceResult,
    GeneratedAttributes,
    LuckTestResult,
    RandomSource,
    RoundResult,
)

# "NdM", "NdM+K" or "NdM-K" (whitespace tolerated, case-insensitive on the 'd').
_DICE_RE = re.compile(r"^\s*(\d+)\s*[dD]\s*(\d+)\s*([+-]\s*\d+)?\s*$")


def roll_dice(notation: str, rng: RandomSource) -> DiceResult:
    """Roll a dice expression like ``"2d6"``, ``"1d6+6"`` or ``"3d6-2"``.

    ``rolls`` holds each individual die face; ``total`` is their sum plus the
    optional modifier. Invalid notation raises ``ValueError``.
    """
    match = _DICE_RE.match(notation)
    if match is None:
        raise ValueError(f"invalid dice notation: {notation!r}")

    count = int(match.group(1))
    sides = int(match.group(2))
    modifier = int(match.group(3).replace(" ", "")) if match.group(3) else 0

    if count <= 0 or sides <= 0:
        raise ValueError(f"invalid dice notation: {notation!r}")

    rolls = [rng.randint(1, sides) for _ in range(count)]
    return DiceResult(rolls=rolls, total=sum(rolls) + modifier)


def generate_attributes(rng: RandomSource) -> GeneratedAttributes:
    """Roll a new hero's starting attributes (``initial == current`` for each).

    skill = 1d6+6 (7–12), stamina = 2d6+12 (14–24), luck = 1d6+6 (7–12).
    """
    skill = roll_dice("1d6+6", rng).total
    stamina = roll_dice("2d6+12", rng).total
    luck = roll_dice("1d6+6", rng).total
    return GeneratedAttributes(
        skill=Attribute(initial=skill, current=skill),
        stamina=Attribute(initial=stamina, current=stamina),
        luck=Attribute(initial=luck, current=luck),
    )


def test_luck(current_luck: int, rng: RandomSource) -> LuckTestResult:
    """Test the hero's luck: roll 2d6, succeed if ``roll <= current_luck``.

    Luck is rolled on **2d6** (range 2–12), not 1d6 — luck sits at 7–12, so a 1d6
    test could never fail. ``luck_after`` is ``current_luck - 1`` *always*, win or
    lose: testing luck spends it.
    """
    roll = roll_dice("2d6", rng).total
    return LuckTestResult(
        roll=roll,
        success=roll <= current_luck,
        luck_after=current_luck - 1,
    )


def resolve_round(
    hero_skill: int, enemy_skill: int, rng: RandomSource
) -> RoundResult:
    """Resolve one combat exchange (no state mutation — pure math only).

    Each side's attack strength (AS) = its skill + 2d6. The higher AS hits for a
    base damage of 2; an equal AS is a tie and deals 0.
    """
    hero_as = hero_skill + roll_dice("2d6", rng).total
    enemy_as = enemy_skill + roll_dice("2d6", rng).total

    if hero_as > enemy_as:
        hitter: Literal["hero", "enemy", "tie"] = "hero"
        base_damage = 2
    elif enemy_as > hero_as:
        hitter = "enemy"
        base_damage = 2
    else:
        hitter = "tie"
        base_damage = 0

    return RoundResult(
        hero_as=hero_as,
        enemy_as=enemy_as,
        hitter=hitter,
        base_damage=base_damage,
    )


def apply_luck_modifier(
    hitter: Literal["hero", "enemy"],
    base_damage: int,
    luck_success: bool,
) -> int:
    """Adjust a hit's damage by the result of a luck test.

    The four cases (final damage, not a delta — ``base_damage`` is the unmodified
    reference and is intentionally not added on):

    * hero hit (won the exchange) + lucky  -> 4
    * hero hit (won the exchange) + unlucky -> 1
    * enemy hit (hero lost)       + lucky  -> 1  (hero softened the blow)
    * enemy hit (hero lost)       + unlucky -> 3  (the blow hurt more)
    """
    if hitter == "hero":
        return 4 if luck_success else 1
    if hitter == "enemy":
        return 1 if luck_success else 3
    raise ValueError(f"luck modifier requires a hitter of 'hero' or 'enemy', got {hitter!r}")


__all__ = [
    "roll_dice",
    "generate_attributes",
    "test_luck",
    "resolve_round",
    "apply_luck_modifier",
]
