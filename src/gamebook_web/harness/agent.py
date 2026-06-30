"""PydanticNarrator — production narrator backed by a PydanticAI Agent (ADR-011, ADR-029).

Architecture (CONTRACTS.md §10, ADR-011, ADR-029):
  - ``Agent(model, output_type=Scene, toolsets=[MCPToolset(...)])``
  - The narrator calls MCP tools directly during generation and incorporates
    the results into the narrative (Principle I — numbers come from the engine,
    never invented in prose).
  - ``output_validator`` rejects structurally invalid scenes only
    (empty narrative, non-terminal scene without choices).
  - The model string is injected at construction; never hardcoded.
  - Default model: ``anthropic:claude-opus-4-8`` (ADR-011).
  - Tests use ``FakeNarrator`` — this module is not imported during testing.

``PydanticNarrator`` reads the adventure module's lore (Ignarok SKILL.md) as a
system prompt addition so the narrator has access to static adventure content
(swap boundary #2 — swap the SKILL.md to swap adventures).
"""

from __future__ import annotations

from pathlib import Path

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
CRITICAL RULE — NUMBERS NEVER IN PROSE (Principle I, NON-NEGOTIABLE):
You have MCP engine tools. Call them during generation. See real results.
Use ONLY those real results in your narrative — never invent numbers.

How to handle common scenarios:
- Dice roll: call roll_dice → see the result → narrate that exact result.
- Luck test: call test_luck → see success/failure + luck decrement → narrate it.
- Character stat change: call update_character_sheet → see new values → narrate them.
- Combat: call start_combat → call resolve_combat_round (repeat until ended) →
  call end_combat → narrate the actual outcome with real round counts and damage.

Active combat rule (IMPORTANT for retries):
If you detect an active combat already in progress (world state shows a combat_id,
or your previous tool call started combat), DO NOT call start_combat again.
Continue the existing combat by calling resolve_combat_round until it ends.
Never start a new combat while one is already active.

Pre-combat decision:
If the player's choice triggers a fight, confirm the decision before calling
start_combat. Offer "fight or flee?" as a choice in the PREVIOUS scene.
Only call start_combat when the player has confirmed they are fighting.

Return a Scene with:
  narrative: 2–4 paragraphs, 2nd person, vivid and atmospheric, with REAL numbers.
  choices: 2–4 numbered options for the player (empty only on death or victory).
"""


def _load_adventure_lore() -> str:
    """Load the active adventure module's SKILL.md lore (swap boundary #2)."""
    if _IGNAROK_SKILL.exists():
        return _IGNAROK_SKILL.read_text(encoding="utf-8")
    return "Adventure: Grey Mountain. Defeat archmage Malachar to win."


# ---------------------------------------------------------------------------
# PydanticNarrator
# ---------------------------------------------------------------------------

class PydanticNarrator:
    """Production narrator: PydanticAI Agent emitting a validated Scene.

    The narrator calls MCP tools directly during agent.run() to resolve engine
    operations (combat, dice rolls, stat changes) and incorporates real results
    into the narrative. output_type=Scene constrains the final return value;
    it does not prevent tool calls during generation.

    The model string is injected and defaults to ``anthropic:claude-opus-4-8``.
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
            f"{_NUMBERS_NEVER_IN_PROSE_RULE}"
        )

        self._agent: Agent[None, Scene] = Agent(
            model=model,
            output_type=Scene,
            system_prompt=system,
            name="gamebook_narrator",
        )

        # Output validator: reject structurally invalid scenes only.
        # Fabricated-number detection is no longer needed — Principle I is
        # enforced by design (narrator calls tools and sees real results).
        @self._agent.output_validator
        def _validate_scene_structure(scene: Scene) -> Scene:
            if not scene.narrative.strip():
                raise ModelRetry("Scene narrative is empty — narrator must produce prose.")
            if not scene.is_terminal and not scene.choices:
                raise ModelRetry(
                    "Non-terminal scene must include player choices. "
                    "Add 2–4 numbered options or make the scene terminal (death/victory)."
                )
            return scene

    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:
        """Run the narrator agent and return a validated Scene.

        The narrator calls MCP tools during this run (tool calls happen inside
        agent.run()). The toolset is passed per-run so the same connection can
        be reused across turns without restarting the subprocess.
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
            "Narrate the next scene. Use MCP tools to read current state, resolve "
            "any combat or dice outcomes, and incorporate real results into your narrative. "
            "Return a Scene with narrative and choices."
        )

        return "\n\n".join(parts)
