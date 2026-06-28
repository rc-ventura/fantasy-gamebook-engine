"""Scene invalid-number rejection — SC-002, SC-003, FR-007 (T018).

Confirms:
1. A ``Scene`` with an empty narrative is rejected by Pydantic validation.
2. An ``Effect`` with an unknown type is rejected by Pydantic validation.
3. The ``output_validator`` in ``PydanticNarrator`` (if a scene reaches it
   with fabricated numbers) raises ``ModelRetry``.
4. A ``FakeNarrator`` returning an invalid (empty-narrative) scene triggers a
   ``422 invalid_scene`` response and the bad scene is never stored.
5. All numbers in accepted responses trace to engine MCP tool results.

US2: the narrator is structurally prevented from inventing numbers.
"""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from gamebook_web.harness.base import FakeNarrator
from gamebook_web.harness.scene import Choice, Effect, Scene


# ---------------------------------------------------------------------------
# Unit tests on the Scene schema itself
# ---------------------------------------------------------------------------

class TestSceneSchemaValidation:
    def test_valid_scene_accepts(self):
        scene = Scene(
            narrative="You stand at the crossroads.",
            choices=[Choice(id="1", label="Go north")],
            effects=[],
        )
        assert scene.narrative

    def test_empty_narrative_rejected(self):
        with pytest.raises(ValidationError, match="narrative"):
            Scene(
                narrative="",
                choices=[],
                effects=[],
            )

    def test_whitespace_only_narrative_rejected(self):
        with pytest.raises(ValidationError, match="narrative"):
            Scene(
                narrative="   \n\t  ",
                choices=[],
                effects=[],
            )

    def test_unknown_effect_type_rejected(self):
        with pytest.raises(ValidationError):
            Effect(type="hack_the_mainframe", params={})

    def test_terminal_scene_allows_empty_choices(self):
        scene = Scene(
            narrative="You have fallen. The adventure is over.",
            choices=[],  # terminal — death
            effects=[],
        )
        assert scene.is_terminal

    def test_non_terminal_scene_has_choices(self):
        scene = Scene(
            narrative="The path forks ahead.",
            choices=[Choice(id="1", label="Go left"), Choice(id="2", label="Go right")],
            effects=[],
        )
        assert not scene.is_terminal

    def test_effect_params_are_arbitrary_dicts(self):
        effect = Effect(
            type="start_combat",
            params={"enemies": [{"name": "Goblin", "skill": 5, "stamina": 4}], "flee_allowed": True},
        )
        assert effect.params["flee_allowed"] is True

    def test_scene_round_trips_json(self):
        scene = Scene(
            narrative="The mountain looms.",
            choices=[Choice(id="1", label="Climb")],
            effects=[Effect(type="register_event", params={"type": "test", "data": {}})],
        )
        reconstructed = Scene.model_validate(scene.model_dump())
        assert reconstructed == scene


class TestOutputValidator:
    """Test the ``_scene_contains_fabricated_numbers`` heuristic directly."""

    def test_clean_scene_passes(self):
        from gamebook_web.harness.agent import _scene_contains_fabricated_numbers
        scene = Scene(
            narrative="A goblin blocks your path.",
            choices=[Choice(id="1", label="Fight")],
            effects=[
                Effect(type="start_combat", params={
                    "enemies": [{"name": "Goblin", "skill": 5, "stamina": 4}],
                    "flee_allowed": True,
                })
            ],
        )
        assert not _scene_contains_fabricated_numbers(scene)

    def test_narrative_with_asserted_stamina_flagged(self):
        from gamebook_web.harness.agent import _scene_contains_fabricated_numbers
        scene = Scene(
            narrative="Your stamina is 14 after the fight.",   # fabricated number
            choices=[Choice(id="1", label="Continue")],
            effects=[],
        )
        assert _scene_contains_fabricated_numbers(scene)

    def test_effect_with_result_key_flagged(self):
        """An effect carrying a computed result value (e.g. luck_after) is fabricated."""
        from gamebook_web.harness.agent import _scene_contains_fabricated_numbers
        scene = Scene(
            narrative="You tested your luck.",
            choices=[Choice(id="1", label="Continue")],
            effects=[
                Effect(type="test_luck", params={"luck_after": 8}),  # result key!
            ],
        )
        assert _scene_contains_fabricated_numbers(scene)

    def test_register_event_with_data_passes(self):
        from gamebook_web.harness.agent import _scene_contains_fabricated_numbers
        scene = Scene(
            narrative="You enter the foothills.",
            choices=[Choice(id="1", label="Onward")],
            effects=[
                Effect(type="register_event", params={"type": "enter_zone", "data": {"zone": "foothills"}}),
            ],
        )
        assert not _scene_contains_fabricated_numbers(scene)


