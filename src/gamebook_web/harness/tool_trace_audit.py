"""Post-audit detection for fabricated numbers in narrator tool calls.

Same belt-and-suspenders pattern as ``_assert_narrator_campaign`` (T006b): a
detection layer that runs after ``agent.run()`` completes, before the scene is
returned to the player. Logs warnings on divergence — does not raise, to avoid
breaking the turn on false positives.

Empirically validated against gpt-5-chat-latest (2026-07-05 live test):
  - Mode 1: narrator registered ``roll_result: 11`` in a ``jump_attempt``
    event and ``roll_result: 7`` in an ``examine_object`` event without ever
    calling ``roll_dice``.
  - Mode 4: narrator narrated a state change and registered it in an event
    without calling ``update_character_sheet`` or any combat tool.
"""

from __future__ import annotations

import logging

from pydantic_ai.messages import ModelMessage, ToolCallPart

logger = logging.getLogger(__name__)

# Uvicorn's default logging config only attaches handlers to ``uvicorn.*``
# loggers — the root logger has none, so warnings from this module would be
# silently discarded. Attach a StreamHandler so audit warnings reach stderr
# where ``docker logs`` and structured log collectors can see them.
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Event-data keys that signal a claim the engine was consulted
# ---------------------------------------------------------------------------

# Keys in register_event data that claim a dice/roll outcome was resolved.
# If any of these appear in an event's data but no roll_dice tool call exists
# in the same turn's message history, the narrator fabricated the number.
_ROLL_LIKE_EVENT_KEYS = frozenset({
    "roll_result",
    "roll",
    "dice_result",
    "roll_value",
    "dice_roll",
})

# Keys in register_event data that claim an attribute change happened.
# If any of these appear but no update_character_sheet / combat tool was called,
# the narrator narrated a state change without going through the engine.
_STATE_CLAIM_EVENT_KEYS = frozenset({
    "stamina_after_rest",
    "stamina_after",
    "stamina_change",
    "damage_dealt",
    "healing",
    "heal_amount",
    "luck_after",
    "luck_change",
})

_COMBAT_TOOLS = frozenset({
    "start_combat",
    "resolve_combat_round",
    "flee_combat",
    "end_combat",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_tool_calls(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Return all ToolCallPart instances from the message history, in order."""
    calls: list[ToolCallPart] = []
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                calls.append(part)
    return calls


# ---------------------------------------------------------------------------
# Public audit entry point
# ---------------------------------------------------------------------------

def assert_tool_trace_consistency(messages: list[ModelMessage]) -> None:
    """Detect fabricated numbers in register_event data (Modes 1 & 4).

    Checks:
      1. **Fabricated dice in events (Mode 1):** if any ``register_event``
         call's ``data`` dict contains roll-like keys (``roll_result``,
         ``dice_result``, etc.) but no ``roll_dice`` tool call exists in the
         turn's message history, the narrator invented the number without
         consulting the engine.

      2. **Claimed state change without engine tool (Mode 4):** if any
         ``register_event`` call's ``data`` claims an attribute change
         (``stamina_after_rest``, ``damage_dealt``, etc.) but neither
         ``update_character_sheet`` nor any combat tool was called, the
         narrator narrated a state change that never went through the engine.
    """
    calls = _extract_tool_calls(messages)
    tool_names_called = {c.tool_name for c in calls}

    roll_dice_called = "roll_dice" in tool_names_called
    state_tool_called = (
        "update_character_sheet" in tool_names_called
        or bool(tool_names_called & _COMBAT_TOOLS)
    )

    for c in calls:
        if c.tool_name != "register_event":
            continue
        args = c.args
        if not isinstance(args, dict):
            continue
        event_data = args.get("data")
        if not isinstance(event_data, dict):
            continue

        event_type = args.get("type", "unknown")

        # Check 1: roll-like claims without roll_dice
        roll_keys_found = _ROLL_LIKE_EVENT_KEYS & set(event_data)
        if roll_keys_found and not roll_dice_called:
            logger.warning(
                "assert_tool_trace_consistency: register_event(type=%r) "
                "claims roll keys %s but roll_dice was never called this turn. "
                "The narrator fabricated dice results in event data without "
                "consulting the engine (Mode 1). Investigate immediately.",
                event_type, sorted(roll_keys_found),
            )

        # Check 2: state-change claims without any state tool
        state_keys_found = _STATE_CLAIM_EVENT_KEYS & set(event_data)
        if state_keys_found and not state_tool_called:
            logger.warning(
                "assert_tool_trace_consistency: register_event(type=%r) "
                "claims state-change keys %s but neither update_character_sheet "
                "nor any combat tool was called this turn. The narrator narrated "
                "a state change that never went through the engine (Mode 4). "
                "Investigate immediately.",
                event_type, sorted(state_keys_found),
            )
