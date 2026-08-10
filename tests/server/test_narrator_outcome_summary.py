"""Turn-outcome summarization for the narrator prompt (issue #27).

Regression coverage for a live, confirmed bug: with `hero_damage=0` in every
combat round, the narrator (`openai:gpt-4o-mini`) still narrated the enemy
landing a hit ("barely grazing you") — a raw Python-dict repr of `checks`
required the model to aggregate "was the hero ever hit across N rounds"
itself. `_summarize_turn_outcome` precomputes that fact instead.
"""

from __future__ import annotations

import asyncio

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gamebook_web.harness.agent import PydanticNarrator, _summarize_turn_outcome
from gamebook_web.harness.narrator import NarratorContext

_STUB_SCENE = {
    "narrative": "You catch your breath, unscathed.",
    "choices": [{"id": "1", "label": "Press on"}],
    "terminal": False,
}


def _combat_outcome(*, hero_damage_per_round: list[int], enemy_damage_per_round: list[int]) -> dict:
    """Build a `TurnOutcome`-shaped dict for N combat rounds.

    A round where the enemy hits costs the hero damage; a round where the
    hero hits costs the enemy damage — mirrors `CombatRound`'s own
    `hitter`/`damage_applied` shape exactly (graph.py).
    """
    checks = []
    for hero_dmg, enemy_dmg in zip(hero_damage_per_round, enemy_damage_per_round):
        if hero_dmg:
            checks.append({"tool": "resolve_combat_round", "result": {"hitter": "enemy", "damage_applied": hero_dmg, "ended": False}})
        elif enemy_dmg:
            checks.append({"tool": "resolve_combat_round", "result": {"hitter": "hero", "damage_applied": enemy_dmg, "ended": False}})
        else:
            checks.append({"tool": "resolve_combat_round", "result": {"hitter": None, "damage_applied": 0, "ended": False}})
    checks.append({"tool": "end_combat", "result": {"winner": "hero"}})
    return {"action": "combat", "template": "combat", "checks": checks, "final_state": {}}


class TestSummarizeTurnOutcome:
    def test_hero_never_hit_says_so_explicitly_and_forbids_narrating_a_hit(self):
        outcome = _combat_outcome(hero_damage_per_round=[0, 0, 0], enemy_damage_per_round=[3, 0, 4])
        summary = _summarize_turn_outcome(outcome)

        assert "did NOT land a single hit" in summary
        assert "Do not narrate the hero being struck, grazed, wounded" in summary

    def test_hero_hit_reports_the_real_aggregate(self):
        outcome = _combat_outcome(hero_damage_per_round=[2, 0, 3], enemy_damage_per_round=[0, 0, 0])
        summary = _summarize_turn_outcome(outcome)

        assert "The enemy hit the hero 2 time(s), for 5 total damage." in summary
        assert "The hero did NOT land a single hit this fight." in summary

    def test_no_checks_at_all(self):
        assert _summarize_turn_outcome({"action": "look", "checks": []}) == "(no mechanical checks this turn)"

    def test_non_combat_check_is_listed_compactly(self):
        outcome = {
            "action": "risky_action",
            "checks": [{"tool": "test_luck", "result": {"success": True}}],
        }
        summary = _summarize_turn_outcome(outcome)
        assert "test_luck" in summary
        assert "success" in summary


class TestNarratorPromptCarriesTheSummary:
    def test_prompt_sent_to_the_model_contains_the_no_hit_instruction(self):
        """End-to-end through PydanticNarrator.narrate(): the *actual* prompt
        the model receives must carry the precomputed fact, not a raw repr.
        """
        captured: dict[str, str] = {}

        def mock_llm(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            # The user prompt is the last part of the first (only) request.
            captured["prompt"] = str(messages[-1].parts[-1].content)
            return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=_STUB_SCENE)])

        narrator = PydanticNarrator(model=FunctionModel(mock_llm))
        outcome = _combat_outcome(hero_damage_per_round=[0, 0], enemy_damage_per_round=[5, 0])
        ctx = NarratorContext(choice="attack", turn_outcome=outcome)

        asyncio.run(narrator.narrate("test-campaign-no-hit", ctx))

        assert "did NOT land a single hit" in captured["prompt"]
        assert "{'tool': 'resolve_combat_round'" not in captured["prompt"]


