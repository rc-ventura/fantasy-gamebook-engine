"""Round-trip behaviour for every ``StorageBackend`` method.

Run against both ``InMemoryStorage`` and ``JSONStorage`` via the parametrized
``storage`` fixture, except for a couple of backend-specific persistence checks.
"""

from __future__ import annotations

import json

import pytest

from gamebook.domain.models import ArchiveRecord, World
from gamebook.storage.interfaces import StorageBackend


def test_impl_satisfies_protocol(storage) -> None:
    assert isinstance(storage, StorageBackend)


def test_character_roundtrip(storage, sample_character) -> None:
    assert storage.load_character() is None
    storage.save_character(sample_character)
    assert storage.load_character() == sample_character


def test_character_replace(storage, sample_character) -> None:
    storage.save_character(sample_character)
    updated = sample_character.model_copy(update={"gold": 0, "alive": False})
    storage.save_character(updated)
    assert storage.load_character() == updated


def test_world_default_then_roundtrip(storage, sample_world) -> None:
    assert storage.load_world() == World()
    storage.save_world(sample_world)
    assert storage.load_world() == sample_world


def test_events_append_only_and_ordered(storage, sample_events) -> None:
    assert storage.load_events() == []
    for event in sample_events:
        storage.append_event(event)
    assert storage.load_events() == sample_events
    extra = sample_events[0].model_copy(update={"turn": 99})
    storage.append_event(extra)
    assert storage.load_events() == [*sample_events, extra]


def test_summary_roundtrip(storage) -> None:
    assert storage.load_summary() == ""
    storage.save_summary("The hero enters the mountain.")
    assert storage.load_summary() == "The hero enters the mountain."


def test_combat_roundtrip_and_remove(storage, sample_combat) -> None:
    assert storage.load_combat("c1") is None
    storage.save_combat(sample_combat)
    assert storage.load_combat("c1") == sample_combat
    storage.remove_combat("c1")
    assert storage.load_combat("c1") is None
    # Removing a missing combat is a no-op, not an error.
    storage.remove_combat("c1")


def test_archive_rejects_unknown_destination(storage, sample_archive) -> None:
    with pytest.raises(ValueError):
        storage.archive(sample_archive, "nowhere")


def test_save_and_load_slot_restores(storage, sample_character, sample_world) -> None:
    storage.save_character(sample_character)
    storage.save_world(sample_world)
    storage.save_slot("checkpoint")

    hurt = sample_character.model_copy(update={"gold": 0})
    storage.save_character(hurt)
    assert storage.load_character() == hurt

    storage.load_slot("checkpoint")
    assert storage.load_character() == sample_character
    assert storage.load_world() == sample_world


def test_load_missing_slot_raises(storage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.load_slot("does_not_exist")


# --- Backend-specific persistence checks (no read API for archives) ---------


def test_archive_persists_to_json_files(json_storage, sample_archive, tmp_path) -> None:
    json_storage.archive(sample_archive, "graveyard")
    json_storage.archive(sample_archive, "graveyard")
    json_storage.archive(sample_archive, "hall_of_fame")

    graveyard = json.loads((tmp_path / "estado" / "graveyard.json").read_text())
    hall = json.loads((tmp_path / "estado" / "hall_of_fame.json").read_text())

    assert len(graveyard) == 2
    assert len(hall) == 1
    assert ArchiveRecord.model_validate(graveyard[0]) == sample_archive
    assert ArchiveRecord.model_validate(hall[0]) == sample_archive


def test_archive_persists_in_memory(memory_storage, sample_archive) -> None:
    memory_storage.archive(sample_archive, "graveyard")
    memory_storage.archive(sample_archive, "hall_of_fame")
    assert memory_storage._archives["graveyard"] == [sample_archive]
    assert memory_storage._archives["hall_of_fame"] == [sample_archive]
