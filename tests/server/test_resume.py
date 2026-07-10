"""Resume test — living game resumes from exact recorded point (FR-003).

Confirms that:
1. A game's recorded state is available via ``GET /me/game``.
2. After multiple turns, the state reflects the cumulative engine history.
3. ``GET /me/game`` never re-rolls, re-starts, or contradicts facts.
4. The current scene (last narrator output) is re-fetchable via ``GET /me/game/scene``.

After the backend-scoped route redesign (spec 006, D1), routes are ``/me/game/...``
— the frontend never manages campaign_id.

After the narrator tool-use refactor (spec 007, ADR-029), the narrator calls
MCP tools directly during generation. FakeNarrator tests verify state-read
paths; engine mutations are injected via ``engine_storage`` where needed.
"""

from __future__ import annotations

import pytest

from gamebook_web.harness.narrator import FakeNarrator
from gamebook_web.harness.scene import Choice, Scene

_HEADERS = {"Authorization": "Bearer dev-token"}


def _create_game(client) -> str:
    resp = client.post("/me/game", headers=_HEADERS)
    assert resp.status_code == 201
    return resp.json()["campaign_id"]


def _create_character(client, name: str = "Resumebot") -> dict:
    resp = client.post("/me/game/character", json={"name": name}, headers=_HEADERS)
    assert resp.status_code == 201
    return resp.json()


def _take_turn(client, choice: str | None = None) -> dict:
    resp = client.post("/me/game/turn", json={"choice": choice}, headers=_HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestResumeLivingCampaign:
    """FR-003: The session-opening read loads exact recorded state."""

    def test_initial_state_has_no_character(self, api_client):
        """Before character creation, GET /me/game shows no character."""
        _create_game(api_client)
        resp = api_client.get("/me/game", headers=_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["character"] is None

    def test_character_persists_across_reads(self, api_client):
        """Created character is visible on subsequent GET /me/game calls."""
        _create_game(api_client)
        original = _create_character(api_client, name="Persisted")

        # First read
        state1 = api_client.get("/me/game", headers=_HEADERS).json()
        assert state1["character"]["name"] == "Persisted"

        # Second read — same state, no re-roll
        state2 = api_client.get("/me/game", headers=_HEADERS).json()
        assert state2["character"] == state1["character"]
        assert state2["character"] == original  # exact same engine record

    def test_events_injected_via_storage_are_visible(self, api_client, engine_storage):
        """Events written directly to engine_storage appear in GET /me/game.

        This tests the state-read path (FR-003). In live play, the narrator
        calls register_event during narrate(); here we inject events directly
        to keep the test deterministic and LLM-free.
        """
        _create_game(api_client)
        _create_character(api_client)

        from datetime import datetime, timezone
        from gamebook.domain.models import Event

        engine_storage.append_event(Event(
            turn=1, type="enter_zone", data={"zone": "foothills"},
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        ))
        engine_storage.append_event(Event(
            turn=2, type="discover", data={"object": "shrine"},
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        ))

        state = api_client.get("/me/game", headers=_HEADERS).json()
        types = [e["type"] for e in state["events"]]
        assert "enter_zone" in types, "Injected enter_zone event must be visible"
        assert "discover" in types, "Injected discover event must be visible"

    def test_stats_do_not_change_without_engine_tool_calls(self, api_client):
        """Character stats are unchanged if the narrator makes no MCP tool calls.

        FakeNarrator returns plain Scenes without calling any tools, so stats
        must remain identical to their post-creation values.
        """
        from gamebook_web.api.app import app

        safe_scene = Scene(
            narrative="Nothing happens. You observe the landscape.",
            choices=[Choice(id="1", label="Move on")],
        )
        app.state.narrator = FakeNarrator(scenes=[safe_scene] * 3)

        _create_game(api_client)
        original = _create_character(api_client, name="Unchanged")

        for _ in range(3):
            _take_turn(api_client)

        state = api_client.get("/me/game", headers=_HEADERS).json()
        final_char = state["character"]
        for attr in ("skill", "stamina", "luck"):
            assert final_char[attr]["current"] == original[attr]["current"], (
                f"{attr}.current changed without an engine tool call"
            )

    def test_current_scene_refetchable(self, api_client):
        """GET /me/game/scene returns the last scene emitted by the narrator (FR-003/resume)."""
        _create_game(api_client)
        _create_character(api_client)

        turn_resp = _take_turn(api_client)
        scene_from_turn = turn_resp["scene"]

        scene_resp = api_client.get("/me/game/scene", headers=_HEADERS)
        assert scene_resp.status_code == 200
        stored_scene = scene_resp.json()["scene"]

        assert stored_scene is not None
        assert stored_scene["narrative"] == scene_from_turn["narrative"]
        assert stored_scene["choices"] == scene_from_turn["choices"]

    def test_world_state_injected_via_storage_is_visible(self, api_client, engine_storage):
        """World state written to engine_storage appears in GET /me/game.

        In live play, the narrator calls update_world during narrate(); here
        we inject world state directly to keep the test deterministic.
        """
        from gamebook.domain.models import World

        _create_game(api_client)
        _create_character(api_client)

        world = engine_storage.load_world()
        engine_storage.save_world(World(
            current_location="cave_of_echoes",
            flags=world.flags,
            visited_locations=world.visited_locations,
            known_npcs=world.known_npcs,
            turn=world.turn,
        ))

        state = api_client.get("/me/game", headers=_HEADERS).json()
        assert state["world"]["current_location"] == "cave_of_echoes"

    def test_resume_returns_active_not_ended(self, api_client):
        """Living game stays 'active' across reads — no phantom end-state."""
        _create_game(api_client)
        _create_character(api_client)
        _take_turn(api_client)

        for _ in range(3):
            state = api_client.get("/me/game", headers=_HEADERS).json()
            assert state["status"] == "active"


# ---------------------------------------------------------------------------
# Fixture: per-test fresh client (needs api_client_factory to avoid sharing)
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client_factory(engine_server):
    """Factory so tests can create their own client if needed."""
    return engine_server
