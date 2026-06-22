"""Combat lifecycle tests with in-memory storage and a seeded RNG."""

from __future__ import annotations

import random

import pytest

from gamebook.combate.implementation import CombatService
from gamebook.dominio.models import Attribute, CharacterSheet, Enemy
from gamebook.storage.in_memory import InMemoryStorage  # allowed in tests


class ConstRandom:
    """A ``RandomSource`` that always returns the same value (deterministic rounds)."""

    def __init__(self, value: int) -> None:
        self._value = value

    def randint(self, a: int, b: int) -> int:
        return self._value


def make_character(
    *, skill: int = 12, stamina: int = 24, luck: int = 12
) -> CharacterSheet:
    return CharacterSheet(
        name="Hero",
        skill=Attribute(initial=skill, current=skill),
        stamina=Attribute(initial=stamina, current=stamina),
        luck=Attribute(initial=luck, current=luck),
    )


def run_to_end(engine: CombatService, combat_id: str, *, use_luck: bool = False):
    outcome = None
    for _ in range(200):
        outcome = engine.resolve_round(combat_id, use_luck=use_luck)
        if outcome.ended:
            return outcome
    raise AssertionError("combat did not end within the round budget")


def test_hero_wins_full_combat() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=20, stamina=24, luck=12))
    engine = CombatService(storage, random.Random(1))

    combat = engine.start_combat(
        [Enemy(name="Goblin", skill=1, stamina=4)], flee_allowed=True
    )
    outcome = run_to_end(engine, combat.combat_id)

    assert outcome.winner == "hero"
    assert storage.load_character().alive is True

    final = engine.end_combat(combat.combat_id)
    assert final.winner == "hero"
    assert final.rounds >= 1
    assert final.hero_final_stamina == storage.load_character().stamina.current
    # The in-progress combat record is removed on conclusion.
    assert storage.load_combat(combat.combat_id) is None


def test_combat_death_propagates_alive_false() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=1, stamina=4, luck=12))
    engine = CombatService(storage, random.Random(3))

    combat = engine.start_combat(
        [Enemy(name="Dragon", skill=20, stamina=40)], flee_allowed=False
    )
    outcome = run_to_end(engine, combat.combat_id)

    assert outcome.winner == "enemy"
    assert outcome.hero_stamina == 0
    assert storage.load_character().alive is False

    final = engine.end_combat(combat.combat_id)
    assert final.winner == "enemy"
    assert storage.load_character().alive is False


def test_flee_blocked_when_not_allowed() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character())
    engine = CombatService(storage, random.Random(0))

    combat = engine.start_combat(
        [Enemy(name="Orc", skill=8, stamina=9)], flee_allowed=False
    )
    with pytest.raises(ValueError):
        engine.flee(combat.combat_id)


def test_flee_costs_two_stamina_when_allowed() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(stamina=24))
    engine = CombatService(storage, random.Random(0))

    combat = engine.start_combat(
        [Enemy(name="Orc", skill=8, stamina=9)], flee_allowed=True
    )
    result = engine.flee(combat.combat_id)

    assert result.damage_taken == 2
    assert result.hero_stamina == 22
    assert result.ended is True
    assert result.hero_alive is True
    assert storage.load_character().stamina.current == 22


def test_luck_spent_and_decremented_in_round() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=20, stamina=24, luck=12))
    engine = CombatService(storage, random.Random(5))

    # Stamina high enough that the enemy survives a single luck-boosted hit.
    combat = engine.start_combat(
        [Enemy(name="Goblin", skill=1, stamina=30)], flee_allowed=True
    )
    luck_before = storage.load_character().luck.current
    outcome = engine.resolve_round(combat.combat_id, use_luck=True)

    # With skill 20 vs 1 the hero wins (not a tie), so luck is tested and spent.
    assert outcome.hitter == "hero"
    assert outcome.luck_used is not None
    assert storage.load_character().luck.current == luck_before - 1

    final = engine.end_combat(combat.combat_id)
    assert final.luck_spent == 1


def test_in_progress_combat_survives_reload() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=12, stamina=24, luck=12))
    engine = CombatService(storage, random.Random(7))

    combat = engine.start_combat(
        [Enemy(name="Orc", skill=8, stamina=12)], flee_allowed=True
    )
    engine.resolve_round(combat.combat_id, use_luck=False)

    # A brand-new service instance (simulating a restart) can keep fighting the
    # same persisted combat.
    revived = CombatService(storage, random.Random(8))
    persisted = storage.load_combat(combat.combat_id)
    assert persisted is not None
    assert persisted.round == 1
    outcome = revived.resolve_round(combat.combat_id, use_luck=False)
    assert outcome.ended in (True, False)  # it resolves without error


