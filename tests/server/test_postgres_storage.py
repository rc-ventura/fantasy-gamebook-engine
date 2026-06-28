"""PostgresStorage contract tests — T005 / T007 (FR-003, SC-001, ADR-009).

These tests prove swap boundary #1: running an identical sequence of operations
against ``PostgresStorage`` produces outcomes identical to ``InMemoryStorage``
and ``JSONStorage``, so the consumer (mcp/combat) needs no code change to work
on Postgres.

Requires a live Postgres database.  All tests are **skipped** when ``DATABASE_URL``
is not set in the environment — they run automatically in CI where Postgres is
available and in local dev with ``docker compose up``.

Usage:
    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/gamebook \\
        uv run pytest tests/server/test_postgres_storage.py -v
"""

from __future__ import annotations

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
# Skip sentinel — no DATABASE_URL means no live Postgres
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live Postgres tests (set to run)",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def campaign_id() -> str:
    """Fresh UUID per test — no cleanup needed; FK cascade handles it."""
    return str(uuid.uuid4())


@pytest.fixture
def pg_storage(campaign_id: str):
    """A ``PostgresStorage`` instance scoped to a fresh campaign."""
    from gamebook.storage.postgres import PostgresStorage

    return PostgresStorage(DATABASE_URL, campaign_id)


@pytest.fixture
def sample_character() -> CharacterSheet:
    return CharacterSheet(
        name="Aldric",
        skill=Attribute(initial=11, current=11),
        stamina=Attribute(initial=20, current=18),
        luck=Attribute(initial=9, current=8),
        inventory=["sword", "lantern"],
        gold=15,
        provisions=3,
        conditions=["poisoned"],
        alive=True,
    )


@pytest.fixture
def sample_world() -> World:
    return World(
        current_location="grey_gate",
        visited_locations=["start", "grey_gate"],
        known_npcs=[Npc(name="Old Sage", state="friendly")],
        flags={"door_open": True},
        turn=5,
    )


@pytest.fixture
def sample_events() -> list[Event]:
    return [
        Event(
            turn=1,
            type="enter_zone",
            data={"zone": "foothills"},
            timestamp="2026-06-21T10:00:00Z",
        ),
        Event(
            turn=2,
            type="combat_start",
            data={"enemy": "orc"},
            timestamp="2026-06-21T10:05:00Z",
        ),
    ]


@pytest.fixture
def sample_combat() -> Combat:
    return Combat(
        combat_id="c1",
        enemies=[Enemy(name="Orc", skill=8, stamina=9)],
        round=2,
        flee_allowed=True,
        ended=False,
        winner=None,
    )


