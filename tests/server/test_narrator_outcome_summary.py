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
