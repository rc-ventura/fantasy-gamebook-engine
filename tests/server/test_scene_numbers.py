"""Scene schema tests and API validation gate (CONTRACTS.md §10, Principle I, ADR-029).

After the narrator tool-use refactor (spec 007), the narrator calls MCP tools
directly during generation and narrates real results. The Scene model no longer
carries effects[]; TurnResponse no longer carries effects_applied.

Tests verify:
1. Scene schema invariants (non-empty narrative, choices, is_terminal).
2. TurnResponse has no effects_applied field (FR-003, SC-005).
3. Scene has no effects field (FR-002, SC-005).
4. Invalid narrator output → 422 (never stored, SC-004).
5. Character stats in turn response come from engine state (SC-001).
"""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from gamebook_web.harness.base import FakeNarrator
from gamebook_web.harness.scene import Choice, Scene


# ---------------------------------------------------------------------------
# Unit tests on the Scene schema itself
# ---------------------------------------------------------------------------

class TestSceneSchemaValidation:
    def test_valid_scene_accepts(self):
        scene = Scene(
            narrative="You stand at the crossroads.",
            choices=[Choice(id="1", label="Go north")],
        )
        assert scene.narrative

    def test_empty_narrative_rejected(self):
        with pytest.raises(ValidationError, match="narrative"):
            Scene(narrative="", choices=[])

    def test_whitespace_only_narrative_rejected(self):
        with pytest.raises(ValidationError, match="narrative"):
            Scene(narrative="   \n\t  ", choices=[])

    def test_terminal_scene_allows_empty_choices(self):
        scene = Scene(
            narrative="You have fallen. The adventure is over.",
            choices=[],  # terminal — death
        )
        assert scene.is_terminal

    def test_non_terminal_scene_has_choices(self):
        scene = Scene(
            narrative="The path forks ahead.",
            choices=[Choice(id="1", label="Go left"), Choice(id="2", label="Go right")],
        )
        assert not scene.is_terminal

    def test_scene_round_trips_json(self):
        scene = Scene(
            narrative="The mountain looms.",
            choices=[Choice(id="1", label="Climb")],
        )
        reconstructed = Scene.model_validate(scene.model_dump())
        assert reconstructed == scene


# ---------------------------------------------------------------------------
# Contract: Scene and TurnResponse have the simplified shape (FR-002, FR-003)
# ---------------------------------------------------------------------------

class TestSceneContractSimplified:
    """Scene is narrative + choices only; TurnResponse has no effects_applied."""

    def test_scene_has_no_effects_field(self):
        """FR-002: Scene must not contain an effects field after the refactor."""
        scene = Scene(narrative="Testing.", choices=[Choice(id="1", label="OK")])
        data = scene.model_dump()
        assert "effects" not in data, (
            "Scene.effects was removed in spec 007 — narrator calls MCP tools directly"
        )

    def test_turn_response_has_no_effects_applied_field(self):
        """FR-003: TurnResponse must not contain effects_applied after the refactor."""
        from gamebook_web.api.play import TurnResponse
        fields = TurnResponse.model_fields
        assert "effects_applied" not in fields, (
            "TurnResponse.effects_applied was removed in spec 007"
        )

    def test_turn_response_shape_matches_contract(self, api_client):
        """TurnResponse contains scene, character, world — nothing else (CONTRACTS.md §9)."""
        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        api_client.post(f"/campaigns/{cid}/character", json={"name": "ContractCheck"},
                        headers={"Authorization": "Bearer dev-token"})

        resp = api_client.post(f"/campaigns/{cid}/turn", json={},
                               headers={"Authorization": "Bearer dev-token"})
        assert resp.status_code == 200
        data = resp.json()

        assert "scene" in data
        assert "effects_applied" not in data, "effects_applied must not appear in TurnResponse"
        assert "effects" not in data.get("scene", {}), "effects must not appear in Scene"


# ---------------------------------------------------------------------------
# API validation gate: invalid narrator output → 422 (never stored)
# ---------------------------------------------------------------------------

class TestAPISceneValidationGate:
    """Invalid narrator output → 422 and the bad scene is never stored (SC-004)."""

    def test_empty_narrative_returns_422(self, api_client):
        """A narrator that raises → 422 invalid_scene."""
        from gamebook_web.api.app import app

        class _BadNarrator:
            async def narrate(self, campaign_id, context):
                raise ValueError("Narrator produced invalid output")

        app.state.narrator = _BadNarrator()

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        api_client.post(f"/campaigns/{cid}/character", json={"name": "BadTest"},
                        headers={"Authorization": "Bearer dev-token"})

        resp = api_client.post(f"/campaigns/{cid}/turn", json={},
                               headers={"Authorization": "Bearer dev-token"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_scene"

    def test_invalid_scene_never_stored(self, api_client):
        """After a 422, the scene is NOT stored in GET /scene."""
        from gamebook_web.api.app import app

        class _ErrorNarrator:
            async def narrate(self, campaign_id, context):
                raise RuntimeError("Catastrophic narrator failure")

        original_narrator = app.state.narrator
        app.state.narrator = _ErrorNarrator()

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        api_client.post(f"/campaigns/{cid}/character", json={"name": "FailTest"},
                        headers={"Authorization": "Bearer dev-token"})

        resp = api_client.post(f"/campaigns/{cid}/turn", json={},
                               headers={"Authorization": "Bearer dev-token"})
        assert resp.status_code == 422

        # Scene not stored
        scene_resp = api_client.get(f"/campaigns/{cid}/scene",
                                    headers={"Authorization": "Bearer dev-token"})
        assert scene_resp.json()["scene"] is None

        # Campaign still active (not corrupted)
        state_resp = api_client.get(f"/campaigns/{cid}",
                                    headers={"Authorization": "Bearer dev-token"})
        assert state_resp.json()["status"] == "active"

        app.state.narrator = original_narrator


# ---------------------------------------------------------------------------
# Engine authority: numbers come from engine state, not narrator (SC-001)
# ---------------------------------------------------------------------------

class TestEngineAuthorityNumbers:
    """Character stats in turn response come from real engine state, not the narrator."""

    def test_character_stats_come_from_engine_not_narrator(self, api_client):
        """Narrator returns a simple Scene with no tool calls (FakeNarrator).
        Character stats in the turn response must equal the engine-rolled initial values.
        """
        from gamebook_web.api.app import app

        app.state.narrator = FakeNarrator(scenes=[
            Scene(narrative="The wind howls.", choices=[Choice(id="1", label="Wait")]),
        ])

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        original = api_client.post(
            f"/campaigns/{cid}/character",
            json={"name": "NoToolCalls"},
            headers={"Authorization": "Bearer dev-token"},
        ).json()

        resp = api_client.post(f"/campaigns/{cid}/turn", json={},
                               headers={"Authorization": "Bearer dev-token"})
        assert resp.status_code == 200
        data = resp.json()

        char = data["character"]
        for attr in ("skill", "stamina", "luck"):
            assert char[attr]["current"] == original[attr]["current"], (
                f"Narrator must not change {attr} without an engine tool call"
            )