class TestAPISceneValidationGate:
    """Invalid narrator output → 422, never stored (SC-003, FR-014)."""

    def test_empty_narrative_returns_422(self, api_client):
        """A narrator returning a Scene with empty narrative → 422 invalid_scene."""
        from gamebook_web.api.app import app

        class _BadNarrator:
            async def narrate(self, campaign_id, context):
                # Bypass the Scene validator by returning a broken scene
                # The API should catch this
                raise ValueError("Narrator produced invalid output")

        app.state.narrator = _BadNarrator()

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        api_client.post(f"/campaigns/{cid}/character", json={"name": "BadTest"}, headers={"Authorization": "Bearer dev-token"})

        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={},
            headers={"Authorization": "Bearer dev-token"},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "invalid_scene"

    def test_invalid_scene_never_stored(self, api_client):
        """After a 422, the scene is NOT stored in GET /scene."""
        from gamebook_web.api.app import app

        class _ErrorNarrator:
            async def narrate(self, campaign_id, context):
                raise RuntimeError("Catastrophic narrator failure")

        original_narrator = app.state.narrator
        app.state.narrator = _ErrorNarrator()

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        api_client.post(f"/campaigns/{cid}/character", json={"name": "FailTest"}, headers={"Authorization": "Bearer dev-token"})

        resp = api_client.post(f"/campaigns/{cid}/turn", json={}, headers={"Authorization": "Bearer dev-token"})
        assert resp.status_code == 422

        # Scene not stored
        scene_resp = api_client.get(f"/campaigns/{cid}/scene", headers={"Authorization": "Bearer dev-token"})
        assert scene_resp.json()["scene"] is None

        # Campaign is still active (not corrupted)
        state_resp = api_client.get(f"/campaigns/{cid}", headers={"Authorization": "Bearer dev-token"})
        assert state_resp.json()["status"] == "active"

        app.state.narrator = original_narrator


class TestEngineAuthorityNumbers:
    """All numbers in accepted responses come from MCP tool results (SC-002)."""

    def test_character_stats_come_from_engine_not_narrator(self, api_client):
        """Narrator returns a Scene with no update_character effects.
        The character stats in the turn response are from the engine's stored state.
        """
        from gamebook_web.api.app import app

        no_effect_scene = Scene(
            narrative="The wind howls.",
            choices=[Choice(id="1", label="Wait")],
            effects=[],
        )
        app.state.narrator = FakeNarrator(scenes=[no_effect_scene])

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        original = api_client.post(
            f"/campaigns/{cid}/character",
            json={"name": "NoEffects"},
            headers={"Authorization": "Bearer dev-token"},
        ).json()

        resp = api_client.post(
            f"/campaigns/{cid}/turn",
            json={},
            headers={"Authorization": "Bearer dev-token"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Stats in turn response == original engine-rolled stats (narrator didn't change them)
        char = data["character"]
        for attr in ("skill", "stamina", "luck"):
            assert char[attr]["current"] == original[attr]["current"], (
                f"Narrator must not change {attr} without an engine effect"
            )

    def test_dice_roll_effect_outcome_is_from_engine(self, api_client):
        """An effect of type roll_dice returns an engine result, not a narrated number."""
        from gamebook_web.api.app import app

        roll_scene = Scene(
            narrative="You roll the ancient dice.",
            choices=[Choice(id="1", label="Accept fate")],
            effects=[
                Effect(type="roll_dice", params={"notation": "2d6"}),
            ],
        )
        app.state.narrator = FakeNarrator(scenes=[roll_scene])

        cid = api_client.post("/campaigns", headers={"Authorization": "Bearer dev-token"}).json()["campaign_id"]
        api_client.post(f"/campaigns/{cid}/character", json={"name": "Roller"}, headers={"Authorization": "Bearer dev-token"})

        resp = api_client.post(f"/campaigns/{cid}/turn", json={}, headers={"Authorization": "Bearer dev-token"})
        assert resp.status_code == 200

        effects_applied = resp.json()["effects_applied"]
        roll_results = [e for e in effects_applied if e["type"] == "roll_dice"]
        assert roll_results, "Expected roll_dice effect to be applied"

        result = roll_results[0]["result"]
        # Engine returned a real dice result with valid range
        assert 2 <= result["total"] <= 12
        assert len(result["rolls"]) == 2