class TestOutputValidatorSemanticGuard:
    """Defense-in-depth (issue #27): even if the prompt fix fails to prevent
    it, a narrative asserting the hero was hit when `hero_damage_taken == 0`
    is rejected with ModelRetry and the model is asked to correct itself —
    the same mechanism `_validate_scene_structure` already uses for
    structural violations (empty narrative, missing choices).
    """

    def _retrying_model(self, first_narrative: str, second_narrative: str):
        """FunctionModel that returns `first_narrative` on call 1 and
        `second_narrative` on every call after — simulates the model
        correcting itself in response to a ModelRetry.
        """
        calls = {"n": 0}

        def mock_llm(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            calls["n"] += 1
            narrative = first_narrative if calls["n"] == 1 else second_narrative
            scene = {**_STUB_SCENE, "narrative": narrative}
            return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=scene)])

        return FunctionModel(mock_llm), calls

    def test_retries_when_narrative_claims_a_hit_that_never_happened(self):
        model, calls = self._retrying_model(
            first_narrative="The guardian's blade grazes you, drawing a thin line of blood.",
            second_narrative="The guardian's blade whistles past, missing you entirely.",
        )
        narrator = PydanticNarrator(model=model)
        outcome = _combat_outcome(hero_damage_per_round=[0, 0], enemy_damage_per_round=[3, 0])
        ctx = NarratorContext(choice="attack", turn_outcome=outcome)

        scene = asyncio.run(narrator.narrate("test-campaign-guard-retry", ctx))

        assert calls["n"] == 2, "the fabricated-hit narrative must be rejected once, then accepted"
        assert "grazes you" not in scene.narrative
        assert scene.narrative == "The guardian's blade whistles past, missing you entirely."

    def test_does_not_retry_when_narrative_makes_no_hit_claim(self):
        model, calls = self._retrying_model(
            first_narrative="The guardian's blade whistles past, missing you entirely.",
            second_narrative="(should never be reached)",
        )
        narrator = PydanticNarrator(model=model)
        outcome = _combat_outcome(hero_damage_per_round=[0], enemy_damage_per_round=[3])
        ctx = NarratorContext(choice="attack", turn_outcome=outcome)

        asyncio.run(narrator.narrate("test-campaign-guard-no-fire", ctx))

        assert calls["n"] == 1, "a narrative with no hit claim must not trigger the guard"

    def test_allows_a_hit_claim_when_the_hero_really_was_hit(self):
        """No false positive: when the outcome says the hero WAS hit, the
        same phrasing that would be a fabrication elsewhere is correct here.
        """
        model, calls = self._retrying_model(
            first_narrative="The guardian's blade cuts you, and pain flares along your arm.",
            second_narrative="(should never be reached)",
        )
        narrator = PydanticNarrator(model=model)
        outcome = _combat_outcome(hero_damage_per_round=[4], enemy_damage_per_round=[0])
        ctx = NarratorContext(choice="attack", turn_outcome=outcome)

        asyncio.run(narrator.narrate("test-campaign-guard-real-hit", ctx))

        assert calls["n"] == 1, "a true hit claim must not be rejected"

    def test_guard_is_inert_without_a_turn_outcome(self):
        """A narrative-free turn (no mechanical stakes) has no outcome to
        check against — the guard must not error or misfire.
        """
        model, calls = self._retrying_model(
            first_narrative="A blade grazes you in an old memory you recount to yourself.",
            second_narrative="(should never be reached)",
        )
        narrator = PydanticNarrator(model=model)
        ctx = NarratorContext(choice="reminisce", turn_outcome=None)

        asyncio.run(narrator.narrate("test-campaign-guard-no-outcome", ctx))

        assert calls["n"] == 1, "with no turn_outcome, the hit-fabrication guard has nothing to check"
