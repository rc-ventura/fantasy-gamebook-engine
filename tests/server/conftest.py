"""Shared fixtures for storage, MCP-server, and web API tests."""

from __future__ import annotations

import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

# The web API auth seam is fail-closed by default (T030/T031, ADR-022): without
# GAMEBOOK_DEV_MODE the dev stub rejects every request and the app refuses to
# start.  The server test-suite runs against the dev stub, so enable dev mode for
# the whole suite here (before any test imports the app).  Tests that exercise
# production/fail-closed behaviour override this explicitly via monkeypatch.
os.environ.setdefault("GAMEBOOK_DEV_MODE", "1")

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

    Uses a storage_factory that always returns the same InMemoryStorage instance,
    so all tool calls within a test share the same in-memory state regardless of
    the campaign_id passed (ADR-018: factory-based multi-tenancy).
    """
    from gamebook.mcp.server import build_server

    rng = random.Random(SEED)
    return build_server(storage_factory=lambda _cid: engine_storage, rng=rng)


@pytest.fixture
def fake_narrator():
    """Default FakeNarrator with an empty queue (uses built-in defaults)."""
    from gamebook_web.harness.narrator import FakeNarrator
    return FakeNarrator()


class RecordingAccountRepository:
    """Functional in-memory ``AccountRepository`` stand-in (issues #19, #14/#25).

    Faithful enough for the registry's DB-first reads — campaigns live in a
    dict keyed by campaign_id — so ``api_client`` exercises the same
    repository-backed code path as production while staying hermetic (no live
    DB, even when the developer's environment has ``DATABASE_URL`` set).
    Ownership writes are recorded in ``created`` for wiring asserts.
    """

    def __init__(self) -> None:
        self.created: list[tuple[str, str | None]] = []
        self._campaigns: dict[str, dict] = {}

    async def create_campaign(
        self, account_id: str, campaign_id: str | None = None, name: str | None = None
    ):
        cid = campaign_id or str(uuid.uuid4())
        self.created.append((account_id, cid))
        self._campaigns[cid] = {
            "campaign_id": cid,
            "account_id": account_id,
            "status": "active",
            "name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "ended_reason": None,
        }
        return {"campaign_id": cid, "status": "active", "account_id": account_id, "name": name}

    async def get_active_campaign(self, account_id: str):
        for row in self._campaigns.values():
            if row["account_id"] == account_id and row["status"] == "active":
                return dict(row)
        return None

    async def list_ended_campaigns(self, account_id: str):
        return [
            dict(r)
            for r in self._campaigns.values()
            if r["account_id"] == account_id and r["status"] == "ended"
        ]

    async def end_campaign(
        self, account_id: str, campaign_id: str, reason: str | None = None
    ) -> bool:
        row = self._campaigns.get(campaign_id)
        if row is None or row["account_id"] != account_id:
            return False
        row["status"] = "ended"
        row["ended_reason"] = reason
        row["ended_at"] = datetime.now(timezone.utc).isoformat()
        return True


@pytest.fixture
def account_repo():
    """Recording account repository injected into ``api_client``."""
    return RecordingAccountRepository()


@pytest.fixture
def api_client(engine_server: Any, fake_narrator: Any, account_repo: Any):
    """Synchronous FastAPI TestClient with:
    - In-process engine toolset (no subprocess)
    - FakeNarrator (no LLM)
    - Fresh CampaignRegistry per test
    - RecordingAccountRepository (no live DB, even if DATABASE_URL is set)

    Routes work identically to production — only the backing implementations differ.
    The ``mcp_host`` factory is patched before the lifespan starts so the lifespan
    does not attempt to spawn a subprocess.
    """
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.accounts import set_account_repository
    from gamebook_web.api.app import app
    from gamebook_web.sessions.campaign import CampaignRegistry

    # Install in-process toolset factory BEFORE entering the lifespan
    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))

    # Install a fresh registry and the FakeNarrator on app.state so the
    # lifespan does not try to create a real narrator or registry.
    app.state.campaign_registry = CampaignRegistry(repository=account_repo)
    app.state.narrator = fake_narrator
    set_account_repository(account_repo)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    # Reset after the test
    mcp_host_mod.set_engine_toolset_factory(None)
    set_account_repository(None)
    app.state.campaign_registry = None  # type: ignore[assignment]
    app.state.narrator = None  # type: ignore[assignment]
    app.state.engine_toolset = None  # type: ignore[assignment]