@pytest.fixture
def sample_archive() -> ArchiveRecord:
    return ArchiveRecord(
        name="Aldric",
        turns=42,
        outcome="victory",
        location="grey_summit",
        cause=None,
        final_inventory=["crown"],
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_postgres_storage_satisfies_protocol(pg_storage) -> None:
    """PostgresStorage must satisfy the StorageBackend runtime-checkable Protocol."""
    assert isinstance(pg_storage, StorageBackend)


# ---------------------------------------------------------------------------
# Character round-trip (T005 / ADR-009)
# ---------------------------------------------------------------------------


def test_character_initially_none(pg_storage) -> None:
    assert pg_storage.load_character() is None


def test_character_save_and_load(pg_storage, sample_character) -> None:
    pg_storage.save_character(sample_character)
    assert pg_storage.load_character() == sample_character


def test_character_replace(pg_storage, sample_character) -> None:
    pg_storage.save_character(sample_character)
    updated = sample_character.model_copy(update={"gold": 0, "alive": False})
    pg_storage.save_character(updated)
    assert pg_storage.load_character() == updated


# ---------------------------------------------------------------------------
# World round-trip
# ---------------------------------------------------------------------------


def test_world_default_on_empty(pg_storage) -> None:
    assert pg_storage.load_world() == World()


def test_world_save_and_load(pg_storage, sample_world) -> None:
    pg_storage.save_world(sample_world)
    assert pg_storage.load_world() == sample_world


def test_world_flags_round_trip(pg_storage) -> None:
    world = World(flags={"key_obtained": True, "door_open": False}, turn=3)
    pg_storage.save_world(world)
    assert pg_storage.load_world() == world


# ---------------------------------------------------------------------------
# Events (append-only, ordered)
# ---------------------------------------------------------------------------


def test_events_initially_empty(pg_storage) -> None:
    assert pg_storage.load_events() == []


def test_events_append_and_load_ordered(pg_storage, sample_events) -> None:
    for event in sample_events:
        pg_storage.append_event(event)
    assert pg_storage.load_events() == sample_events


def test_events_preserve_insertion_order(pg_storage, sample_events) -> None:
    extra = sample_events[0].model_copy(update={"turn": 99})
    for event in sample_events:
        pg_storage.append_event(event)
    pg_storage.append_event(extra)
    assert pg_storage.load_events() == [*sample_events, extra]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_initially_empty(pg_storage) -> None:
    assert pg_storage.load_summary() == ""


def test_summary_save_and_load(pg_storage) -> None:
    pg_storage.save_summary("The hero enters the mountain.")
    assert pg_storage.load_summary() == "The hero enters the mountain."


def test_summary_replace(pg_storage) -> None:
    pg_storage.save_summary("chapter one")
    pg_storage.save_summary("chapter two")
    assert pg_storage.load_summary() == "chapter two"


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------


def test_combat_initially_none(pg_storage, sample_combat) -> None:
    assert pg_storage.load_combat(sample_combat.combat_id) is None


def test_combat_save_and_load(pg_storage, sample_combat) -> None:
    pg_storage.save_combat(sample_combat)
    assert pg_storage.load_combat(sample_combat.combat_id) == sample_combat


def test_combat_remove(pg_storage, sample_combat) -> None:
    pg_storage.save_combat(sample_combat)
    pg_storage.remove_combat(sample_combat.combat_id)
    assert pg_storage.load_combat(sample_combat.combat_id) is None


def test_combat_remove_missing_is_noop(pg_storage) -> None:
    pg_storage.remove_combat("nonexistent")  # must not raise


def test_multiple_combats_isolated(pg_storage) -> None:
    c1 = Combat(
        combat_id="c1",
        enemies=[Enemy(name="Orc", skill=8, stamina=9)],
    )
    c2 = Combat(
        combat_id="c2",
        enemies=[Enemy(name="Troll", skill=10, stamina=14)],
    )
    pg_storage.save_combat(c1)
    pg_storage.save_combat(c2)
    assert pg_storage.load_combat("c1") == c1
    assert pg_storage.load_combat("c2") == c2
    pg_storage.remove_combat("c1")
    assert pg_storage.load_combat("c1") is None
    assert pg_storage.load_combat("c2") == c2


# ---------------------------------------------------------------------------
# Archive
# ---------------------------------------------------------------------------


def test_archive_unknown_destination_raises(pg_storage, sample_archive) -> None:
    with pytest.raises(ValueError):
        pg_storage.archive(sample_archive, "nowhere")  # type: ignore[arg-type]


def test_archive_graveyard(pg_storage, sample_archive) -> None:
    # Just confirm it doesn't raise; no read API per StorageBackend
    pg_storage.archive(sample_archive, "graveyard")


def test_archive_hall_of_fame(pg_storage, sample_archive) -> None:
    pg_storage.archive(sample_archive, "hall_of_fame")


# ---------------------------------------------------------------------------
# Save / load slot
# ---------------------------------------------------------------------------


def test_slot_save_restore(pg_storage, sample_character, sample_world) -> None:
    pg_storage.save_character(sample_character)
    pg_storage.save_world(sample_world)
    pg_storage.save_summary("chapter one")
    pg_storage.save_slot("checkpoint")

    # Mutate state
    hurt = sample_character.model_copy(update={"gold": 0})
    pg_storage.save_character(hurt)
    pg_storage.save_summary("chapter two")
    assert pg_storage.load_character() == hurt

    # Restore
    pg_storage.load_slot("checkpoint")
    assert pg_storage.load_character() == sample_character
    assert pg_storage.load_world() == sample_world
    assert pg_storage.load_summary() == "chapter one"


def test_slot_missing_raises_file_not_found(pg_storage) -> None:
    with pytest.raises(FileNotFoundError):
        pg_storage.load_slot("does_not_exist")


def test_slot_overwrite(pg_storage, sample_character) -> None:
    pg_storage.save_character(sample_character)
    pg_storage.save_slot("s1")
    updated = sample_character.model_copy(update={"gold": 999})
    pg_storage.save_character(updated)
    pg_storage.save_slot("s1")  # overwrite
    pg_storage.load_slot("s1")
    assert pg_storage.load_character() == updated


# ---------------------------------------------------------------------------
# T007 — Restart-resume (FR-003, SC-001)
# ---------------------------------------------------------------------------


def test_restart_resume_state_intact(campaign_id) -> None:
    """Simulate process restart: open two separate PostgresStorage instances
    with the same campaign_id and verify the second sees what the first wrote.

    This proves FR-003: 'reopen the same campaign; state intact'.
    """
    from gamebook.storage.postgres import PostgresStorage

    # --- Session 1: write state ---
    s1 = PostgresStorage(DATABASE_URL, campaign_id)
    character = CharacterSheet(
        name="Resumed Hero",
        skill=Attribute(initial=10, current=9),
        stamina=Attribute(initial=18, current=15),
        luck=Attribute(initial=8, current=7),
    )
    world = World(current_location="dark_forest", turn=7)
    s1.save_character(character)
    s1.save_world(world)
    s1.save_summary("Reached the dark forest at turn 7.")
    s1.append_event(
        Event(turn=7, type="enter_zone", data={"zone": "dark_forest"},
              timestamp="2026-06-27T12:00:00Z")
    )

    # --- Session 2: open the SAME campaign (simulates process restart) ---
    s2 = PostgresStorage(DATABASE_URL, campaign_id)
    assert s2.load_character() == character
    assert s2.load_world() == world
    assert s2.load_summary() == "Reached the dark forest at turn 7."
    events = s2.load_events()
    assert len(events) == 1
    assert events[0].type == "enter_zone"


# ---------------------------------------------------------------------------
# Behaviour-parity: identical to InMemoryStorage (ADR-009)
# ---------------------------------------------------------------------------


def _run_sequence(storage, character, world, events, combat):
    """Run the canonical sequence used in test_storage_parity.py."""
    out = []

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


def test_postgres_parity_with_in_memory(
    pg_storage, sample_character, sample_world, sample_events, sample_combat
) -> None:
    """PostgresStorage must be observationally identical to InMemoryStorage."""
    from gamebook.storage.in_memory import InMemoryStorage

    memory_results = _run_sequence(
        InMemoryStorage(), sample_character, sample_world, sample_events, sample_combat
    )
    pg_results = _run_sequence(
        pg_storage, sample_character, sample_world, sample_events, sample_combat
    )
    assert memory_results == pg_results


# ---------------------------------------------------------------------------
# Slot restore — clearing state the snapshot didn't have (regression)
# ---------------------------------------------------------------------------


def test_load_slot_resets_world_when_snapshot_had_no_world(pg_storage, sample_world) -> None:
    """Restoring a slot saved before any world existed must reset world to default.

    Regression: ``_restore_snapshot`` upserted ``world`` but never deleted the
    row when the snapshot's world was ``None``, leaving stale world state after
    ``load_slot`` — breaking parity with InMemory/JSON (ADR-009, swap boundary #1,
    "restore to the exact recorded point").
    """
    pg_storage.save_slot("early")  # snapshot taken before any world is saved
    pg_storage.save_world(sample_world)
    assert pg_storage.load_world().current_location == "grey_gate"

    pg_storage.load_slot("early")
    restored = pg_storage.load_world()
    assert restored.current_location == ""
    assert restored.turn == 0
    assert restored.visited_locations == []
