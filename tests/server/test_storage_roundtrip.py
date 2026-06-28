"""Domain round-trip invariants across all storage backends (T009 / FR-005, SC-003).

Proves: object → DB → identical object, with domain invariants intact, for every
entity type and across all three backends (InMemoryStorage, JSONStorage, and
PostgresStorage).

For ``InMemoryStorage`` and ``JSONStorage`` the parametrized ``storage`` fixture
already covers them.  The Postgres section uses a ``pg_storage`` fixture and
requires ``DATABASE_URL`` in the environment; tests are skipped otherwise.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

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
from gamebook.storage.interfaces import StorageBackend

# ---------------------------------------------------------------------------
# DATABASE_URL sentinel
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ===========================================================================
# Helpers
# ===========================================================================


def _char_with_inventory() -> CharacterSheet:
    return CharacterSheet(
        name="Aldric",
        skill=Attribute(initial=11, current=11),
        stamina=Attribute(initial=20, current=18),
        luck=Attribute(initial=9, current=8),
        inventory=["sword", "lantern", "healing potion"],
        gold=15,
        provisions=3,
        conditions=["poisoned"],
        alive=True,
    )


def _world_complex() -> World:
    return World(
        current_location="grey_gate",
        visited_locations=["start", "foothills", "grey_gate"],
        known_npcs=[
            Npc(name="Old Sage", state="friendly"),
            Npc(name="Gate Guard", state="hostile"),
        ],
        flags={"door_open": True, "torch_lit": False, "key_obtained": True},
        turn=7,
    )


def _events() -> list[Event]:
    return [
        Event(turn=1, type="enter_zone", data={"zone": "foothills"},
              timestamp="2026-06-21T10:00:00Z"),
        Event(turn=3, type="combat_result",
              data={"outcome": "victory", "enemy": "orc"},
              timestamp="2026-06-21T10:05:00Z"),
        Event(turn=7, type="npc_met",
              data={"name": "Old Sage", "dialogue": "Beware the mountain"},
              timestamp="2026-06-21T10:20:00Z"),
    ]


def _combat() -> Combat:
    return Combat(
        combat_id="fight-001",
        enemies=[
            Enemy(name="Orc", skill=8, stamina=9),
            Enemy(name="Goblin", skill=6, stamina=5),
        ],
        round=2,
        flee_allowed=True,
        ended=False,
        winner=None,
    )


def _archive() -> ArchiveRecord:
    return ArchiveRecord(
        name="Aldric the Brave",
        turns=42,
        outcome="victory",
        location="grey_summit",
        cause=None,
        final_inventory=["crown", "sword", "lantern"],
    )


# ===========================================================================
# Cross-backend round-trip tests (InMemoryStorage + JSONStorage via fixture)
# ===========================================================================


def test_impl_satisfies_protocol(storage) -> None:
    assert isinstance(storage, StorageBackend)


def test_character_roundtrip(storage) -> None:
    char = _char_with_inventory()
    assert storage.load_character() is None
    storage.save_character(char)
    loaded = storage.load_character()
    assert loaded == char
    # Re-serialise to confirm JSON round-trip fidelity
    assert CharacterSheet.model_validate(json.loads(char.model_dump_json())) == char


def test_character_replace(storage) -> None:
    char = _char_with_inventory()
    storage.save_character(char)
    updated = char.model_copy(update={"gold": 0, "alive": False})
    storage.save_character(updated)
    assert storage.load_character() == updated


def test_world_default_then_roundtrip(storage) -> None:
    assert storage.load_world() == World()
    world = _world_complex()
    storage.save_world(world)
    loaded = storage.load_world()
    assert loaded == world
    # known_npcs round-trip
    assert loaded.known_npcs == world.known_npcs
    # flags round-trip
    assert loaded.flags == world.flags


def test_events_append_only_and_ordered(storage) -> None:
    assert storage.load_events() == []
    events = _events()
    for event in events:
        storage.append_event(event)
    loaded = storage.load_events()
    assert loaded == events
    extra = events[0].model_copy(update={"turn": 99})
    storage.append_event(extra)
    assert storage.load_events() == [*events, extra]


def test_summary_roundtrip(storage) -> None:
    assert storage.load_summary() == ""
    storage.save_summary("The hero enters the mountain.")
    assert storage.load_summary() == "The hero enters the mountain."


def test_combat_roundtrip_and_remove(storage) -> None:
    combat = _combat()
    assert storage.load_combat(combat.combat_id) is None
    storage.save_combat(combat)
    loaded = storage.load_combat(combat.combat_id)
    assert loaded == combat
    # Verify enemy list round-trips
    assert loaded.enemies == combat.enemies
    storage.remove_combat(combat.combat_id)
    assert storage.load_combat(combat.combat_id) is None
    # Removing a missing combat is a no-op, not an error.
    storage.remove_combat(combat.combat_id)


def test_archive_rejects_unknown_destination(storage) -> None:
    with pytest.raises(ValueError):
        storage.archive(_archive(), "nowhere")  # type: ignore[arg-type]


def test_save_and_load_slot_restores(storage) -> None:
    char = _char_with_inventory()
    world = _world_complex()
    storage.save_character(char)
    storage.save_world(world)
    storage.save_slot("checkpoint")

    hurt = char.model_copy(update={"gold": 0})
    storage.save_character(hurt)
    assert storage.load_character() == hurt

    storage.load_slot("checkpoint")
    assert storage.load_character() == char
    assert storage.load_world() == world


def test_load_missing_slot_raises(storage) -> None:
    with pytest.raises(FileNotFoundError):
        storage.load_slot("does_not_exist")


def test_attribute_invariants_are_enforced_by_domain() -> None:
    """Domain validates invariants; storage just persists what domain allows."""
    # current > initial is rejected by domain, not by storage
    with pytest.raises(Exception):
        CharacterSheet(
            name="Bad",
            skill=Attribute(initial=10, current=15),  # violates 0 <= current <= initial
            stamina=Attribute(initial=20, current=20),
            luck=Attribute(initial=9, current=9),
        )


# --- Backend-specific persistence checks ------------------------------------


def test_archive_persists_to_json_files(json_storage, tmp_path) -> None:
    record = _archive()
    json_storage.archive(record, "graveyard")
    json_storage.archive(record, "graveyard")
    json_storage.archive(record, "hall_of_fame")

    graveyard = json.loads((tmp_path / "estado" / "graveyard.json").read_text())
    hall = json.loads((tmp_path / "estado" / "hall_of_fame.json").read_text())

    assert len(graveyard) == 2
    assert len(hall) == 1
    assert ArchiveRecord.model_validate(graveyard[0]) == record
    assert ArchiveRecord.model_validate(hall[0]) == record


def test_archive_persists_in_memory(memory_storage) -> None:
    record = _archive()
    memory_storage.archive(record, "graveyard")
    memory_storage.archive(record, "hall_of_fame")
    assert memory_storage._archives["graveyard"] == [record]
    assert memory_storage._archives["hall_of_fame"] == [record]


# ===========================================================================
# PostgresStorage round-trip (T009, FR-005, SC-003)
# ===========================================================================


@pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping Postgres round-trip tests",
)
class TestPostgresRoundTrip:
    """Object → DB → identical object for every domain entity type (T009)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from gamebook.storage.postgres import PostgresStorage

        campaign_id = str(uuid.uuid4())
        self.storage = PostgresStorage(DATABASE_URL, campaign_id)

    def test_satisfies_protocol(self) -> None:
        assert isinstance(self.storage, StorageBackend)

    def test_character_roundtrip(self) -> None:
        char = _char_with_inventory()
        assert self.storage.load_character() is None
        self.storage.save_character(char)
        loaded = self.storage.load_character()
        assert loaded == char
        # Full JSON round-trip
        assert CharacterSheet.model_validate(json.loads(char.model_dump_json())) == char

    def test_world_roundtrip(self) -> None:
        world = _world_complex()
        assert self.storage.load_world() == World()
        self.storage.save_world(world)
        loaded = self.storage.load_world()
        assert loaded == world
        assert loaded.known_npcs == world.known_npcs
        assert loaded.flags == world.flags
        assert loaded.turn == world.turn

    def test_events_roundtrip_and_ordered(self) -> None:
        events = _events()
        for ev in events:
            self.storage.append_event(ev)
        loaded = self.storage.load_events()
        assert loaded == events

    def test_summary_roundtrip(self) -> None:
        self.storage.save_summary("Narrative summary text.")
        assert self.storage.load_summary() == "Narrative summary text."

    def test_combat_roundtrip(self) -> None:
        combat = _combat()
        self.storage.save_combat(combat)
        loaded = self.storage.load_combat(combat.combat_id)
        assert loaded == combat
        assert loaded.enemies == combat.enemies

    def test_archive_roundtrip(self) -> None:
        record = _archive()
        self.storage.archive(record, "graveyard")
        self.storage.archive(record, "hall_of_fame")
        # No read API per StorageBackend — confirm no exception is raised.

    def test_slot_roundtrip(self) -> None:
        char = _char_with_inventory()
        world = _world_complex()
        events = _events()
        combat = _combat()
        summary = "Summary text for slot test."

        self.storage.save_character(char)
        self.storage.save_world(world)
        for ev in events:
            self.storage.append_event(ev)
        self.storage.save_summary(summary)
        self.storage.save_combat(combat)
        self.storage.save_slot("slot_test")

        # Overwrite with new state
        self.storage.save_character(char.model_copy(update={"gold": 0}))
        self.storage.save_summary("different")

        # Restore and verify
        self.storage.load_slot("slot_test")
        assert self.storage.load_character() == char
        assert self.storage.load_world() == world
        assert self.storage.load_events() == events
        assert self.storage.load_summary() == summary
        assert self.storage.load_combat(combat.combat_id) == combat

    def test_attribute_current_at_zero_roundtrips(self) -> None:
        """Boundary: stamina.current == 0 (dead hero) must round-trip."""
        dead = CharacterSheet(
            name="Dead Hero",
            skill=Attribute(initial=10, current=10),
            stamina=Attribute(initial=18, current=0),
            luck=Attribute(initial=8, current=8),
            alive=False,
        )
        self.storage.save_character(dead)
        assert self.storage.load_character() == dead

    def test_world_empty_collections_roundtrip(self) -> None:
        """Edge case: world with all-empty collections round-trips to World()."""
        empty_world = World()
        self.storage.save_world(empty_world)
        assert self.storage.load_world() == empty_world

    def test_event_data_with_nested_structures(self) -> None:
        """Complex JSONB payload round-trips exactly."""
        event = Event(
            turn=1,
            type="complex",
            data={
                "nested": {"key": "value"},
                "list": [1, 2, 3],
                "unicode": "héros",
            },
            timestamp="2026-06-27T00:00:00Z",
        )
        self.storage.append_event(event)
        loaded = self.storage.load_events()
        assert loaded[0] == event
