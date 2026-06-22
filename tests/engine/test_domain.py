"""Domain model tests: invariant enforcement and JSON round-trip parity."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from gamebook.domain.models import (
    ArchiveRecord,
    Attribute,
    CharacterSheet,
    Combat,
    Enemy,
    Event,
    Npc,
    World,
)


def _attr(initial: int = 10, current: int | None = None) -> Attribute:
    return Attribute(initial=initial, current=initial if current is None else current)


# --- Attribute invariants ----------------------------------------------------
def test_attribute_current_above_initial_raises() -> None:
    with pytest.raises(ValidationError):
        Attribute(initial=10, current=12)


def test_attribute_current_negative_raises() -> None:
    with pytest.raises(ValidationError):
        Attribute(initial=10, current=-1)


def test_attribute_negative_initial_raises() -> None:
    with pytest.raises(ValidationError):
        Attribute(initial=-1, current=-1)


@pytest.mark.parametrize("current", [0, 5, 10])
def test_attribute_valid_bounds_accepted(current: int) -> None:
    attr = Attribute(initial=10, current=current)
    assert attr.current == current


# --- CharacterSheet / World non-negative invariants --------------------------
def test_character_negative_gold_raises() -> None:
    with pytest.raises(ValidationError):
        CharacterSheet(
            name="x", skill=_attr(), stamina=_attr(), luck=_attr(), gold=-1
        )


def test_character_negative_provisions_raises() -> None:
    with pytest.raises(ValidationError):
        CharacterSheet(
            name="x", skill=_attr(), stamina=_attr(), luck=_attr(), provisions=-1
        )


def test_world_negative_turn_raises() -> None:
    with pytest.raises(ValidationError):
        World(turn=-1)


# --- JSON round-trip: object -> JSON -> identical object ----------------------
def _sample_models() -> list[object]:
    return [
        _attr(12, 9),
        Npc(name="Old Sage", state="friendly"),
        CharacterSheet(
            name="Aldric",
            skill=_attr(11, 11),
            stamina=_attr(20, 18),
            luck=_attr(9, 8),
            inventory=["sword", "lantern"],
            gold=15,
            provisions=3,
            conditions=["poisoned"],
            alive=True,
        ),
        World(
            current_location="grey_gate",
            visited_locations=["start", "grey_gate"],
            known_npcs=[Npc(name="Old Sage", state="friendly")],
            flags={"door_open": True},
            turn=5,
        ),
        Event(
            turn=1,
            type="enter_zone",
            data={"zone": "foothills", "depth": 2},
            timestamp="2026-06-21T10:00:00Z",
        ),
        Enemy(name="Orc", skill=8, stamina=9),
        Combat(
            combat_id="c1",
            enemies=[Enemy(name="Orc", skill=8, stamina=9)],
            round=2,
            flee_allowed=True,
            ended=False,
            winner=None,
        ),
        ArchiveRecord(
            name="Aldric",
            turns=42,
            outcome="victory",
            location="grey_summit",
            cause=None,
            final_inventory=["crown"],
        ),
    ]


@pytest.mark.parametrize("model", _sample_models(), ids=lambda m: type(m).__name__)
def test_json_round_trip(model: object) -> None:
    restored = type(model).model_validate(json.loads(model.model_dump_json()))
    assert restored == model
