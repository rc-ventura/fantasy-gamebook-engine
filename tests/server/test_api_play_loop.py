"""Full play loop via documented API with FakeNarrator (SC-001, FR-001/008).

Drives the complete gamebook loop — create/resume → explore → combat →
end-state — using ONLY the HTTP API (FastAPI TestClient) with:
  - FakeNarrator (no LLM — deterministic)
  - In-process engine (InMemoryStorage + seeded RNG — fast and isolated)

After the backend-scoped route redesign (spec 006, ADR-017, D1), routes are
``/me/game/...`` — the frontend never manages campaign_id.

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


def _create_game(client) -> str:
    """POST /me/game and return the campaign_id (for test reference only)."""
    resp = client.post("/me/game", headers=_auth_headers())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "campaign_id" in data
    assert data["status"] == "active"
    return data["campaign_id"]


def _create_character(client, name: str = "TestHero") -> dict:
    """POST /me/game/character and return the character sheet."""
    resp = client.post("/me/game/character", json={"name": name}, headers=_auth_headers())
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


class TestGameCRUD:
    def test_create_game(self, api_client):
        cid = _create_game(api_client)
        assert cid  # non-empty UUID-like string

    def test_create_game_returns_status(self, api_client):
        resp = api_client.post("/me/game", headers=_auth_headers())
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "active"
        assert "campaign_id" in data

    def test_get_game_state(self, api_client):
        _create_game(api_client)
        _create_character(api_client)

        resp = api_client.get("/me/game", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["character"] is not None
        assert data["character"]["name"] == "TestHero"
        assert isinstance(data["summary"], str)
        assert isinstance(data["events"], list)

    def test_get_game_without_active_campaign_returns_404(self, api_client):
        """GET /me/game with no active campaign returns 404 no_active_campaign."""
        resp = api_client.get("/me/game", headers=_auth_headers())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "no_active_campaign"

    def test_delete_game(self, api_client):
        _create_game(api_client)
        resp = api_client.delete("/me/game", headers=_auth_headers())
        assert resp.status_code == 204
        # Confirm deleted — no active campaign
        resp2 = api_client.get("/me/game", headers=_auth_headers())
        assert resp2.status_code == 404
        assert resp2.json()["error"]["code"] == "no_active_campaign"

    def test_graveyard_lists_ended_campaigns(self, api_client):
        """GET /me/graveyard lists campaigns ended via DELETE /me/game."""
        _create_game(api_client)
        api_client.delete("/me/game", headers=_auth_headers())

        resp = api_client.get("/me/graveyard", headers=_auth_headers())
        assert resp.status_code == 200
        graveyard = resp.json()
        assert isinstance(graveyard, list)
        assert len(graveyard) == 1
        entry = graveyard[0]
        assert entry["status"] == "ended"
        assert "campaign_id" in entry


class TestCharacterCreation:
    def test_create_character_engine_rolls_stats(self, api_client):
        """Engine rolls attributes — client never supplies numbers (FR-001)."""
        _create_game(api_client)
        sheet = _create_character(api_client, name="Aldric")

        # All numbers from the engine
        for attr in ("skill", "stamina", "luck"):
            assert sheet[attr]["initial"] == sheet[attr]["current"]

    def test_read_character_reflects_engine_state(self, api_client):
        _create_game(api_client)
        created = _create_character(api_client)

        resp = api_client.get("/me/game/character", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json() == created  # exact same engine state

    def test_duplicate_character_creation_rejected(self, api_client):
        _create_game(api_client)
        _create_character(api_client)

        # Second attempt — engine must reject it
        resp = api_client.post(
            "/me/game/character",
            json={"name": "Duplicate"},
            headers=_auth_headers(),
        )
        assert resp.status_code in (409, 422, 500)  # engine raises on duplicate living hero

    def test_character_with_no_active_game_returns_404(self, api_client):
        """Creating a character when no active game exists returns 404 no_active_campaign."""
        resp = api_client.post(
            "/me/game/character",
            json={"name": "Ghost"},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "no_active_campaign"


class TestTurnBasedPlay:
    """Play loop — exploration turns via FakeNarrator (US1, US2)."""

    def test_first_turn_returns_scene(self, api_client):
        _create_game(api_client)
        _create_character(api_client)

        resp = api_client.post("/me/game/turn", json={"choice": None}, headers=_auth_headers())
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
        _create_game(api_client)
        _create_character(api_client)

        resp = api_client.post("/me/game/turn", json={"choice": "1"}, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        char = data["character"]
        assert char is not None
        assert "skill" in char
        assert "stamina" in char

    def test_multiple_turns_advance_story(self, api_client):
        _create_game(api_client)
        _create_character(api_client)

        for choice in ["1", "2", "1"]:
            resp = api_client.post("/me/game/turn", json={"choice": choice}, headers=_auth_headers())
            assert resp.status_code == 200

    def test_turn_stores_scene_for_resume(self, api_client):
        """After a turn, GET /me/game/scene returns the stored scene."""
        _create_game(api_client)
        _create_character(api_client)

        # Before any turn
        resp = api_client.get("/me/game/scene", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["scene"] is None

        # After a turn
        api_client.post("/me/game/turn", json={}, headers=_auth_headers())
        resp = api_client.get("/me/game/scene", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["scene"] is not None

    def test_turn_with_no_active_game_returns_404(self, api_client):
        """POST /me/game/turn when no active game returns 404 no_active_campaign."""
        resp = api_client.post("/me/game/turn", json={}, headers=_auth_headers())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "no_active_campaign"


class TestCombatEndpointsRemoved:
    """Combat-round and flee endpoints are removed (US3, FR-005, spec 007).

    Combat now resolves inside POST /turn — the narrator calls start_combat,
    resolve_combat_round, and end_combat directly during generation.
    """

    def test_combat_round_returns_404(self, api_client):
        resp = api_client.post(
            "/me/game/combat/round",
            json={"test_luck": False},
            headers=_auth_headers(),
        )
        assert resp.status_code == 404, (
            "POST /me/game/combat/round must not exist after spec 007 refactor"
        )

    def test_combat_flee_returns_404(self, api_client):
        resp = api_client.post("/me/game/combat/flee", headers=_auth_headers())
        assert resp.status_code == 404, (
            "POST /me/game/combat/flee must not exist after spec 007 refactor"
        )


class TestEndStates:
    """Death and victory end-states archive and prevent further play."""

    def test_death_ends_campaign(self, api_client, engine_storage):
        """When hero stamina reaches 0 (alive=False), the campaign ends after the next turn.

        Simulates combat outcome by directly writing a dead hero to engine_storage.
        The API detects alive=False in _check_terminal_state, archives, and ends the campaign.
        """
        from gamebook.domain.models import Attribute, CharacterSheet

        _create_game(api_client)
        sheet_data = _create_character(api_client)

        # Directly kill the hero via storage (simulates combat driving stamina to 0)
        dead_sheet = CharacterSheet(
            name=sheet_data["name"],
            skill=Attribute(**sheet_data["skill"]),
            stamina=Attribute(initial=sheet_data["stamina"]["initial"], current=0),
            luck=Attribute(**sheet_data["luck"]),
            inventory=sheet_data.get("inventory", []),
            gold=sheet_data.get("gold", 0),
            provisions=sheet_data.get("provisions", 0),
            conditions=sheet_data.get("conditions", []),
            alive=False,
        )
        engine_storage.save_character(dead_sheet)

        # Next turn: API reads dead hero → _check_terminal_state archives → campaign ends
        resp = api_client.post("/me/game/turn", json={}, headers=_auth_headers())
        assert resp.status_code == 200

        # Game is now ended — no active campaign
        game = api_client.get("/me/game", headers=_auth_headers())
        assert game.status_code == 404
        assert game.json()["error"]["code"] == "no_active_campaign"

        # Further turns rejected — no active campaign
        resp2 = api_client.post("/me/game/turn", json={}, headers=_auth_headers())
        assert resp2.status_code == 404
        assert resp2.json()["error"]["code"] == "no_active_campaign"

        # Game appears in graveyard
        grave = api_client.get("/me/graveyard", headers=_auth_headers()).json()
        assert len(grave) >= 1
        assert any(e["ended_reason"] == "death" for e in grave)

    def test_victory_ends_campaign(self, api_client, engine_storage):
        """When malachar_defeated flag is set in world, the campaign ends after the next turn."""
        from gamebook.domain.models import World

        _create_game(api_client)
        _create_character(api_client)

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
        resp = api_client.post("/me/game/turn", json={}, headers=_auth_headers())
        assert resp.status_code == 200

        # Game ended — no active campaign
        game = api_client.get("/me/game", headers=_auth_headers())
        assert game.status_code == 404
        assert game.json()["error"]["code"] == "no_active_campaign"

        # Appears in graveyard
        grave = api_client.get("/me/graveyard", headers=_auth_headers()).json()
        assert any(e["ended_reason"] == "victory" for e in grave)

    def test_save_checkpoint(self, api_client):
        """POST /me/game/save triggers engine's save_progress tool."""
        _create_game(api_client)
        _create_character(api_client)

        resp = api_client.post("/me/game/save", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


class TestInputValidation:
    """Player input is bounded before reaching the narrator (A03 mitigation)."""

    def test_choice_over_max_length_returns_422(self, api_client):
        """A choice exceeding 500 chars is rejected before the narrator is called."""
        _create_game(api_client)
        _create_character(api_client)

        long_choice = "x" * 501
        resp = api_client.post("/me/game/turn", json={"choice": long_choice}, headers=_auth_headers())
        assert resp.status_code == 422

    def test_choice_at_max_length_accepted(self, api_client):
        """A choice of exactly 500 chars is accepted."""
        _create_game(api_client)
        _create_character(api_client)

        long_choice = "y" * 500
        resp = api_client.post("/me/game/turn", json={"choice": long_choice}, headers=_auth_headers())
        assert resp.status_code == 200

    def test_game_name_over_max_length_returns_422(self, api_client):
        """M-02: a game name exceeding 100 chars is rejected."""
        long_name = "x" * 101
        resp = api_client.post("/me/game", json={"name": long_name}, headers=_auth_headers())
        assert resp.status_code == 422

    def test_character_name_over_max_length_returns_422(self, api_client):
        """M-02: a character name exceeding 100 chars is rejected."""
        _create_game(api_client)
        long_name = "x" * 101
        resp = api_client.post("/me/game/character", json={"name": long_name}, headers=_auth_headers())
        assert resp.status_code == 422

    def test_game_name_control_chars_are_stripped(self, api_client):
        """M-02: control characters in game name are stripped (log injection prevention)."""
        # Name with newlines, tabs, null bytes — should be stripped to "Aria"
        dirty_name = "Ar\ri\na\t\x00"
        resp = api_client.post("/me/game", json={"name": dirty_name}, headers=_auth_headers())
        assert resp.status_code == 201
        assert resp.json()["name"] == "Aria"

    def test_character_name_control_chars_are_stripped(self, api_client):
        """M-02: control characters in character name are stripped."""
        _create_game(api_client)
        dirty_name = "He\rl\no\t\x00"
        resp = api_client.post("/me/game/character", json={"name": dirty_name}, headers=_auth_headers())
        assert resp.status_code == 201


class TestAuthEnvelope:
    def test_invalid_token_returns_401(self, api_client):
        resp = api_client.post(
            "/me/game",
            json={},
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthenticated"

    def test_no_token_dev_mode_allowed(self, api_client, monkeypatch):
        """With dev mode explicitly enabled, no auth token is accepted."""
        monkeypatch.setenv("GAMEBOOK_DEV_MODE", "1")
        resp = api_client.post("/me/game", json={})  # no Authorization header
        assert resp.status_code == 201

    def test_no_auth_configured_refuses_to_boot(self, monkeypatch):
        """Fail-closed at boot (T030, ADR-022): with neither GAMEBOOK_DEV_MODE
        nor OIDC configured, the app refuses to start rather than serving a
        public API reachable with the well-known dev token."""
        from starlette.testclient import TestClient

        from gamebook_web.api.app import app

        monkeypatch.delenv("GAMEBOOK_DEV_MODE", raising=False)
        monkeypatch.delenv("OIDC_JWKS_URI", raising=False)
        app.dependency_overrides.clear()
        with pytest.raises(RuntimeError, match="no authentication configured"):
            with TestClient(app):
                pass
