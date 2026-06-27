"""PydanticNarrator — production narrator backed by a PydanticAI Agent (ADR-011).

Architecture (CONTRACTS.md §10, ADR-011):
  - ``Agent(model, output_type=Scene, toolsets=[MCPToolset(...)])``
  - ``output_validator`` raises ``ModelRetry`` on any ``Scene`` carrying a
    literal number (Principle I — code invariant independent of the model).
  - The model string is injected at construction; never hardcoded.
  - Default model: ``anthropic:claude-opus-4-8`` (ADR-011).
  - Tests use ``FakeNarrator`` — this module is not imported during testing.

``PydanticNarrator`` reads the adventure module's lore (Ignarok SKILL.md) as a
system prompt addition so the narrator has access to static adventure content
(swap boundary #2 — swap the SKILL.md to swap adventures).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.mcp import MCPToolset

from gamebook_web.harness.base import NarratorContext
from gamebook_web.harness.scene import Scene

# ---------------------------------------------------------------------------
# Default model and adventure-module lore path
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "anthropic:claude-opus-4-8"
_IGNAROK_SKILL = (
    Path(__file__).resolve().parents[3]  # repo root
    / ".claude" / "skills" / "ignarok" / "SKILL.md"
)

_NUMBERS_NEVER_IN_PROSE_RULE = """
CRITICAL RULE — NUMBERS NEVER IN PROSE:
You must NEVER invent numbers, roll dice, or assert stat values in your narrative.
Every number (dice roll, stamina damage, luck change, gold gain) must come from an MCP
tool result via effects[].  Your Scene's effects[] describe ENGINE OPERATIONS to perform,
not their outcomes.  The engine executes them; you narrate.
"""


def _load_adventure_lore() -> str:
    """Load the active adventure module's SKILL.md lore (swap boundary #2)."""
    if _IGNAROK_SKILL.exists():
        return _IGNAROK_SKILL.read_text(encoding="utf-8")
    return "Adventure: Grey Mountain. Defeat archmage Malachar to win."


# ---------------------------------------------------------------------------
# Output validator — Principle I gate (FR-007, SC-003)
# ---------------------------------------------------------------------------

# Pattern that catches literal numbers in Effect.params values.
# We allow numbers that are valid *parameters* (e.g. flee_allowed=True,
# enemy skill/stamina for start_combat) but reject results sneaking through.
# The heuristic: params key names that carry "result" values are banned.
_RESULT_KEYS = frozenset({
    "result", "total", "roll", "rolls", "current", "new_value",
    "damage", "stamina_after", "luck_after", "hero_stamina",
    "hero_as", "enemy_as",
})


def _scene_contains_fabricated_numbers(scene: Scene) -> bool:
    """Return True if the scene carries narrator-fabricated result values."""

    def _scan(obj: Any) -> bool:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in _RESULT_KEYS and isinstance(v, (int, float)):
                    return True
                if _scan(v):
                    return True
        elif isinstance(obj, list):
            return any(_scan(item) for item in obj)
        elif isinstance(obj, str):
            # Reject prose that asserts a stat value directly, e.g. "your stamina is 14"
            if re.search(r"\b(stamina|skill|luck|gold)\s+(is|was|becomes?|dropped? to)\s+\d+", obj, re.I):
                return True
        return False

    for effect in scene.effects:
        if _scan(effect.params):
            return True
    return _scan(scene.narrative)


# ---------------------------------------------------------------------------
# PydanticNarrator
# ---------------------------------------------------------------------------

class PydanticNarrator:
    """Production narrator: PydanticAI Agent emitting a validated Scene.

    The model string is injected and defaults to ``anthropic:claude-opus-4-8``.
    The engine MCP toolset (``MCPToolset``) is shared with the API layer
    (already entered as an async context manager in the app lifespan).

    ``ANTHROPIC_API_KEY`` must be set in the environment for Anthropic models.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        toolset: MCPToolset | None = None,
    ) -> None:
        self._model = model
        self._toolset = toolset

        lore = _load_adventure_lore()
        system = (
            f"You are the Game Master narrator for a Fighting Fantasy–style gamebook.\n\n"
            f"ADVENTURE MODULE LORE:\n{lore}\n\n"
            f"{_NUMBERS_NEVER_IN_PROSE_RULE}\n\n"
            "Produce a Scene with:\n"
            "  narrative: 2–4 paragraphs, 2nd person, vivid and atmospheric.\n"
            "  choices: 2–4 numbered options for the player (empty on death/victory).\n"
            "  effects: engine operations to apply this turn — use MCP tools, never raw values.\n"
        )

        self._agent: Agent[None, Scene] = Agent(
            model=model,
            output_type=Scene,
            system_prompt=system,
            name="gamebook_narrator",
        )

        # Register the output validator (Principle I gate)
        @self._agent.output_validator
        def _validate_no_fabricated_numbers(scene: Scene) -> Scene:
            if _scene_contains_fabricated_numbers(scene):
                raise ModelRetry(
                    "The scene contains narrator-fabricated numbers. "
                    "Use effects[] with engine operation params only — "
                    "never assert stat/dice result values directly."
                )
            return scene

    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:
        """Run the narrator agent and return a validated Scene.

        The toolset is passed per-run so the same toolset (with the active MCP
        connection) can be re-used across turns without restarting the subprocess.
        """
        prompt = self._build_prompt(context)

        toolsets = [self._toolset] if self._toolset else []
        result = await self._agent.run(
            prompt,
            toolsets=toolsets,
        )
        return result.output

    # ------------------------------------------------------------------

    def _build_prompt(self, ctx: NarratorContext) -> str:
        parts: list[str] = []

        if ctx.summary:
            parts.append(f"STORY SO FAR:\n{ctx.summary}")

        if ctx.character:
            sheet = ctx.character
            parts.append(
                f"HERO STATE: {sheet.get('name', 'Unknown')} — "
                f"skill {sheet.get('skill', {}).get('current', '?')}, "
                f"stamina {sheet.get('stamina', {}).get('current', '?')}, "
                f"luck {sheet.get('luck', {}).get('current', '?')}, "
                f"alive={sheet.get('alive', True)}"
            )

        if ctx.world:
            parts.append(f"LOCATION: {ctx.world.get('current_location', 'unknown')}")

        if ctx.recent_events:
            last = ctx.recent_events[-3:]  # last 3 events
            parts.append("RECENT EVENTS:\n" + "\n".join(str(e) for e in last))

        if ctx.choice is not None:
            parts.append(f"PLAYER CHOICE: {ctx.choice}")
        else:
            parts.append("PLAYER ACTION: start of session / fresh turn")

        parts.append(
            "Narrate the next scene. Use MCP tools to read current state. "
            "Return a Scene with narrative, choices, and effects[]."
        )

        return "\n\n".join(parts)
