"""Combat victory inside POST /me/game/turn (T092, SC-025, FR-044).

Since spec 007 (ADR-029) there is no /combat/round endpoint: the narrator
resolves combat via MCP tools *during* narrate(). These tests simulate that
by using a narrator test double that mutates engine state mid-narrate (the
same observable behavior as real tool calls), then assert the play loop's
post-narrate re-read + ``_check_terminal_state`` ends and archives the run.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from gamebook.domain.models import World
from gamebook_web.harness.base import NarratorContext
from gamebook_web.harness.scene import Scene


AUTH = {"Authorization": "Bearer dev-token"}


class CombatResolvingNarrator:
    """Test double honoring ADR-029: state changes happen INSIDE narrate().

    On the second narrate() call (the "fight Malachar" turn) it sets the
    victory flag in engine storage — exactly what the real narrator's
    update_world tool call does after winning the final combat — and returns
    a terminal Scene narrating the outcome.
    """

    def __init__(self, engine_storage: Any) -> None:
        self._storage = engine_storage
        self.calls = 0

    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:
        self.calls += 1
        if self.calls == 1:
            return Scene(
                narrative="Malachar rises from his obsidian throne. Fight or flee?",
                choices=[{"id": "1", "label": "Fight"}, {"id": "2", "label": "Flee"}],
            )
        # Combat auto-resolved during the turn: hero wins, boss falls.
        world = self._storage.load_world()
        self._storage.save_world(
            World(
                current_location=world.current_location,
                visited_locations=world.visited_locations,
                flags={**world.flags, "malachar_defeated": True},
                known_npcs=world.known_npcs,
                turn=world.turn,
            )
        )
        return Scene(
            narrative="Your blade finds its mark. Malachar collapses — the Grey Mountain is free.",
            choices=[],
            terminal=True,
        )


@pytest.fixture
def victory_client(engine_server: Any, engine_storage: Any):
    """API client wired with the combat-resolving narrator double."""
    from pydantic_ai.mcp import MCPToolset

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.sessions.campaign import CampaignRegistry

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = CombatResolvingNarrator(engine_storage)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None  # type: ignore[assignment]
    app.state.narrator = None  # type: ignore[assignment]
    app.state.engine_toolset = None  # type: ignore[assignment]


class TestCombatVictoryViaTurn:
    def test_victory_turn_ends_and_archives_campaign(
        self, victory_client, engine_storage, monkeypatch
    ):
        import gamebook_web.api.play as play_mod

        # Spy on _check_terminal_state without changing its behavior.
        terminal_checks: list[str] = []
        original = play_mod._check_terminal_state

        async def spy(campaign_id, character, world, toolset, registry):
            terminal_checks.append(campaign_id)
            return await original(campaign_id, character, world, toolset, registry)

        monkeypatch.setattr(play_mod, "_check_terminal_state", spy)

        # Set up a run and a hero.
        resp = victory_client.post(
            "/me/game", json={"name": "Doom of Malachar"}, headers=AUTH
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Doom of Malachar"
        resp = victory_client.post(
            "/me/game/character", json={"name": "Aria"}, headers=AUTH
        )
        assert resp.status_code == 201

        # Turn 1: pre-combat scene (fight or flee).
        turn1 = victory_client.post("/me/game/turn", json={}, headers=AUTH)
        assert turn1.status_code == 200
        assert turn1.json()["status"] == "active"

        # Turn 2: player fights — combat resolves inside the turn, victory flag set.
        turn2 = victory_client.post(
            "/me/game/turn", json={"choice": "1"}, headers=AUTH
        )
        assert turn2.status_code == 200
        body = turn2.json()
        assert body["status"] == "ended"
        assert body["scene"]["terminal"] is True

        # _check_terminal_state ran on both turns.
        assert len(terminal_checks) == 2

        # Hero archived to the hall of fame (victory destination).
        assert len(engine_storage._archives["hall_of_fame"]) == 1

    def test_further_turns_rejected_after_victory(self, victory_client, engine_storage):
        victory_client.post("/me/game", json={"name": "Doom of Malachar"}, headers=AUTH)
        victory_client.post("/me/game/character", json={"name": "Aria"}, headers=AUTH)
        victory_client.post("/me/game/turn", json={}, headers=AUTH)
        end = victory_client.post("/me/game/turn", json={"choice": "1"}, headers=AUTH)
        assert end.json()["status"] == "ended"

        # Ended runs are no longer addressable: the single-active-campaign
        # model resolves "my game" to nothing, so further turns get 404
        # no_active_campaign (the 409 run_ended path is for a campaign that
        # ends mid-request). Either way: rejected.
        again = victory_client.post("/me/game/turn", json={"choice": "1"}, headers=AUTH)
        assert again.status_code in (404, 409)
        assert again.json()["error"]["code"] in ("no_active_campaign", "run_ended")

    def test_victory_appears_in_graveyard_with_reason(self, victory_client):
        victory_client.post("/me/game", json={"name": "Doom of Malachar"}, headers=AUTH)
        victory_client.post("/me/game/character", json={"name": "Aria"}, headers=AUTH)
        victory_client.post("/me/game/turn", json={}, headers=AUTH)
        victory_client.post("/me/game/turn", json={"choice": "1"}, headers=AUTH)

        grave = victory_client.get("/me/graveyard", headers=AUTH).json()
        assert len(grave) == 1
        entry = grave[0]
        assert entry["ended_reason"] == "victory"
        assert entry["name"] == "Doom of Malachar"
        assert entry["ended_at"] is not None
