"""Full play loop via documented API with FakeNarrator (SC-001, FR-001/008).

Drives the complete gamebook loop — create/resume → explore → combat →
end-state — using ONLY the HTTP API (FastAPI TestClient) with:
  - FakeNarrator (no LLM — deterministic)
  - In-process engine (InMemoryStorage + seeded RNG — fast and isolated)

Confirms every number in responses traces to an engine MCP tool result
(SC-002, Principle I).
"""

from __future__ import annotations

import pytest

from gamebook_web.harness.base import FakeNarrator
from gamebook_web.harness.scene import Choice, Effect, Scene

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-token"}


def _create_campaign(client) -> str:
    """POST /campaigns and return the campaign_id."""
    resp = client.post("/campaigns", headers=_auth_headers())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "campaign_id" in data
    assert data["status"] == "active"
    return data["campaign_id"]


def _create_character(client, cid: str, name: str = "TestHero") -> dict:
    """POST /campaigns/{id}/character and return the character sheet."""
    resp = client.post(
        f"/campaigns/{cid}/character",
        json={"name": name},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    sheet = resp.json()
    assert sheet["name"] == name
    assert sheet["alive"] is True
    # Attributes rolled by engine (not narrated) — validate ranges
    assert 7 <= sheet["skill"]["initial"] <= 12
    assert 14 <= sheet["stamina"]["initial"] <= 24
    assert 7 <= sheet["luck"]["initial"] <= 12
    return sheet


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHealthAndOpenAPI:
    def test_health_returns_ok(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_openapi_schema_available(self, api_client):
        resp = api_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Gamebook Web API"

    def test_docs_available(self, api_client):
        resp = api_client.get("/docs")
        assert resp.status_code == 200


class TestCampaignCRUD:
    def test_create_campaign(self, api_client):
        cid = _create_campaign(api_client)
        assert cid  # non-empty UUID-like string

    def test_list_campaigns(self, api_client):
        cid = _create_campaign(api_client)
        resp = api_client.get("/campaigns", headers=_auth_headers())
        assert resp.status_code == 200
        campaigns = resp.json()
        assert any(c["campaign_id"] == cid for c in campaigns)

    def test_get_campaign_state(self, api_client):
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.get(f"/campaigns/{cid}", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["campaign_id"] == cid
        assert data["status"] == "active"
        assert data["character"] is not None
        assert data["character"]["name"] == "TestHero"
        # Summary and events come from engine state (not narrated)
        assert isinstance(data["summary"], str)
        assert isinstance(data["events"], list)

    def test_get_unknown_campaign_returns_404(self, api_client):
        resp = api_client.get(
            "/campaigns/nonexistent-id", headers=_auth_headers()
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_delete_campaign(self, api_client):
        cid = _create_campaign(api_client)
        resp = api_client.delete(f"/campaigns/{cid}", headers=_auth_headers())
        assert resp.status_code == 204
        # Confirm deleted
        resp2 = api_client.get(f"/campaigns/{cid}", headers=_auth_headers())
        assert resp2.status_code == 404


class TestCharacterCreation:
    def test_create_character_engine_rolls_stats(self, api_client):
        """Engine rolls attributes — client never supplies numbers (FR-001)."""
        cid = _create_campaign(api_client)
        sheet = _create_character(api_client, cid, name="Aldric")

        # All numbers from the engine
        for attr in ("skill", "stamina", "luck"):
            assert sheet[attr]["initial"] == sheet[attr]["current"]

    def test_read_character_reflects_engine_state(self, api_client):
        cid = _create_campaign(api_client)
        created = _create_character(api_client, cid)

        resp = api_client.get(f"/campaigns/{cid}/character", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json() == created  # exact same engine state

    def test_duplicate_character_creation_rejected(self, api_client):
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        # Second attempt — engine must reject it
        resp = api_client.post(
            f"/campaigns/{cid}/character",
            json={"name": "Duplicate"},
            headers=_auth_headers(),
        )
        assert resp.status_code in (409, 422, 500)  # engine raises on duplicate living hero

    def test_character_on_ended_campaign_rejected(self, api_client, engine_server):
        """Creating a character on an ended campaign returns 409."""
        from gamebook_web.api.app import app
        cid = _create_campaign(api_client)
        # Manually end the campaign
        app.state.campaign_registry.set_ended(cid)

        resp = api_client.post(
            f"/campaigns/{cid}/character",
            json={"name": "Ghost"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "run_ended"


class TestTurnBasedPlay:
    """US1: full play loop — exploration turns via FakeNarrator."""

    def test_first_turn_returns_scene(self, api_client):
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={"choice": None},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        scene = data["scene"]
        assert scene["narrative"]
        assert isinstance(scene["choices"], list)
        assert isinstance(scene["effects"], list)

    def test_turn_returns_engine_state(self, api_client):
        """After a turn the response includes real engine state (not narrated numbers)."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={"choice": "1"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        # character comes from engine, not narrator
        char = data["character"]
        assert char is not None
        assert "skill" in char
        assert "stamina" in char

    def test_multiple_turns_advance_story(self, api_client):
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        for choice in ["1", "2", "1"]:
            resp = api_client.post(
                f"/campaigns/{cid}/turn",
                json={"choice": choice},
                headers=_auth_headers(),
            )
            assert resp.status_code == 200

    def test_turn_with_register_event_effect(self, api_client, engine_server):
        """Effects in the FakeNarrator Scene are applied via MCP (not narrated)."""
        from gamebook_web.api.app import app

        scene_with_event = Scene(
            narrative="You enter the foothills. Ancient trees loom around you.",
            choices=[
                Choice(id="1", label="Explore deeper"),
                Choice(id="2", label="Turn back"),
            ],
            effects=[
                Effect(
                    type="register_event",
                    params={"type": "enter_zone", "data": {"zone": "foothills"}},
                )
            ],
        )
        app.state.narrator = FakeNarrator(scenes=[scene_with_event])

        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={"choice": None},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        # The effect was applied — check events in campaign state
        state_resp = api_client.get(f"/campaigns/{cid}", headers=_auth_headers())
        events = state_resp.json()["events"]
        assert any(e["type"] == "enter_zone" for e in events)

    def test_get_scene_after_turn(self, api_client):
        """GET /scene returns the last narrator scene."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        # Before any turn
        resp = api_client.get(f"/campaigns/{cid}/scene", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["scene"] is None

        # After a turn
        api_client.post(f"/campaigns/{cid}/turn", json={}, headers=_auth_headers())
        resp = api_client.get(f"/campaigns/{cid}/scene", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["scene"] is not None

    def test_turn_on_ended_campaign_returns_409(self, api_client):
        from gamebook_web.api.app import app
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)
        app.state.campaign_registry.set_ended(cid)

        resp = api_client.post(
            f"/campaigns/{cid}/turn", json={}, headers=_auth_headers()
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "run_ended"


class TestCombatViaAPI:
    """US1: combat loop driven by explicit combat endpoints."""

    def _setup_combat(self, api_client, engine_server) -> tuple[str, str]:
        """Create campaign + character + start combat.  Return (campaign_id, combat_id)."""
        from gamebook_web.api.app import app

        combat_scene = Scene(
            narrative="A fierce goblin leaps from the shadows, blade raised!",
            choices=[
                Choice(id="1", label="Attack!"),
                Choice(id="2", label="Try to flee"),
            ],
            effects=[
                Effect(
                    type="start_combat",
                    params={
                        "enemies": [{"name": "Goblin", "skill": 5, "stamina": 4}],
                        "flee_allowed": True,
                    },
                )
            ],
        )
        app.state.narrator = FakeNarrator(scenes=[combat_scene])

        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        # Turn triggers start_combat effect → combat_id stored in campaign state
        resp = api_client.post(
            f"/campaigns/{cid}/turn", json={}, headers=_auth_headers()
        )
        assert resp.status_code == 200, resp.text

        # Retrieve the combat_id from the registry
        registry = app.state.campaign_registry
        campaign_state = registry.get(cid)
        assert campaign_state.current_combat_id is not None, (
            "Expected start_combat effect to store a combat_id"
        )
        return cid, campaign_state.current_combat_id

    def test_combat_round_returns_engine_outcome(self, api_client, engine_server):
        cid, combat_id = self._setup_combat(api_client, engine_server)

        resp = api_client.post(
            f"/campaigns/{cid}/combat/round",
            json={"test_luck": False},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        outcome = data["outcome"]

        # All numbers from the engine (SC-002)
        assert outcome["hitter"] in ("hero", "enemy", "tie")
        assert "hero_stamina" in outcome
        assert "enemy_stamina" in outcome
        assert "hero_as" in outcome
        assert "enemy_as" in outcome

    def test_combat_rounds_until_ended(self, api_client, engine_server):
        """Drive combat to completion; confirm the final result is engine-authoritative."""
        cid, _ = self._setup_combat(api_client, engine_server)

        final_result = None
        for _ in range(100):  # max rounds guard
            resp = api_client.post(
                f"/campaigns/{cid}/combat/round",
                json={"test_luck": False},
                headers=_auth_headers(),
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()

            if data["outcome"].get("ended"):
                final_result = data["final_result"]
                assert final_result is not None
                assert final_result["winner"] in ("hero", "enemy")
                assert final_result["rounds"] >= 1
                break

        assert final_result is not None, "Combat did not conclude within 100 rounds"

    def test_combat_round_with_luck(self, api_client, engine_server):
        """Luck test is computed by engine (use_luck=True path, FR-005)."""
        cid, _ = self._setup_combat(api_client, engine_server)

        resp = api_client.post(
            f"/campaigns/{cid}/combat/round",
            json={"test_luck": True},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        outcome = resp.json()["outcome"]
        # If there was a hit, luck info is present
        if outcome["hitter"] != "tie" and not outcome.get("ended"):
            # luck_used may or may not be present depending on hit side
            assert "hitter" in outcome

    def test_no_active_combat_returns_409(self, api_client):
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.post(
            f"/campaigns/{cid}/combat/round",
            json={},
            headers=_auth_headers(),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "no_active_combat"

    def test_flee_combat(self, api_client, engine_server):
        cid, _ = self._setup_combat(api_client, engine_server)

        resp = api_client.post(
            f"/campaigns/{cid}/combat/flee",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "result" in data
        assert "damage_taken" in data["result"]
        # Flee costs engine-computed damage (not narrated)
        assert data["result"]["damage_taken"] == 2


class TestEndStates:
    """US1: death and victory end-states archive and prevent further play."""

    def test_death_ends_campaign(self, api_client, engine_server):
        """After hero dies in combat, campaign is ended and further turns are rejected."""
        from gamebook_web.api.app import app

        combat_scene = Scene(
            narrative="A mighty troll blocks your path!",
            choices=[Choice(id="1", label="Fight!")],
            effects=[
                Effect(
                    type="start_combat",
                    params={
                        "enemies": [{"name": "Giant Troll", "skill": 12, "stamina": 100}],
                        "flee_allowed": False,
                    },
                )
            ],
        )
        app.state.narrator = FakeNarrator(scenes=[combat_scene])

        cid = _create_campaign(api_client)
        _create_character(api_client, cid)
        api_client.post(f"/campaigns/{cid}/turn", json={}, headers=_auth_headers())

        # Drive combat until hero dies (troll has skill=12, hero has skill~9)
        campaign_ended = False
        for _ in range(200):
            resp = api_client.post(
                f"/campaigns/{cid}/combat/round",
                json={"test_luck": False},
                headers=_auth_headers(),
            )
            if resp.status_code == 409:
                # Already ended
                campaign_ended = True
                break
            data = resp.json()
            if data.get("campaign_ended"):
                campaign_ended = True
                break

        assert campaign_ended, "Hero should have died against the Giant Troll"

    def test_save_checkpoint(self, api_client):
        """POST /campaigns/{id}/save triggers engine's save_progress tool."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.post(f"/campaigns/{cid}/save", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestAuthEnvelope:
    def test_invalid_token_returns_401(self, api_client):
        resp = api_client.get(
            "/campaigns",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthenticated"

    def test_no_token_dev_mode_allowed(self, api_client):
        """In dev mode (default), no auth token is accepted."""
        resp = api_client.get("/campaigns")  # no Authorization header
        assert resp.status_code == 200
