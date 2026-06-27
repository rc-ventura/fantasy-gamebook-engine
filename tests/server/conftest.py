"""Shared fixtures for storage, MCP-server, and web API tests."""

from __future__ import annotations

import random
from typing import Any

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


# ---------------------------------------------------------------------------
# Web API test fixtures
# ---------------------------------------------------------------------------

SEED = 42


@pytest.fixture
def engine_storage() -> InMemoryStorage:
    """Fresh in-memory storage for each web API test."""
    return InMemoryStorage()


@pytest.fixture
def engine_server(engine_storage: InMemoryStorage) -> Any:
    """In-process FastMCP server backed by ``InMemoryStorage``.

    Tests import ``gamebook.mcp.server`` (engine internals are allowed in
    tests — ``tests/`` is not ``gamebook_web/``).  This server is injected
    into the FastAPI app via ``mcp_host.set_engine_toolset_factory`` so no
    subprocess is started during API tests.
    """
    from gamebook.combat.implementation import CombatService
    from gamebook.mcp.server import build_server

    rng = random.Random(SEED)
    combat = CombatService(engine_storage, rng)
    return build_server(storage=engine_storage, combat=combat, rng=rng)


@pytest.fixture
def fake_narrator():
    """Default FakeNarrator with an empty queue (uses built-in defaults)."""
    from gamebook_web.harness.base import FakeNarrator
    return FakeNarrator()


@pytest.fixture
def api_client(engine_server: Any, fake_narrator: Any):
    """Synchronous FastAPI TestClient with:
    - In-process engine toolset (no subprocess)
    - FakeNarrator (no LLM)
    - Fresh CampaignRegistry per test

    Routes work identically to production — only the backing implementations differ.
    The ``mcp_host`` factory is patched before the lifespan starts so the lifespan
    does not attempt to spawn a subprocess.
    """
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.sessions.campaign import CampaignRegistry

    # Install in-process toolset factory BEFORE entering the lifespan
    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))

    # Install a fresh registry and the FakeNarrator on app.state so the
    # lifespan does not try to create a real narrator or registry.
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = fake_narrator

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    # Reset after the test
    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None  # type: ignore[assignment]
    app.state.narrator = None  # type: ignore[assignment]
    app.state.engine_toolset = None  # type: ignore[assignment]
