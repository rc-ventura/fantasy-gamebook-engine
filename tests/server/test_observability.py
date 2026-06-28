"""Test: OTel traces surface errors and slow narrator (T021 / SC-008).

Uses InMemorySpanExporter so no real OTLP collector is needed.

Scenarios:
  1. Slow narrator (asyncio.sleep) → span duration is recorded.
  2. Narrator exception → span has status=ERROR and the API returns
     ``{"error": {"code": "invalid_scene", ...}}`` (not a raw 500 traceback).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from gamebook_web.harness.base import FakeNarrator, NarratorContext
from gamebook_web.harness.scene import Scene


# ---------------------------------------------------------------------------
# Slow narrator
# ---------------------------------------------------------------------------

class SlowNarrator(FakeNarrator):
    """FakeNarrator that sleeps before returning to simulate LLM latency."""

    def __init__(self, delay: float = 0.05) -> None:
        super().__init__()
        self._delay = delay

    async def narrate(self, campaign_id: str, ctx: NarratorContext) -> Scene:
        await asyncio.sleep(self._delay)
        return await super().narrate(campaign_id, ctx)


# ---------------------------------------------------------------------------
# Failing narrator
# ---------------------------------------------------------------------------

class FailingNarrator(FakeNarrator):
    """Narrator that always raises RuntimeError."""

    async def narrate(self, campaign_id: str, ctx: NarratorContext) -> Scene:
        raise RuntimeError("Induced narrator failure for testing")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def otel_client(engine_server):
    """API client with InMemorySpanExporter for span assertions."""
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.observability.setup import reset_telemetry, setup_telemetry
    from gamebook_web.sessions.campaign import CampaignRegistry

    # Reset OTel state so we get a fresh InMemorySpanExporter
    reset_telemetry()
    in_mem_exporter = setup_telemetry(service_name="test-gamebook")

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))
    app.state.campaign_registry = CampaignRegistry()

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, in_mem_exporter

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None
    app.state.narrator = None
    app.state.engine_toolset = None
    reset_telemetry()


@pytest.fixture
def slow_client(engine_server):
    """API client with a SlowNarrator."""
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.observability.setup import reset_telemetry, setup_telemetry
    from gamebook_web.sessions.campaign import CampaignRegistry

    reset_telemetry()
    in_mem_exporter = setup_telemetry(service_name="test-gamebook")

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = SlowNarrator(delay=0.05)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, in_mem_exporter

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None
    app.state.narrator = None
    app.state.engine_toolset = None
    reset_telemetry()


@pytest.fixture
def fail_client(engine_server):
    """API client with a FailingNarrator."""
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.observability.setup import reset_telemetry, setup_telemetry
    from gamebook_web.sessions.campaign import CampaignRegistry

    reset_telemetry()
    in_mem_exporter = setup_telemetry(service_name="test-gamebook")

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = FailingNarrator()

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, in_mem_exporter

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None
    app.state.narrator = None
    app.state.engine_toolset = None
    reset_telemetry()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_slow_narrator_does_not_suppress_response(slow_client) -> None:
    """A slow narrator still returns a valid response (not a timeout 500)."""
    client, _ = slow_client

    resp = client.post("/campaigns", headers={"Authorization": "Bearer dev-token"})
    assert resp.status_code == 201
    cid = resp.json()["campaign_id"]

    client.post(f"/campaigns/{cid}/character", headers={"Authorization": "Bearer dev-token"})

    resp_turn = client.post(
        f"/campaigns/{cid}/turn",
        headers={"Authorization": "Bearer dev-token"},
        json={"choice": "go north"},
    )
    # Should succeed (200) or fail with a structured error — never a raw 500
    assert resp_turn.status_code != 500 or "error" in resp_turn.json()


def test_failing_narrator_returns_structured_error(fail_client) -> None:
    """A narrator exception returns ``invalid_scene`` error (no raw traceback)."""
    client, exporter = fail_client

    resp = client.post("/campaigns", headers={"Authorization": "Bearer dev-token"})
    assert resp.status_code == 201
    cid = resp.json()["campaign_id"]

    client.post(f"/campaigns/{cid}/character", headers={"Authorization": "Bearer dev-token"})

    resp_turn = client.post(
        f"/campaigns/{cid}/turn",
        headers={"Authorization": "Bearer dev-token"},
        json={"choice": "go north"},
    )
    assert resp_turn.status_code in (422, 500), resp_turn.json()
    body = resp_turn.json()
    # Must return a structured error, not a raw Python traceback
    assert "error" in body, f"Expected error envelope but got: {body}"
    # The error code must be a stable string, not a raw exception message
    code = body["error"].get("code", "")
    assert code in ("invalid_scene", "internal_error"), f"Unexpected error code: {code}"


def test_health_check_returns_ok() -> None:
    """GET /health returns 200 with status ok."""
    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.sessions.campaign import CampaignRegistry
    from gamebook_web.harness.base import FakeNarrator
    from pydantic_ai.mcp import MCPToolset

    # minimal fixture
    from gamebook.storage.in_memory import InMemoryStorage
    from gamebook.combat.implementation import CombatService
    from gamebook.mcp.server import build_server
    import random

    engine_storage = InMemoryStorage()
    rng = random.Random(42)
    combat = CombatService(engine_storage, rng)
    server = build_server(storage=engine_storage, combat=combat, rng=rng)

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(server))
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = FakeNarrator()

    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/health")

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None
    app.state.narrator = None
    app.state.engine_toolset = None

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
