"""Shared fixtures for storage and MCP-server tests."""

from __future__ import annotations

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
from gamebook.storage.in_memory import InMemoryStorage
from gamebook.storage.json_storage import JSONStorage


@pytest.fixture(params=["memory", "json"])
def storage(request: pytest.FixtureRequest, tmp_path):
    """A ``StorageBackend`` instance, run once per implementation.

    Tests using this fixture run against both ``InMemoryStorage`` and
    ``JSONStorage`` to prove behavioural parity (swap point #1).
    """
    if request.param == "memory":
        return InMemoryStorage()
    return JSONStorage(str(tmp_path / "estado"))


@pytest.fixture
def json_storage(tmp_path) -> JSONStorage:
    return JSONStorage(str(tmp_path / "estado"))


@pytest.fixture
def memory_storage() -> InMemoryStorage:
    return InMemoryStorage()


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
