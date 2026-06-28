"""Resume test — living campaign resumes from exact recorded point (FR-003).

Confirms that:
1. A campaign's recorded state is available via ``GET /campaigns/{id}``.
2. After multiple turns, the state reflects the cumulative engine history.
3. ``GET /campaigns/{id}`` never re-rolls, re-starts, or contradicts facts.
4. The current scene (last narrator output) is re-fetchable via ``GET /scene``.

Tests use FakeNarrator + in-process engine (no LLM, no subprocess).
"""

from __future__ import annotations

import pytest

from gamebook_web.harness.base import FakeNarrator
from gamebook_web.harness.scene import Choice, Effect, Scene

_HEADERS = {"Authorization": "Bearer dev-token"}


def _create_campaign(client) -> str:
    resp = client.post("/campaigns", headers=_HEADERS)
    assert resp.status_code == 201
    return resp.json()["campaign_id"]


def _create_character(client, cid: str, name: str = "Resumebot") -> dict:
    resp = client.post(
        f"/campaigns/{cid}/character",
        json={"name": name},
        headers=_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()


def _take_turn(client, cid: str, choice: str | None = None) -> dict:
    resp = client.post(
        f"/campaigns/{cid}/turn",
        json={"choice": choice},
        headers=_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestResumeLivingCampaign:
    """FR-003: The session-opening read loads exact recorded state."""

    def test_initial_state_has_no_character(self, api_client):
        """Before character creation, GET /campaigns/{id} shows no character."""
        cid = _create_campaign(api_client)
        resp = api_client.get(f"/campaigns/{cid}", headers=_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["character"] is None

    def test_character_persists_across_reads(self, api_client):
        """Created character is visible on subsequent GET /campaigns/{id} calls."""
        cid = _create_campaign(api_client)
        original = _create_character(api_client, cid, name="Persisted")

        # First read
        state1 = api_client.get(f"/campaigns/{cid}", headers=_HEADERS).json()
        assert state1["character"]["name"] == "Persisted"

        # Second read — same state, no re-roll
        state2 = api_client.get(f"/campaigns/{cid}", headers=_HEADERS).json()
        assert state2["character"] == state1["character"]
        assert state2["character"] == original  # exact same engine record

    def test_events_accumulate_across_turns(self, api_client, api_client_factory):
        """Events registered in effects are visible on subsequent reads (FR-003)."""
        from gamebook_web.api.app import app

        scenes_queue = [
            Scene(
                narrative="Turn 1: You enter the foothills.",
                choices=[Choice(id="1", label="Continue")],
                effects=[
                    Effect(
                        type="register_event",
                        params={"type": "enter_zone", "data": {"zone": "foothills"}},
                    )
                ],
            ),
            Scene(
                narrative="Turn 2: You find an old shrine.",
                choices=[Choice(id="1", label="Investigate")],
                effects=[
                    Effect(
                        type="register_event",
                        params={"type": "discover", "data": {"object": "shrine"}},
                    )
                ],
            ),
        ]
        app.state.narrator = FakeNarrator(scenes=list(scenes_queue))

        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        _take_turn(api_client, cid, choice="1")   # registers enter_zone
        _take_turn(api_client, cid, choice="1")   # registers discover

        state = api_client.get(f"/campaigns/{cid}", headers=_HEADERS).json()
        types = [e["type"] for e in state["events"]]
        assert "enter_zone" in types, "Event from turn 1 must persist"
        assert "discover" in types, "Event from turn 2 must persist"

    def test_stats_do_not_change_without_engine_mutation(self, api_client):
        """Character stats are unchanged if no update_character effect is applied."""
        from gamebook_web.api.app import app

        # Scene with no character-mutation effects
        safe_scene = Scene(
            narrative="Nothing happens. You observe the landscape.",
            choices=[Choice(id="1", label="Move on")],
            effects=[],
        )
        app.state.narrator = FakeNarrator(scenes=[safe_scene] * 3)

        cid = _create_campaign(api_client)
        original = _create_character(api_client, cid, name="Unchanged")

        for _ in range(3):
            _take_turn(api_client, cid)

        state = api_client.get(f"/campaigns/{cid}", headers=_HEADERS).json()
        final_char = state["character"]
        # Stats unchanged by turns with no effects
        for attr in ("skill", "stamina", "luck"):
            assert final_char[attr]["current"] == original[attr]["current"], (
                f"{attr}.current changed without an engine mutation effect"
            )

    def test_current_scene_refetchable(self, api_client):
        """GET /scene returns the last scene emitted by the narrator (FR-003 / resume)."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        turn_resp = _take_turn(api_client, cid)
        scene_from_turn = turn_resp["scene"]

        scene_resp = api_client.get(f"/campaigns/{cid}/scene", headers=_HEADERS)
        assert scene_resp.status_code == 200
        stored_scene = scene_resp.json()["scene"]

        assert stored_scene is not None
        assert stored_scene["narrative"] == scene_from_turn["narrative"]
        assert stored_scene["choices"] == scene_from_turn["choices"]

    def test_world_location_persists_after_update(self, api_client):
        """World updates from effects are reflected in subsequent reads."""
        from gamebook_web.api.app import app

        location_scene = Scene(
            narrative="You arrive at the Cave of Echoes.",
            choices=[Choice(id="1", label="Enter")],
            effects=[
                Effect(
                    type="update_world",
                    params={"current_location": "cave_of_echoes"},
                )
            ],
        )
        app.state.narrator = FakeNarrator(scenes=[location_scene])

        cid = _create_campaign(api_client)
        _create_character(api_client, cid)
        _take_turn(api_client, cid)

        state = api_client.get(f"/campaigns/{cid}", headers=_HEADERS).json()
        assert state["world"]["current_location"] == "cave_of_echoes"

    def test_resume_returns_active_not_ended(self, api_client):
        """Living campaign stays 'active' across reads — no phantom end-state."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)
        _take_turn(api_client, cid)

        for _ in range(3):
            state = api_client.get(f"/campaigns/{cid}", headers=_HEADERS).json()
            assert state["status"] == "active"


# ---------------------------------------------------------------------------
# Fixture: per-test fresh client (needs api_client_factory to avoid sharing)
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client_factory(engine_server):
    """Factory so tests can create their own client if needed."""
    return engine_server