# --- start_combat validation (no soft-lock) ----------------------------------
def test_start_combat_rejects_empty_enemy_list() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character())
    engine = CombatService(storage, random.Random(0))
    with pytest.raises(ValueError):
        engine.start_combat([], flee_allowed=True)


def test_start_combat_rejects_all_dead_enemies() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character())
    engine = CombatService(storage, random.Random(0))
    with pytest.raises(ValueError):
        engine.start_combat(
            [Enemy(name="Corpse", skill=5, stamina=0)], flee_allowed=True
        )


# --- Multi-enemy progression: sequential targeting + win-when-all-dead -------
def test_multi_enemy_sequential_targeting_and_victory() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=20, stamina=24, luck=12))
    # ConstRandom(3): every 2d6 -> 6, so the high-skill hero wins every round and
    # always deals base damage 2 — fully deterministic progression.
    engine = CombatService(storage, ConstRandom(3))

    combat = engine.start_combat(
        [
            Enemy(name="Goblin", skill=1, stamina=4),
            Enemy(name="Rat", skill=1, stamina=4),
        ],
        flee_allowed=False,
    )
    cid = combat.combat_id

    def foe_stamina() -> tuple[int, int]:
        foes = storage.load_combat(cid).enemies
        return foes[0].stamina, foes[1].stamina

    # Round 1: only the first enemy (the active one) takes damage.
    o1 = engine.resolve_round(cid, use_luck=False)
    assert foe_stamina() == (2, 4)
    assert o1.ended is False

    # Round 2: first enemy drops to 0, the second is still untouched, so the
    # combat is NOT over (proves win requires ALL enemies down, not just one).
    o2 = engine.resolve_round(cid, use_luck=False)
    assert foe_stamina() == (0, 4)
    assert o2.ended is False
    assert o2.winner is None

    # Round 3: targeting advances to the second enemy only now the first is dead.
    engine.resolve_round(cid, use_luck=False)
    assert foe_stamina() == (0, 2)

    # Round 4: last enemy down -> hero wins (the all-enemies-dead branch).
    o4 = engine.resolve_round(cid, use_luck=False)
    assert foe_stamina() == (0, 0)
    assert o4.ended is True
    assert o4.winner == "hero"


# --- Enemy-hit + luck modifier branch (damage 1 / 3) -------------------------
def test_enemy_hit_with_lucky_modifier_deals_one() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=1, stamina=24, luck=12))
    engine = CombatService(storage, ConstRandom(3))  # enemy_as 26 vs hero_as 7

    combat = engine.start_combat(
        [Enemy(name="Troll", skill=20, stamina=30)], flee_allowed=False
    )
    outcome = engine.resolve_round(combat.combat_id, use_luck=True)

    # The enemy wins the round; with luck 12 the 2d6=6 luck roll succeeds.
    assert outcome.hitter == "enemy"
    assert outcome.luck_used is not None and outcome.luck_used.success is True
    assert outcome.damage_applied == 1  # lost + lucky -> 1
    assert outcome.hero_stamina == 23
    assert storage.load_character().luck.current == 11


def test_enemy_hit_with_unlucky_modifier_deals_three() -> None:
    storage = InMemoryStorage()
    storage.save_character(make_character(skill=1, stamina=24, luck=3))
    engine = CombatService(storage, ConstRandom(3))  # 2d6=6 luck roll fails vs 3

    combat = engine.start_combat(
        [Enemy(name="Troll", skill=20, stamina=30)], flee_allowed=False
    )
    outcome = engine.resolve_round(combat.combat_id, use_luck=True)

    assert outcome.hitter == "enemy"
    assert outcome.luck_used is not None and outcome.luck_used.success is False
    assert outcome.damage_applied == 3  # lost + unlucky -> 3
    assert outcome.hero_stamina == 21
    assert storage.load_character().luck.current == 2


# --- Fatal flee: hero_alive False + unambiguous enemy winner ------------------
def test_fatal_flee_marks_dead_and_end_combat_reports_enemy_winner() -> None:
    storage = InMemoryStorage()
    # Stamina 2 so the fixed 2 flee-damage is lethal.
    storage.save_character(make_character(stamina=2))
    engine = CombatService(storage, random.Random(0))

    combat = engine.start_combat(
        [Enemy(name="Orc", skill=8, stamina=9)], flee_allowed=True
    )
    result = engine.flee(combat.combat_id)

    assert result.hero_stamina == 0
    assert result.hero_alive is False
    assert storage.load_character().alive is False

    # combat.winner is None (a flee), but the dead hero must surface as a defeat.
    final = engine.end_combat(combat.combat_id)
    assert final.winner == "enemy"
    assert storage.load_combat(combat.combat_id) is None
