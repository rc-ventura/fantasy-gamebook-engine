"""Rules engine tests: notation parsing, ranges, luck decrement, ties, modifiers."""

from __future__ import annotations

import random

import pytest

from gamebook.rules.implementation import (
    apply_luck_modifier,
    generate_attributes,
    resolve_round,
    roll_dice,
)
# Aliased on import: a name starting with ``test_`` would otherwise be collected
# by pytest as a test function (and fail looking for a ``current_luck`` fixture).
from gamebook.rules.implementation import test_luck as run_luck_test


class ConstRandom:
    """A ``RandomSource`` that always returns the same value (forces ties)."""

    def __init__(self, value: int) -> None:
        self._value = value

    def randint(self, a: int, b: int) -> int:
        return self._value


def rng(seed: int = 0) -> random.Random:
    return random.Random(seed)


# --- Dice notation -----------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    ["", "d6", "2x6", "abc", "2d", "6", "2d6++1", "2d0", "0d6", "-2d6", "2d-6"],
)
def test_invalid_notation_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        roll_dice(bad, rng())


def test_roll_dice_positive_modifier() -> None:
    result = roll_dice("2d6+3", rng(1))
    assert len(result.rolls) == 2
    assert all(1 <= face <= 6 for face in result.rolls)
    assert result.total == sum(result.rolls) + 3


def test_roll_dice_negative_modifier() -> None:
    result = roll_dice("1d6-2", rng(1))
    assert result.total == result.rolls[0] - 2


# --- Attribute generation ----------------------------------------------------
def test_generated_attribute_ranges() -> None:
    for seed in range(100):
        gen = generate_attributes(rng(seed))
        assert 7 <= gen.skill.initial <= 12
        assert 14 <= gen.stamina.initial <= 24
        assert 7 <= gen.luck.initial <= 12
        # Fresh attributes start full.
        assert gen.skill.current == gen.skill.initial
        assert gen.stamina.current == gen.stamina.initial
        assert gen.luck.current == gen.luck.initial


# --- Luck test ---------------------------------------------------------------
def test_luck_always_decrements_by_one() -> None:
    for seed in range(50):
        assert run_luck_test(8, rng(seed)).luck_after == 7


def test_luck_uses_2d6_range() -> None:
    for seed in range(100):
        assert 2 <= run_luck_test(12, rng(seed)).roll <= 12


def test_luck_success_follows_roll() -> None:
    for seed in range(50):
        result = run_luck_test(9, rng(seed))
        assert result.success == (result.roll <= 9)


# --- Combat round ------------------------------------------------------------
def test_tie_deals_no_damage() -> None:
    result = resolve_round(10, 10, ConstRandom(3))
    assert result.hitter == "tie"
    assert result.base_damage == 0
    assert result.hero_as == result.enemy_as


def test_hero_wins_with_higher_skill() -> None:
    result = resolve_round(20, 1, ConstRandom(3))
    assert result.hitter == "hero"
    assert result.base_damage == 2


def test_enemy_wins_with_higher_skill() -> None:
    result = resolve_round(1, 20, ConstRandom(3))
    assert result.hitter == "enemy"
    assert result.base_damage == 2


# --- Luck modifier: all four cases -------------------------------------------
def test_luck_modifier_cases() -> None:
    assert apply_luck_modifier("hero", 2, True) == 4   # won + lucky
    assert apply_luck_modifier("hero", 2, False) == 1  # won + unlucky
    assert apply_luck_modifier("enemy", 2, True) == 1  # lost + lucky
    assert apply_luck_modifier("enemy", 2, False) == 3  # lost + unlucky


def test_luck_modifier_rejects_tie() -> None:
    with pytest.raises(ValueError):
        apply_luck_modifier("tie", 2, True)  # type: ignore[arg-type]


# --- Determinism -------------------------------------------------------------
def test_seeded_results_are_reproducible() -> None:
    assert generate_attributes(rng(42)) == generate_attributes(rng(42))
    assert roll_dice("3d6+2", rng(7)) == roll_dice("3d6+2", rng(7))
    assert resolve_round(10, 9, rng(99)) == resolve_round(10, 9, rng(99))
