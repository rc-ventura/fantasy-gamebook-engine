"""Serialization round-trip + invariant guardian coverage for `domain`.

Independent QA coverage of two ``CONTRACTS.md`` global rules:

* **Rule 7 (JSON round-trip):** ``Model.model_validate(json.loads(m.model_dump_json())) == m``
  must hold for *every* domain model -- object -> JSON -> identical object. This
  is what guarantees ``JSONStorage`` (and a future ``PostgresStorage``) can
  faithfully persist and restore state.
* **Invariants live in `domain`:** an out-of-range ``Attribute`` (and the other
  non-negative constraints) can never be *constructed*, so a malformed state can
  never enter the system.

This overlaps the core team's own ``tests/engine/test_domain.py`` on purpose --
QA owns an independent check of the contract regardless of how the models evolve.
"""

from __future__ import annotations

import inspect
import json

import pytest
from pydantic import BaseModel, ValidationError

from gamebook.domain import models as domain_models
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


def _attr(initial: int, current: int | None = None) -> Attribute:
    return Attribute(initial=initial, current=initial if current is None else current)


# A representative, fully-populated instance of every persistent domain model.
def _model_instances() -> list[BaseModel]:
    npc = Npc(name="Old Sage", state="friendly")
    return [
        _attr(12, 9),
        _attr(10, 10),
        _attr(8, 0),
        npc,
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
            known_npcs=[npc],
            flags={"door_open": True, "alarm": False},
            turn=5,
        ),
        Event(
            turn=1,
            type="enter_zone",
            data={"zone": "foothills", "depth": 2, "lit": True},
            timestamp="2026-06-21T10:00:00Z",
        ),
        Enemy(name="Orc", skill=8, stamina=9),
        Combat(
            combat_id="c1",
            enemies=[Enemy(name="Orc", skill=8, stamina=9), Enemy(name="Wolf", skill=6, stamina=5)],
            round=2,
            flee_allowed=True,
            ended=False,
            winner=None,
        ),
        Combat(
            combat_id="c2",
            enemies=[Enemy(name="Dragon", skill=12, stamina=0)],
            round=9,
            flee_allowed=False,
            ended=True,
            winner="hero",
        ),
        ArchiveRecord(
            name="Aldric",
            turns=42,
            outcome="victory",
            location="grey_summit",
            cause=None,
            final_inventory=["crown"],
        ),
        ArchiveRecord(
            name="Borin",
            turns=7,
            outcome="death",
            location="trap_corridor",
            cause="spiked pit",
            final_inventory=[],
        ),
    ]


# --------------------------------------------------------------------------- round-trip
@pytest.mark.parametrize(
    "model", _model_instances(), ids=lambda m: f"{type(m).__name__}"
)
def test_json_round_trip_is_identity(model: BaseModel) -> None:
    """object -> JSON -> object yields an equal object (CONTRACTS rule 7)."""
    restored = type(model).model_validate(json.loads(model.model_dump_json()))
    assert restored == model
    # The serialized form must itself be stable (re-dumping is identical).
    assert restored.model_dump_json() == model.model_dump_json()


def test_every_domain_model_is_covered() -> None:
    """Guard against a new domain model slipping past the round-trip parametrize."""
    declared = {
        obj
        for _name, obj in inspect.getmembers(domain_models, inspect.isclass)
        if issubclass(obj, BaseModel)
        and obj is not BaseModel
        and obj.__module__ == domain_models.__name__
    }
    covered = {type(m) for m in _model_instances()}
    missing = declared - covered
    assert not missing, f"domain models without round-trip coverage: {sorted(c.__name__ for c in missing)}"


# --------------------------------------------------------------------------- invariants
def test_attribute_current_above_initial_raises() -> None:
    with pytest.raises(ValidationError):
        Attribute(initial=10, current=11)


def test_attribute_current_negative_raises() -> None:
    with pytest.raises(ValidationError):
        Attribute(initial=10, current=-1)


def test_attribute_negative_initial_raises() -> None:
    with pytest.raises(ValidationError):
        Attribute(initial=-1, current=-1)


@pytest.mark.parametrize("current", [0, 1, 5, 10])
def test_attribute_valid_bounds_accepted(current: int) -> None:
    assert Attribute(initial=10, current=current).current == current


def test_character_negative_gold_raises() -> None:
    with pytest.raises(ValidationError):
        CharacterSheet(name="x", skill=_attr(10), stamina=_attr(10), luck=_attr(10), gold=-1)


def test_character_negative_provisions_raises() -> None:
    with pytest.raises(ValidationError):
        CharacterSheet(name="x", skill=_attr(10), stamina=_attr(10), luck=_attr(10), provisions=-1)


def test_world_negative_turn_raises() -> None:
    with pytest.raises(ValidationError):
        World(turn=-1)


def test_invalid_attribute_survives_json_reload() -> None:
    """Invariants are enforced on *load*, not just on construction.

    A hand-crafted JSON blob with ``current > initial`` must be rejected by
    ``model_validate`` -- otherwise corrupt persisted state could re-enter the
    engine through storage.
    """
    poisoned = json.dumps({"initial": 5, "current": 99})
    with pytest.raises(ValidationError):
        Attribute.model_validate_json(poisoned)
