"""PydanticNarrator integration test with a mocked LLM (spec 009, ADR-033).

Pure narrator (spec 009): ``PydanticNarrator.narrate()`` runs with
``toolsets=[]`` — zero tools, mutating or read-only. It never calls MCP tools
during generation; it narrates from ``NarratorContext`` (including the
dispatcher's ``turn_outcome``, if any) as prompt content. This supersedes
ADR-029's "narrator calls tools directly" loop, which ADR-033 proved could be
bypassed by the model (fabricated stat changes reproduced with both a cheap
model and the strongest non-reasoning model available).

The former ``TestNarratorToolUseIntegration`` /
``TestNarratorWorldTrackingInstructions`` test classes drove and asserted on
that now-superseded loop (narrator-calls-``roll_dice``-then-narrates,
prompt-instructs-``update_world``) and have been removed rather than adapted —
there is no narrator-level equivalent left to test; that correctness now
belongs to the deterministic dispatcher and is covered by
``tests/server/test_dispatcher.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from starlette.testclient import TestClient

import pytest

from gamebook_web.harness.scene import Scene


AUTH = {"Authorization": "Bearer dev-token"}

_STUB_SCENE = {
    "narrative": (
        "You cast the bone dice across the flagstones. The passage ahead "
        "exhales cold air."
    ),
    "choices": [
        {"id": "1", "label": "Press on into the dark"},
        {"id": "2", "label": "Turn back"},
    ],
    "terminal": False,
}


def _make_pure_narrator_mock_llm():
    """LLM stand-in for a pure narrator: emits a Scene directly, no tool call.

    ``toolsets=[]`` means no regular tool is ever available — only the
    implicit structured-output "tool" (``final_result``) an Agent with
    ``output_type=Scene`` always exposes regardless of ``toolsets``.
    """

    def mock_llm(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=_STUB_SCENE)])

    return mock_llm


@pytest.fixture
def narrator_api_client(engine_server: Any):
    """API client whose narrator is a real PydanticNarrator on a mocked LLM."""
    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.harness.agent import PydanticNarrator
    from gamebook_web.sessions.campaign import CampaignRegistry

    toolset = MCPToolset(engine_server)
    narrator = PydanticNarrator(
        model=FunctionModel(_make_pure_narrator_mock_llm()),
    )

    mcp_host_mod.set_engine_toolset_factory(lambda: toolset)
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = narrator

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None  # type: ignore[assignment]
    app.state.narrator = None  # type: ignore[assignment]
    app.state.engine_toolset = None  # type: ignore[assignment]


class TestPureNarratorHasNoTools:
    """spec 009 (ADR-033): the narrator's ``agent.run()`` always gets
    ``toolsets=[]`` — structurally, not by allowlist convention.
    """

    def test_narrator_agent_run_receives_empty_toolsets(self):
        """Any attempted tool call by the model fails — no tool is ever
        available, not even a previously-allowlisted "safe" one.
        """
        from gamebook_web.harness.agent import PydanticNarrator
        from gamebook_web.harness.narrator import NarratorContext

        def attempts_a_tool_call(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            assert info.function_tools == [], "pure narrator must expose zero tools"
            return ModelResponse(
                parts=[ToolCallPart(tool_name="roll_dice", args={"notation": "1d6"})]
            )

        narrator = PydanticNarrator(model=FunctionModel(attempts_a_tool_call))
        ctx = NarratorContext(choice="test")

        with pytest.raises(UnexpectedModelBehavior):
            asyncio.run(narrator.narrate("test-campaign-no-tools", ctx))

    def test_narrator_narrates_from_turn_outcome_with_no_tool_calls(self):
        """The happy path: given a turn_outcome, the narrator returns a Scene
        without ever attempting a tool call.
        """
        from gamebook_web.harness.agent import PydanticNarrator
        from gamebook_web.harness.narrator import NarratorContext

        narrator = PydanticNarrator(
            model=FunctionModel(_make_pure_narrator_mock_llm()),
        )
        ctx = NarratorContext(
            choice="attack",
            turn_outcome={"action": "risky_action", "checks": [{"tool": "test_luck", "success": True}]},
        )
        scene = asyncio.run(narrator.narrate("test-campaign-outcome", ctx))
        assert scene.narrative
        assert scene.choices


# ---------------------------------------------------------------------------
# Contract hygiene: no effects[]/effects_applied anywhere (spec 007, ADR-029)
# ---------------------------------------------------------------------------

def test_scene_and_turn_response_have_no_effects_fields(narrator_api_client):
    """spec 007 (ADR-029): the effects[] pattern is gone from the contract —
    still true under the pure-narrator architecture (spec 009), unrelated to
    which component calls tools.
    """
    from gamebook_web.api.schemas import TurnResponse

    assert "effects" not in Scene.model_fields
    assert "effects_applied" not in TurnResponse.model_fields

    client = narrator_api_client
    client.post("/me/game", json={}, headers=AUTH)
    client.post("/me/game/character", json={"name": "Aria"}, headers=AUTH)
    body = client.post("/me/game/turn", json={}, headers=AUTH).json()

    assert "effects" not in body["scene"]
    assert "effects_applied" not in body
