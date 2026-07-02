"""PydanticNarrator integration test with a mocked LLM (T093, SC-026, FR-047).

Exercises the REAL narrator pipeline — ``PydanticNarrator`` → pydantic-ai
``Agent`` → ``ScopedMCPToolset`` → in-process engine — with a ``FunctionModel``
standing in for the LLM. The mocked model:

  1. first requests a ``roll_dice`` MCP tool call (no campaign_id — the
     scoped toolset must inject it),
  2. reads the engine's REAL dice result from the tool return,
  3. emits a Scene whose narrative contains that exact number.

This proves the ADR-029 loop end to end: tools are called during generation,
real results land in the prose, and no ``effects``/``effects_applied`` fields
exist anywhere in the contract (Principle I enforced by design).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from starlette.testclient import TestClient

import pytest

from gamebook_web.harness.scene import Scene


AUTH = {"Authorization": "Bearer dev-token"}


def _extract_total(content: Any) -> int | None:
    """Pull DiceResult.total out of a tool return (dict or serialized)."""
    if isinstance(content, dict) and "total" in content:
        return int(content["total"])
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    match = re.search(r'"total":\s*(\d+)', text)
    return int(match.group(1)) if match else None


def _make_mock_llm(observed: dict[str, Any]):
    """LLM stand-in: call roll_dice once, then narrate the real result."""

    def mock_llm(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        dice_total: int | None = None
        for message in messages:
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name == "roll_dice":
                    dice_total = _extract_total(part.content)

        if dice_total is None:
            # First round: ask the engine for a real roll. Deliberately no
            # campaign_id — ScopedMCPToolset must inject it (ADR-018 D2).
            return ModelResponse(
                parts=[ToolCallPart(tool_name="roll_dice", args={"notation": "1d6"})]
            )

        observed["dice_total"] = dice_total
        scene = {
            "narrative": (
                f"You cast the bone dice across the flagstones — they come up "
                f"{dice_total}. The passage ahead exhales cold air."
            ),
            "choices": [
                {"id": "1", "label": "Press on into the dark"},
                {"id": "2", "label": "Turn back"},
            ],
            "terminal": False,
        }
        return ModelResponse(parts=[ToolCallPart(tool_name="final_result", args=scene)])

    return mock_llm


@pytest.fixture
def narrator_api_client(engine_server: Any):
    """API client whose narrator is a real PydanticNarrator on a mocked LLM."""
    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.harness.agent import PydanticNarrator
    from gamebook_web.sessions.campaign import CampaignRegistry

    observed: dict[str, Any] = {}
    toolset = MCPToolset(engine_server)
    narrator = PydanticNarrator(
        model=FunctionModel(_make_mock_llm(observed)),
        toolset=toolset,
    )

    mcp_host_mod.set_engine_toolset_factory(lambda: toolset)
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = narrator

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, observed

    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None  # type: ignore[assignment]
    app.state.narrator = None  # type: ignore[assignment]
    app.state.engine_toolset = None  # type: ignore[assignment]


class TestNarratorToolUseIntegration:
    def test_turn_narrates_real_engine_dice_result(self, narrator_api_client):
        client, observed = narrator_api_client

        assert client.post("/me/game", json={}, headers=AUTH).status_code == 201
        assert (
            client.post("/me/game/character", json={"name": "Aria"}, headers=AUTH).status_code
            == 201
        )

        resp = client.post("/me/game/turn", json={"choice": "explore"}, headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()

        # The narrator called roll_dice during generation and saw a real result.
        assert "dice_total" in observed, "narrator never received a roll_dice result"
        assert 1 <= observed["dice_total"] <= 6

        # That exact engine-produced number landed in the narrative (Principle I).
        assert str(observed["dice_total"]) in body["scene"]["narrative"]
        assert body["scene"]["choices"], "non-terminal scene must offer choices"

    def test_scene_and_turn_response_have_no_effects_fields(self, narrator_api_client):
        """spec 007 (ADR-029): the effects[] pattern is gone from the contract."""
        from gamebook_web.api.play import TurnResponse

        assert "effects" not in Scene.model_fields
        assert "effects_applied" not in TurnResponse.model_fields

        client, _ = narrator_api_client
        client.post("/me/game", json={}, headers=AUTH)
        client.post("/me/game/character", json={"name": "Aria"}, headers=AUTH)
        body = client.post("/me/game/turn", json={}, headers=AUTH).json()

        assert "effects" not in body["scene"]
        assert "effects_applied" not in body


class TestScopedMCPToolset:
    """Unit-level guarantees for the campaign_id-injection wrapper.

    Regression coverage for the real bug: a duck-typed wrapper was silently
    dropped by pydantic-ai's toolset-tree rebuild, so campaign_id never reached
    the engine. A real WrapperToolset dataclass subclass survives the rebuild.
    """

    def test_is_a_real_wrapper_toolset_subclass(self):
        """Must subclass WrapperToolset — a __getattr__ delegate is dropped at run start."""
        from pydantic_ai.toolsets import WrapperToolset

        from gamebook_web.harness.agent import ScopedMCPToolset

        assert issubclass(ScopedMCPToolset, WrapperToolset)

    def test_call_tool_injects_campaign_id_over_model_value(self):
        """The wrapper overrides whatever campaign_id the model supplied."""
        import asyncio

        from gamebook_web.harness.agent import ScopedMCPToolset

        seen: dict = {}

        class RecordingBase:
            async def call_tool(self, name, tool_args, ctx, tool):
                seen["args"] = tool_args
                return "ok"

        scoped = ScopedMCPToolset(wrapped=RecordingBase(), campaign_id="real-campaign")
        # Model tries to pass its own (wrong) campaign_id — must be discarded.
        result = asyncio.run(
            scoped.call_tool("roll_dice", {"notation": "1d6", "campaign_id": "attacker"}, None, None)
        )
        assert result == "ok"
        assert seen["args"]["campaign_id"] == "real-campaign"
        assert seen["args"]["notation"] == "1d6"

    def test_empty_campaign_id_is_rejected_at_construction(self):
        """A security-scoping value must never default to empty/unscoped."""
        import pytest

        from gamebook_web.harness.agent import ScopedMCPToolset

        with pytest.raises(ValueError, match="non-empty campaign_id"):
            ScopedMCPToolset(wrapped=object(), campaign_id="")

    def test_missing_campaign_id_is_a_type_error(self):
        import pytest

        from gamebook_web.harness.agent import ScopedMCPToolset

        with pytest.raises(TypeError):
            ScopedMCPToolset(wrapped=object())  # type: ignore[call-arg]
