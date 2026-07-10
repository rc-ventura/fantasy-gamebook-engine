from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.mcp import MCPToolset

from gamebook_web.harness.adventure_structure import (
    AdventureStructure,
    MechanicalSituationTemplate,
)
from gamebook_web.harness.narrator import NarratorBackend, NarratorContext


class IntentClassification(BaseModel):
    """Output of the `ClassifyIntent` node — one `pydantic_ai.Agent` call,
    structured output, no tools. Deliberately has no numeric game field (no
    `roll_result`, no `stamina`) — the classifier names an action, it never
    states an outcome, so it has no fabrication surface (research.md).
    """

    action: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    template: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class TurnOutcome(BaseModel):
    """What actually happened, handed to `Narrate` as settled fact — per
    spec.md's own Key Entities section, "never something the narration step
    invents itself."
    """

    action: str
    template: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)


@dataclass
class DispatchState:
    """`GraphRunContext` state threaded through one turn's graph run."""

    campaign_id: str
    toolset: MCPToolset
    context: NarratorContext
    adventure: AdventureStructure
    templates: dict[str, MechanicalSituationTemplate] = field(default_factory=dict)
    outcome: TurnOutcome | None = None  # written once by MechanicalDispatch; read post-run


@dataclass
class DispatchDeps:
    """Stable, reusable dependencies — constructed once per `DispatcherNarrator`
    instance (not per turn), injected into every graph run via `deps=`.
    """

    classifier_agent: Agent[None, IntentClassification]
    narrator: NarratorBackend


CONFIDENCE_THRESHOLD = 0.7


def build_classifier_agent(model: str) -> Agent[None, IntentClassification]:
    """Construct the intent classifier's Agent — structured output, no tools."""
    agent: Agent[None, IntentClassification] = Agent(
        model,
        name="intent_classifier",
        output_type=IntentClassification,
        instructions=(
            "You classify a solo-gamebook player's free-text action against a "
            "list of available mechanical actions for their current location. "
            "You never decide outcomes and never state a number — you only name "
            "which action (if any) the player's text corresponds to, and how "
            "confident you are. If no action clearly applies, or you are not "
            "confident, set action to null: the story continues freely rather "
            "than guessing at a mechanical consequence (a non-negotiable rule)."
        ),
    )

    @agent.output_validator
    def _validate_classification(c: IntentClassification) -> IntentClassification:
        if not (0.0 <= c.confidence <= 1.0):
            raise ModelRetry(f"confidence {c.confidence} is out of range [0, 1] — retry.")
        if c.action is not None and not c.action.strip():
            raise ModelRetry("action must be a non-empty string or null — retry.")
        return c

    return agent
