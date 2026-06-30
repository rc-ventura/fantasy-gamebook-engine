"""Full play loop via documented API with FakeNarrator (SC-001, FR-001/008).

Drives the complete gamebook loop — create/resume → explore → combat →
end-state — using ONLY the HTTP API (FastAPI TestClient) with:
  - FakeNarrator (no LLM — deterministic)
  - In-process engine (InMemoryStorage + seeded RNG — fast and isolated)

After the narrator tool-use refactor (spec 007, ADR-029), the narrator calls
MCP tools directly during generation. The explicit combat endpoints
(POST /combat/round, POST /combat/flee) are removed; combat resolves inside
POST /turn. Tests confirm this API shape and the simplified TurnResponse.
"""

from __future__ import annotations

import pytest

from gamebook_web.harness.base import FakeNarrator
from gamebook_web.harness.scene import Choice, Scene

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
        app.state.campaign_registry.set_ended(cid)

        resp = api_client.post(
            f"/campaigns/{cid}/character",
            json={"name": "Ghost"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "run_ended"


class TestTurnBasedPlay:
    """Play loop — exploration turns via FakeNarrator (US1, US2)."""

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
        # Structural contract: no effects field (FR-002, spec 007)
        assert "effects" not in scene
        # No effects_applied in TurnResponse (FR-003, spec 007)
        assert "effects_applied" not in data

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

    def test_turn_stores_scene_for_resume(self, api_client):
        """After a turn, GET /scene returns the stored scene."""
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


class TestCombatEndpointsRemoved:
    """POST /combat/round and POST /combat/flee are removed (US3, FR-005, spec 007).

    Combat now resolves inside POST /turn — the narrator calls start_combat,
    resolve_combat_round, and end_combat directly during generation.
    """

    def test_combat_round_returns_404(self, api_client):
        cid = _create_campaign(api_client)
        resp = api_client.post(
            f"/campaigns/{cid}/combat/round",
            json={"test_luck": False},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404, (
            "POST /combat/round must not exist after spec 007 refactor"
        )

    def test_combat_flee_returns_404(self, api_client):
        cid = _create_campaign(api_client)
        resp = api_client.post(
            f"/campaigns/{cid}/combat/flee",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404, (
            "POST /combat/flee must not exist after spec 007 refactor"
        )


class TestEndStates:
    """Death and victory end-states archive and prevent further play."""

    def test_death_ends_campaign(self, api_client, engine_storage):
        """When hero stamina reaches 0 (alive=False), the campaign ends after the next turn.

        Simulates combat outcome by directly writing a dead hero to engine_storage.
        The API detects alive=False in _check_terminal_state, archives, and ends the campaign.
        """
        from gamebook.domain.models import Attribute, CharacterSheet

        cid = _create_campaign(api_client)
        sheet_data = _create_character(api_client, cid)

        # Directly kill the hero via storage (simulates combat driving stamina to 0)
        dead_sheet = CharacterSheet(
            name=sheet_data["name"],
            skill=Attribute(**sheet_data["skill"]),
            stamina=Attribute(
                initial=sheet_data["stamina"]["initial"],
                current=0,
            ),
            luck=Attribute(**sheet_data["luck"]),
            inventory=sheet_data.get("inventory", []),
            gold=sheet_data.get("gold", 0),
            provisions=sheet_data.get("provisions", 0),
            conditions=sheet_data.get("conditions", []),
            alive=False,
        )
        engine_storage.save_character(dead_sheet)

        # Next turn: API reads dead hero → _check_terminal_state archives → campaign ends
        resp = api_client.post(f"/campaigns/{cid}/turn", json={}, headers=_auth_headers())
        assert resp.status_code == 200

        campaign = api_client.get(f"/campaigns/{cid}", headers=_auth_headers()).json()
        assert campaign["status"] == "ended"

        # Further turns rejected
        resp2 = api_client.post(f"/campaigns/{cid}/turn", json={}, headers=_auth_headers())
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "run_ended"

    def test_victory_ends_campaign(self, api_client, engine_storage):
        """When malachar_defeated flag is set in world, the campaign ends after the next turn.

        Simulates victory by directly writing the victory flag to engine_storage.
        The API detects it in _check_terminal_state, archives to hall_of_fame, and ends.
        """
        from gamebook.domain.models import World

        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        # Inject victory flag directly into engine world state
        world = engine_storage.load_world()
        engine_storage.save_world(World(
            current_location=world.current_location,
            flags={**world.flags, "malachar_defeated": True},
            visited_locations=world.visited_locations,
            known_npcs=world.known_npcs,
            turn=world.turn,
        ))

        # Next turn: API reads world → _check_terminal_state triggers victory archive
        resp = api_client.post(f"/campaigns/{cid}/turn", json={}, headers=_auth_headers())
        assert resp.status_code == 200

        campaign = api_client.get(f"/campaigns/{cid}", headers=_auth_headers()).json()
        assert campaign["status"] == "ended"

        # Further turns rejected
        resp2 = api_client.post(f"/campaigns/{cid}/turn", json={}, headers=_auth_headers())
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "run_ended"

    def test_save_checkpoint(self, api_client):
        """POST /campaigns/{id}/save triggers engine's save_progress tool."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        resp = api_client.post(f"/campaigns/{cid}/save", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestInputValidation:
    """Player input is bounded before reaching the narrator (A03 mitigation)."""

    def test_choice_over_max_length_returns_422(self, api_client):
        """A choice exceeding 500 chars is rejected before the narrator is called."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        long_choice = "x" * 501
        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={"choice": long_choice},
            headers=_auth_headers(),
        )
        assert resp.status_code == 422

    def test_choice_at_max_length_accepted(self, api_client):
        """A choice of exactly 500 chars is accepted."""
        cid = _create_campaign(api_client)
        _create_character(api_client, cid)

        long_choice = "y" * 500
        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={"choice": long_choice},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200


class TestAuthEnvelope:
    def test_invalid_token_returns_401(self, api_client):
        resp = api_client.get(
            "/campaigns",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthenticated"

    def test_no_token_dev_mode_allowed(self, api_client, monkeypatch):
        """With dev mode explicitly enabled, no auth token is accepted."""
        monkeypatch.setenv("GAMEBOOK_DEV_MODE", "1")
        resp = api_client.get("/campaigns")  # no Authorization header
        assert resp.status_code == 200

    def test_no_token_fails_closed_by_default(self, api_client):
        """Fail-closed: without GAMEBOOK_DEV_MODE set, a missing token → 401."""
        resp = api_client.get("/campaigns")  # no Authorization header
        assert resp.status_code == 401
