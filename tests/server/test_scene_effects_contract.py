"""Scene.effects[] ↔ MCP tool contract lockstep test (Principle III, T019).

Confirms that:
1. Every effect type in ``Scene`` maps to a known MCP tool name via
   ``EFFECT_TO_MCP_TOOL`` (no orphaned effect types).
2. Adding a new effect type to the schema without a matching entry in
   ``EFFECT_TO_MCP_TOOL`` causes this test to fail (Principle III).
3. The effect type literals in ``EffectType`` exactly match the keys in
   ``EFFECT_TO_MCP_TOOL`` (no extras, no gaps).

This is the merge gate for Principle III: if the narrator emits an effect
type that does not map to an MCP tool, the API would fail to apply it; this
test catches that failure at review time, not runtime.
"""

from __future__ import annotations

import re
import typing

import pytest


# ---------------------------------------------------------------------------
# Expected MCP tool names (from CONTRACTS.md §6) — the authoritative set
# ---------------------------------------------------------------------------

CONTRACTS_MCP_TOOLS = {
    "roll_dice",
    "test_luck",
    "update_character_sheet",   # note: effect alias is "update_character"
    "register_event",
    "update_world",
    "start_combat",
    "resolve_combat_round",
    "flee_combat",
    "end_combat",
    # Non-effect tools (not referenced by Scene.effects[]):
    # create_character, read_character_sheet, read_world, read_events,
    # read_summary, update_summary, archive_character, save_progress, load_progress
}

# Effect types that are aliases (effect type ≠ MCP tool name)
ALIASES = {
    "update_character": "update_character_sheet",
}


class TestEffectTypeLockstep:
    """Every effect type must map 1:1 to an MCP tool (Principle III)."""

    def test_effect_to_mcp_tool_covers_all_effect_types(self):
        """``EFFECT_TO_MCP_TOOL`` has an entry for every effect type."""
        from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL, EffectType

        # Extract the literal types from EffectType
        effect_types = set(typing.get_args(EffectType))
        mapping_keys = set(EFFECT_TO_MCP_TOOL.keys())

        assert effect_types == mapping_keys, (
            f"EFFECT_TO_MCP_TOOL is out of sync with EffectType.\n"
            f"In EffectType but not mapping: {effect_types - mapping_keys}\n"
            f"In mapping but not EffectType: {mapping_keys - effect_types}"
        )

    def test_mcp_tool_targets_are_in_known_tools(self):
        """Every target MCP tool in the mapping is a real engine tool."""
        from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL

        known_effect_targets = set(EFFECT_TO_MCP_TOOL.values())
        unknown = known_effect_targets - CONTRACTS_MCP_TOOLS
        assert not unknown, (
            f"EFFECT_TO_MCP_TOOL maps to unknown MCP tools: {unknown}\n"
            f"Update CONTRACTS.md §6 and add the tool to the engine first."
        )

    def test_aliases_are_documented(self):
        """Every alias (effect type ≠ tool name) is in the ALIASES dict."""
        from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL

        for effect_type, mcp_tool in EFFECT_TO_MCP_TOOL.items():
            if effect_type != mcp_tool:
                assert effect_type in ALIASES, (
                    f"Effect type {effect_type!r} maps to {mcp_tool!r} but is not "
                    f"declared as an alias in the contract. Add it to ALIASES."
                )
                assert ALIASES[effect_type] == mcp_tool, (
                    f"Alias mismatch: ALIASES[{effect_type!r}] = {ALIASES[effect_type]!r} "
                    f"but EFFECT_TO_MCP_TOOL says {mcp_tool!r}."
                )

    def test_no_duplicate_mcp_tool_targets(self):
        """Two different effect types must not map to the same MCP tool
        (unless intentional — add an explicit exception here if so)."""
        from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL

        seen: dict[str, str] = {}
        for effect_type, mcp_tool in EFFECT_TO_MCP_TOOL.items():
            if mcp_tool in seen:
                other = seen[mcp_tool]
                # Allow the one documented alias
                if {effect_type, other} <= set(ALIASES):
                    continue
                pytest.fail(
                    f"Two effect types map to the same MCP tool {mcp_tool!r}: "
                    f"{effect_type!r} and {other!r}."
                )
            seen[mcp_tool] = effect_type


class TestEffectSchemaIntegrity:
    """The Effect Pydantic model enforces the closed-type constraint."""

    def test_valid_effect_types_accepted(self):
        from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL, Effect

        for effect_type in EFFECT_TO_MCP_TOOL:
            effect = Effect(type=effect_type, params={})
            assert effect.type == effect_type

    def test_invalid_effect_type_raises_validation_error(self):
        from pydantic import ValidationError
        from gamebook_web.harness.scene import Effect

        with pytest.raises(ValidationError):
            Effect(type="invent_number", params={"stamina": 42})

    def test_effect_params_accept_nested_structures(self):
        """Effect params can carry complex structures (enemy lists, flags dicts)."""
        from gamebook_web.harness.scene import Effect

        effect = Effect(
            type="start_combat",
            params={
                "enemies": [
                    {"name": "Goblin", "skill": 5, "stamina": 4},
                    {"name": "Orc", "skill": 7, "stamina": 6},
                ],
                "flee_allowed": True,
            },
        )
        assert len(effect.params["enemies"]) == 2


class TestMCPServerExposesSameTools:
    """The MCP server exposes exactly the tools referenced as effect targets."""

    def test_mcp_server_has_all_effect_target_tools(self):
        """Every MCP tool referenced by EFFECT_TO_MCP_TOOL exists on the engine."""
        import asyncio
        import random

        from gamebook.combat.implementation import CombatService
        from gamebook.mcp.server import build_server
        from gamebook.storage.in_memory import InMemoryStorage
        from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL

        storage = InMemoryStorage()
        rng = random.Random(0)
        combat = CombatService(storage, rng)
        server = build_server(storage=storage, combat=combat, rng=rng)

        async def _tool_names():
            names = await server.list_tools()
            return {t.name for t in names}

        available = asyncio.run(_tool_names())
        targets = set(EFFECT_TO_MCP_TOOL.values())
        missing = targets - available
        assert not missing, (
            f"These effect-target MCP tools are NOT exposed by the engine server:\n"
            f"  {sorted(missing)}\n"
            f"Either add the tools to the engine or remove the effect types."
        )
