"""Multi-campaign isolation tests (ADR-018, T008).

Proves that the storage_factory seam delivers independent storage backends per
campaign_id so that one campaign's state never bleeds into another's.

All tests use two in-memory backends — campaign A and campaign B — wired to a
single FastMCP server via a factory dict.  No subprocess, no disk, no AI.
"""

from __future__ import annotations

import asyncio
import json
import random

from gamebook.mcp.server import build_server
from gamebook.storage.in_memory import InMemoryStorage

SEED = 99


def _make_server():
    """Two distinct InMemoryStorage instances, one per campaign."""
    store_a = InMemoryStorage()
    store_b = InMemoryStorage()
    backends = {"campaign-a": store_a, "campaign-b": store_b}

    def factory(campaign_id: str) -> InMemoryStorage:
        if campaign_id not in backends:
            backends[campaign_id] = InMemoryStorage()
        return backends[campaign_id]

    rng = random.Random(SEED)
    server = build_server(storage_factory=factory, rng=rng)
    return server, store_a, store_b


def _call(server, tool: str, **arguments):
    result = asyncio.run(server.call_tool(tool, arguments))
    if isinstance(result, tuple):
        structured = result[1]
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured
    block = result[0]
    text = getattr(block, "text", None)
    if text is None:
        return result
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def test_characters_are_isolated_between_campaigns():
    """Creating a character in campaign A must not appear in campaign B."""
    server, store_a, store_b = _make_server()

    _call(server, "create_character", campaign_id="campaign-a", name="Aldric")

    # Campaign A sees the character
    sheet_a = _call(server, "read_character_sheet", campaign_id="campaign-a")
    assert sheet_a["name"] == "Aldric"

    # Campaign B has no character yet
    assert store_b.load_character() is None


def test_world_state_is_isolated_between_campaigns():
    """Updating world in campaign A must not affect campaign B's world."""
    server, store_a, store_b = _make_server()

    _call(server, "update_world", campaign_id="campaign-a", changes={"current_location": "grey_gate", "turn": 5})

    world_a = _call(server, "read_world", campaign_id="campaign-a")
    assert world_a["current_location"] == "grey_gate"
    assert world_a["turn"] == 5

    world_b = _call(server, "read_world", campaign_id="campaign-b")
    assert world_b["current_location"] == ""
    assert world_b["turn"] == 0


def test_events_are_isolated_between_campaigns():
    """Events appended to campaign A must not appear in campaign B's log."""
    server, store_a, store_b = _make_server()

    _call(server, "register_event", campaign_id="campaign-a", type="enter_zone", data={"zone": "foothills"})

    events_a = _call(server, "read_events", campaign_id="campaign-a")
    events_b = _call(server, "read_events", campaign_id="campaign-b")

    assert len(events_a) == 1
    assert events_a[0]["type"] == "enter_zone"
    assert events_b == []


def test_summary_is_isolated_between_campaigns():
    """Summary saved for campaign A must not affect campaign B's summary."""
    server, store_a, store_b = _make_server()

    _call(server, "update_summary", campaign_id="campaign-a", text="The hero reached the foothills.")

    summary_a = _call(server, "read_summary", campaign_id="campaign-a")
    summary_b = _call(server, "read_summary", campaign_id="campaign-b")

    assert "foothills" in summary_a
    assert summary_b == ""


def test_factory_creates_new_backend_on_demand():
    """Unknown campaign IDs must get a fresh, independent backend."""
    server, store_a, store_b = _make_server()

    # campaign-c is not pre-seeded in the factory dict
    _call(server, "create_character", campaign_id="campaign-c", name="Newcomer")

    sheet_c = _call(server, "read_character_sheet", campaign_id="campaign-c")
    assert sheet_c["name"] == "Newcomer"

    # campaign-a and campaign-b are still empty / unaffected
    assert store_a.load_character() is None
    assert store_b.load_character() is None


def test_concurrent_characters_in_two_campaigns():
    """Both campaigns can have independent heroes simultaneously."""
    server, store_a, store_b = _make_server()

    _call(server, "create_character", campaign_id="campaign-a", name="Hero A")
    _call(server, "create_character", campaign_id="campaign-b", name="Hero B")

    sheet_a = _call(server, "read_character_sheet", campaign_id="campaign-a")
    sheet_b = _call(server, "read_character_sheet", campaign_id="campaign-b")

    assert sheet_a["name"] == "Hero A"
    assert sheet_b["name"] == "Hero B"

    # Mutating A does not touch B
    _call(server, "update_character_sheet", campaign_id="campaign-a", changes={"gold": 100})
    sheet_b_after = _call(server, "read_character_sheet", campaign_id="campaign-b")
    assert sheet_b_after["gold"] == 0
