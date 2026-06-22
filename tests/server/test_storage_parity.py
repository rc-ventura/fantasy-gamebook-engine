"""Behavioural parity between ``InMemoryStorage`` and ``JSONStorage``.

Proves swap point #1: running an identical sequence of operations against both
backends produces identical observable results, so the in-memory backend is a
faithful stand-in for tests and Postgres can replace JSON later with no other
module changing.
"""

from __future__ import annotations

from typing import Any

from gamebook.storage.in_memory import InMemoryStorage
from gamebook.storage.json_storage import JSONStorage


def _run_sequence(storage, character, world, events, combat) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []

    out.append(("character_empty", storage.load_character()))
    storage.save_character(character)
    out.append(("character", storage.load_character()))

    out.append(("world_default", storage.load_world()))
    storage.save_world(world)
    out.append(("world", storage.load_world()))

    out.append(("events_empty", storage.load_events()))
    for event in events:
        storage.append_event(event)
    out.append(("events", storage.load_events()))

    out.append(("summary_empty", storage.load_summary()))
    storage.save_summary("chapter one")
    out.append(("summary", storage.load_summary()))

    out.append(("combat_empty", storage.load_combat(combat.combat_id)))
    storage.save_combat(combat)
    out.append(("combat", storage.load_combat(combat.combat_id)))
    storage.remove_combat(combat.combat_id)
    out.append(("combat_removed", storage.load_combat(combat.combat_id)))

    return out


def test_in_memory_and_json_are_observationally_identical(
    tmp_path, sample_character, sample_world, sample_events, sample_combat
) -> None:
    memory_results = _run_sequence(
        InMemoryStorage(), sample_character, sample_world, sample_events, sample_combat
    )
    json_results = _run_sequence(
        JSONStorage(str(tmp_path / "estado")),
        sample_character,
        sample_world,
        sample_events,
        sample_combat,
    )
    assert memory_results == json_results


def test_slot_save_restore_parity(
    tmp_path, sample_character, sample_world
) -> None:
    def exercise(storage) -> tuple[Any, Any]:
        storage.save_character(sample_character)
        storage.save_world(sample_world)
        storage.save_slot("slot1")
        storage.save_character(sample_character.model_copy(update={"gold": 0}))
        storage.load_slot("slot1")
        return storage.load_character(), storage.load_world()

    assert exercise(InMemoryStorage()) == exercise(JSONStorage(str(tmp_path / "estado")))
