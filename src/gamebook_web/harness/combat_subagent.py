"""Combat subagent — delegated combat resolution (ADR-001 pattern, ADR-011).

When the narrator encounters a combat encounter it *delegates* to this
subagent, which drives the full fight (start → resolve rounds → flee/end)
through MCP tools.  The subagent shares the parent agent's MCP toolset via
``RunContext.deps``.

This module is used ONLY by ``PydanticNarrator`` (production path).  Tests use
``FakeNarrator`` + the explicit ``POST /combat/round`` endpoint instead.

Architecture note (ADR-001):
  The narrator calls the subagent as a tool; it returns a ``CombatResult``
  that the narrator uses to write the post-combat narrative.  No numbers are
  fabricated — all outcomes come from the engine's MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset

from gamebook_web.harness.scene import Scene


# ---------------------------------------------------------------------------
# Combat result type (returned to the parent narrator)
# ---------------------------------------------------------------------------

class CombatResult(BaseModel):
    """Structured outcome of a delegated combat — all numbers from MCP."""

    combat_id: str
    winner: str | None           # "hero" | "enemy" | None (escaped)
    rounds: int
    hero_final_stamina: int
    luck_spent: int
    drops: list[str] = []
    hero_alive: bool = True


# ---------------------------------------------------------------------------
# CombatDeps — shared per-run context
# ---------------------------------------------------------------------------

@dataclass
class CombatDeps:
    toolset: MCPToolset
    combat_id: str


# ---------------------------------------------------------------------------
# Combat subagent (ADR-001 agent-delegation pattern)
# ---------------------------------------------------------------------------

_COMBAT_SYSTEM = """
You are a combat resolution sub-agent.  Drive the fight round by round via MCP tools:
1. Call `resolve_combat_round` each round (set use_luck=true if the player wants it).
2. Stop when the round outcome `ended` is True.
3. Call `end_combat` to finalise.  Return the CombatResult.
NEVER invent numbers — read all outcomes from MCP tool results.
"""

_combat_agent: Agent[CombatDeps, CombatResult] = Agent(
    model=None,   # inherited from parent via agent delegation (ADR-011)
    output_type=CombatResult,
    system_prompt=_COMBAT_SYSTEM,
    deps_type=CombatDeps,
    name="combat_subagent",
)


async def resolve_combat(
    combat_id: str,
    toolset: MCPToolset,
    model: str,
    *,
    player_wants_luck: bool = False,
) -> CombatResult:
    """Run the combat subagent and return a structured result.

    Called from ``PydanticNarrator`` when the scene triggers combat.
    The ``toolset`` (already connected) is forwarded via deps.
    """
    deps = CombatDeps(toolset=toolset, combat_id=combat_id)
    prompt = (
        f"Run combat {combat_id}. "
        f"Player {'wants' if player_wants_luck else 'does not want'} to test luck each round."
    )
    result = await _combat_agent.run(
        prompt,
        model=model,
        deps=deps,
        toolsets=[toolset],
    )
    return result.output
