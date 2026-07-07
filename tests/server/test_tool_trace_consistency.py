"""Tests for assert_tool_trace_consistency — fabricated-number detection (Modes 1 & 4).

Validates the post-audit detection layer added after the 2026-07-05 live test
against gpt-5-chat-latest, which confirmed:
  - Mode 1: narrator registers ``roll_result: 11`` in event data without
    calling ``roll_dice`` (fabricated dice in event).
  - Mode 4: narrator narrates a state change and registers it in an event
    without calling ``update_character_sheet`` or any combat tool.

The audit is detection-only (logs warnings, never raises) — same pattern as
``_assert_narrator_campaign`` (T006b). These tests use ``caplog`` to assert
warnings are emitted on divergence and absent on clean turns.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from gamebook_web.harness.tool_trace_audit import assert_tool_trace_consistency


def _msg_with_tool_calls(calls: list[ToolCallPart]) -> ModelMessage:
    """Build a ModelMessage containing the given tool call parts."""
    return ModelResponse(parts=list(calls))


def _register_event(
    event_type: str,
    data: dict[str, Any],
) -> ToolCallPart:
    """Build a register_event ToolCallPart with campaign_id injected."""
    return ToolCallPart(
        tool_name="register_event",
        args={
            "campaign_id": "test-campaign",
            "type": event_type,
            "data": data,
        },
    )


def _roll_dice(notation: str = "1d6") -> ToolCallPart:
    return ToolCallPart(
        tool_name="roll_dice",
        args={"campaign_id": "test-campaign", "notation": notation},
    )


def _update_character_sheet(changes: dict[str, Any]) -> ToolCallPart:
    return ToolCallPart(
        tool_name="update_character_sheet",
        args={"campaign_id": "test-campaign", "changes": changes},
    )


def _start_combat() -> ToolCallPart:
    return ToolCallPart(
        tool_name="start_combat",
        args={
            "campaign_id": "test-campaign",
            "enemies": [{"name": "Goblin", "skill": 5, "stamina": 4}],
            "flee_allowed": True,
        },
    )


class TestAssertToolTraceConsistency:
    """Detection-only audit: warnings on divergence, silent on clean turns."""

    # ------------------------------------------------------------------
    # Check 1: fabricated dice in events (Mode 1)
    # ------------------------------------------------------------------

    def test_warns_when_event_has_roll_result_but_no_roll_dice(self, caplog):
        """Mode 1: register_event claims roll_result=11 but roll_dice never called."""
        messages = [_msg_with_tool_calls([
            _register_event("jump_attempt", {"success": True, "roll_result": 11}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert any("Mode 1" in r.message for r in caplog.records), (
            "should warn about fabricated roll_result without roll_dice"
        )
        assert any("roll_result" in r.message for r in caplog.records)

    def test_no_warning_when_roll_dice_called_before_event_with_roll_result(self, caplog):
        """Clean turn: roll_dice called, then event records the real result."""
        messages = [_msg_with_tool_calls([
            _roll_dice("2d6"),
            _register_event("trap", {"success": False, "roll_result": 7}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not any("Mode 1" in r.message for r in caplog.records), (
            "should NOT warn when roll_dice was actually called"
        )

    def test_warns_for_each_fabricated_roll_event(self, caplog):
        """Multiple events with fabricated rolls each produce a warning."""
        messages = [_msg_with_tool_calls([
            _register_event("jump_attempt", {"roll_result": 11}),
            _register_event("examine_object", {"roll_result": 7}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        mode1_warnings = [r for r in caplog.records if "Mode 1" in r.message]
        assert len(mode1_warnings) == 2, (
            "each fabricated-roll event should produce its own warning"
        )

    def test_no_warning_for_event_without_roll_keys(self, caplog):
        """Event with no roll-like keys should not trigger Check 1."""
        messages = [_msg_with_tool_calls([
            _register_event("move", {"to": "Dark Ravine", "from": "Mountain Pass"}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not any("Mode 1" in r.message for r in caplog.records)

    # ------------------------------------------------------------------
    # Check 2: state-change claims without engine tool (Mode 4)
    # ------------------------------------------------------------------

    def test_warns_when_event_claims_healing_but_no_state_tool_called(self, caplog):
        """Mode 4: register_event claims stamina_after_rest=16 but no
        update_character_sheet or combat tool was called."""
        messages = [_msg_with_tool_calls([
            _register_event("rest", {
                "effect": "stamina_recovered",
                "stamina_after_rest": 16,
            }),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert any("Mode 4" in r.message for r in caplog.records), (
            "should warn about state-change claim without any state tool"
        )
        assert any("stamina_after_rest" in r.message for r in caplog.records)

    def test_no_warning_when_update_character_sheet_called_before_healing_event(
        self, caplog
    ):
        """Clean turn: update_character_sheet called, then event records result."""
        messages = [_msg_with_tool_calls([
            _update_character_sheet({"stamina": {"current": 16}}),
            _register_event("rest", {"stamina_after_rest": 16}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not any("Mode 4" in r.message for r in caplog.records), (
            "should NOT warn when update_character_sheet was actually called"
        )

    def test_no_warning_when_combat_tool_called_before_damage_event(self, caplog):
        """Clean turn: start_combat called, then event records combat result."""
        messages = [_msg_with_tool_calls([
            _start_combat(),
            _register_event("combat_result", {
                "enemy": "Goblin",
                "rounds": 3,
                "winner": "hero",
                "damage_dealt": 2,
            }),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not any("Mode 4" in r.message for r in caplog.records), (
            "should NOT warn when a combat tool was actually called"
        )

    # ------------------------------------------------------------------
    # Combined / edge cases
    # ------------------------------------------------------------------

    def test_warns_for_both_modes_simultaneously(self, caplog):
        """A single turn can trigger both Mode 1 and Mode 4 warnings."""
        messages = [_msg_with_tool_calls([
            _register_event("trap", {"roll_result": 9, "damage_dealt": 3}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert any("Mode 1" in r.message for r in caplog.records)
        assert any("Mode 4" in r.message for r in caplog.records)

    def test_silent_on_completely_clean_turn(self, caplog):
        """A turn with only read tools and a move event should produce no warnings."""
        messages = [_msg_with_tool_calls([
            ToolCallPart(
                tool_name="read_character_sheet",
                args={"campaign_id": "test-campaign"},
            ),
            ToolCallPart(
                tool_name="read_world",
                args={"campaign_id": "test-campaign"},
            ),
            _register_event("move", {"to": "Hall", "from": "Pass"}),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not caplog.records, (
            "clean turn should produce zero warnings"
        )

    def test_empty_messages_is_silent(self, caplog):
        """No messages → no warnings."""
        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency([])

        assert not caplog.records

    def test_ignores_non_dict_event_data(self, caplog):
        """register_event with non-dict data should not crash or warn."""
        messages = [_msg_with_tool_calls([
            ToolCallPart(
                tool_name="register_event",
                args={
                    "campaign_id": "test-campaign",
                    "type": "note",
                    "data": "just a string, not a dict",
                },
            ),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not caplog.records

    def test_ignores_non_dict_args(self, caplog):
        """register_event with non-dict args should not crash."""
        messages = [_msg_with_tool_calls([
            ToolCallPart(
                tool_name="register_event",
                args="malformed-args-string",
            ),
        ])]

        with caplog.at_level("WARNING"):
            assert_tool_trace_consistency(messages)

        assert not caplog.records
