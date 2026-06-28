"""Scene — the validated narrator structured-output unit (CONTRACTS.md §10).

`Scene` is the contract between the narrator (swap boundary #3) and the
frontend / API client.  **Safety invariant**: a `Scene` carries no
narrator-fabricated numbers; `effects[]` reference engine *operations*, and
every numeric outcome comes from an MCP tool result (Principle I).

``Effect.type`` values are the exact MCP tool names (or their canonical web
aliases).  The mapping ``EFFECT_TO_MCP_TOOL`` (below) is the lockstep binding
required by CONTRACTS.md §10 / Principle III — adding an effect type without
a corresponding MCP tool and a CONTRACTS.md update is a bug.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Effect → MCP tool name mapping (CONTRACTS.md §6 + §10, Principle III)
# ---------------------------------------------------------------------------
EFFECT_TO_MCP_TOOL: dict[str, str] = {
    "roll_dice": "roll_dice",
    "test_luck": "test_luck",
    "update_character": "update_character_sheet",   # alias: effect uses short form
    "register_event": "register_event",
    "update_world": "update_world",
    "start_combat": "start_combat",
    "resolve_combat_round": "resolve_combat_round",
    "flee_combat": "flee_combat",
    "end_combat": "end_combat",
}

# Closed enum of allowed effect types — derived from the mapping so they stay
# in lockstep.  Test ``test_scene_effects_contract.py`` asserts parity.
EffectType = Literal[
    "roll_dice",
    "test_luck",
    "update_character",
    "register_event",
    "update_world",
    "start_combat",
    "resolve_combat_round",
    "flee_combat",
    "end_combat",
]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class Choice(BaseModel):
    """A numbered option offered to the player."""

    id: str    # stable id for the UI / API ("1", "2", …)
    label: str  # what the player sees


class Effect(BaseModel):
    """An engine operation to apply this turn — never a literal stat/dice value.

    ``type`` must be one of the known effect types (closed enum).  ``params``
    contains operation *parameters* only, never resulting values (the engine
    computes those via the MCP tool).
    """

    type: EffectType
    params: dict[str, Any] = {}


class Scene(BaseModel):
    """Validated narrator output for one turn.

    Invariants (CONTRACTS.md §10):
    - ``narrative`` non-empty.
    - ``choices`` may be empty only on terminal scenes (death/victory).
    - No ``Effect`` carries a literal resulting stat/dice value.

    The ``output_validator`` in ``harness/agent.py`` enforces the no-literal-
    number constraint at the PydanticAI layer; these validators enforce the
    structural invariants.
    """

    narrative: str
    choices: list[Choice] = []
    effects: list[Effect] = []

    @field_validator("narrative")
    @classmethod
    def narrative_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("narrative must not be empty")
        return v

    @property
    def is_terminal(self) -> bool:
        """True for death/victory scenes (no player choices)."""
        return len(self.choices) == 0
