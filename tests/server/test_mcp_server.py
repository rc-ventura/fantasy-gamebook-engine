"""Server/tool unit-integration tests for the MCP façade.

These exercise the server through ``build_server`` with an in-memory storage, a
real ``CombatService``, and a seeded ``random.Random`` — so they are fast,
deterministic, and touch no disk. They prove the façade orchestrates the engine
correctly and honours the CONTRACTS §6 tool contract. The broad end-to-end flow
lives in ``tests/qa`` (owned by QA); these stay focused on the tool surface.
"""

from __future__ import annotations

import asyncio
import json
import random
import re

import pytest

from gamebook.combate.implementation import CombatService
from gamebook.mcp.server import build_server
from gamebook.storage.in_memory import InMemoryStorage

# The exact 17 tools mandated by CONTRACTS §6, in contract order.
EXPECTED_TOOLS = [
    "roll_dice",
    "test_luck",
    "create_character",
    "read_character_sheet",
    "update_character_sheet",
    "read_world",
    "update_world",
    "register_event",
    "read_events",
    "read_summary",
    "update_summary",
    "start_combat",
    "resolve_combat_round",
    "flee_combat",
    "end_combat",
    "archive_character",
    "save_progress",
    "load_progress",
]

_TOOL_NAME_RE = re.compile(r"^[a-z0-9_]+$")


# --------------------------------------------------------------------------- helpers
@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def server(storage: InMemoryStorage):
    rng = random.Random(12345)
    combat = CombatService(storage, rng)
    return build_server(storage, combat, rng)


def call(server, tool: str, **arguments):
    """Invoke a tool synchronously and return its structured result.

    FastMCP returns ``(content, structured)`` for model/dict returns and a bare
    content list otherwise; this normalises both to the structured value.
    """
    result = asyncio.run(server.call_tool(tool, arguments))
    if isinstance(result, tuple):
        structured = result[1]
        # FastMCP wraps non-object returns (list/str/scalar) as {"result": ...}.
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


# --------------------------------------------------------------------------- discovery
def test_server_builds_and_lists_all_17_tools(server):
    names = [tool.name for tool in asyncio.run(server.list_tools())]
    assert sorted(names) == sorted(EXPECTED_TOOLS)
    assert len(names) == 18


def test_tool_names_match_required_pattern(server):
    names = [tool.name for tool in asyncio.run(server.list_tools())]
    for name in names:
        assert _TOOL_NAME_RE.match(name), f"tool name {name!r} violates ^[a-z0-9_]+$"


# --------------------------------------------------------------------------- character flow
def test_full_tool_flow(server, storage):
    # create_character
    sheet = call(server, "create_character", name="Aldric")
    assert sheet["name"] == "Aldric"
    assert sheet["alive"] is True
    assert 7 <= sheet["skill"]["initial"] <= 12
    assert 14 <= sheet["stamina"]["initial"] <= 24
    assert 7 <= sheet["luck"]["initial"] <= 12

    # read_character_sheet reflects persisted state
    read = call(server, "read_character_sheet")
    assert read == sheet

    # update_character_sheet — merge attribute sub-dict + replace scalar/list
    target_stamina = sheet["stamina"]["initial"] - 3
    updated = call(
        server,
        "update_character_sheet",
        changes={
            "stamina": {"current": target_stamina},
            "gold": 25,
            "inventory": ["sword", "torch"],
        },
    )
    assert updated["stamina"]["current"] == target_stamina
    assert updated["stamina"]["initial"] == sheet["stamina"]["initial"]  # merge kept initial
    assert updated["gold"] == 25
    assert updated["inventory"] == ["sword", "torch"]

    # start_combat → resolve rounds → end_combat
    combat = call(
        server,
        "start_combat",
        enemies=[{"name": "Goblin", "skill": 5, "stamina": 4}],
        flee_allowed=True,
    )
    combat_id = combat["combat_id"]
    assert combat["ended"] is False

    outcome = None
    for _ in range(50):
        outcome = call(server, "resolve_combat_round", combat_id=combat_id, use_luck=False)
        assert outcome["hitter"] in {"hero", "enemy", "tie"}
        if outcome["ended"]:
            break
    assert outcome is not None and outcome["ended"] is True

    final = call(server, "end_combat", combat_id=combat_id)
    assert final["winner"] in {"hero", "enemy", None}
    assert final["rounds"] >= 1
    # combat record is removed on end_combat
    assert storage.load_combat(combat_id) is None


def test_create_character_raises_when_living_exists(server):
    call(server, "create_character", name="First")
    with pytest.raises(Exception, match="living character already exists"):
        call(server, "create_character", name="Second")


def test_create_character_replaces_dead(server, storage):
    call(server, "create_character", name="Doomed")
    # Kill the hero, then a new character may replace them.
    call(server, "update_character_sheet", changes={"alive": False})
    replacement = call(server, "create_character", name="Heir")
    assert replacement["name"] == "Heir"
    assert replacement["alive"] is True


def test_invalid_update_unknown_field_leaves_state_unchanged(server, storage):
    call(server, "create_character", name="Aldric")
    before = storage.load_character()
    with pytest.raises(Exception, match="unknown character field"):
        call(server, "update_character_sheet", changes={"hp": 99})
    assert storage.load_character() == before


def test_invalid_update_overheal_leaves_state_unchanged(server, storage):
    sheet = call(server, "create_character", name="Aldric")
    before = storage.load_character()
    over = sheet["stamina"]["initial"] + 5
    with pytest.raises(Exception):  # dominio invariant: current must not exceed initial
        call(server, "update_character_sheet", changes={"stamina": {"current": over}})
    assert storage.load_character() == before


# --------------------------------------------------------------------------- dice / luck
def test_roll_dice_uses_engine(server):
    result = call(server, "roll_dice", notation="2d6")
    assert len(result["rolls"]) == 2
    assert result["total"] == sum(result["rolls"])


def test_roll_dice_invalid_notation_raises(server):
    with pytest.raises(Exception):
        call(server, "roll_dice", notation="banana")


def test_test_luck_spends_one_luck(server, storage):
    call(server, "create_character", name="Aldric")
    before = storage.load_character().luck.current
    result = call(server, "test_luck")
    assert result["luck_after"] == before - 1
    assert storage.load_character().luck.current == before - 1
    assert isinstance(result["success"], bool)


def test_test_luck_without_character_raises(server):
    with pytest.raises(Exception, match="no character sheet"):
        call(server, "test_luck")


# --------------------------------------------------------------------------- world / events / summary
def test_register_and_read_events(server):
    created = call(server, "register_event", type="enter_zone", data={"zone": "foothills"})
    assert created["type"] == "enter_zone"
    assert created["data"] == {"zone": "foothills"}
    assert isinstance(created["timestamp"], str) and created["timestamp"]

    events = call(server, "read_events")
    assert len(events) == 1
    assert events[0]["type"] == "enter_zone"


def test_read_world_returns_default(server):
    world = call(server, "read_world")
    assert world["turn"] == 0
    assert world["current_location"] == ""


def test_update_world_roundtrips_through_mcp(server):
    updated = call(
        server,
        "update_world",
        changes={
            "current_location": "grey_gate",
            "turn": 7,
            "flags": {"door_open": True},
        },
    )
    assert updated["current_location"] == "grey_gate"
    assert updated["turn"] == 7
    assert updated["flags"] == {"door_open": True}

    world = call(server, "read_world")
    assert world["current_location"] == "grey_gate"
    assert world["turn"] == 7
    assert world["flags"]["door_open"] is True


def test_update_world_merges_flags_key_wise(server):
    call(server, "update_world", changes={"flags": {"door_open": True}})
    # A second update sets one flag without dropping the first.
    updated = call(server, "update_world", changes={"flags": {"malachar_defeated": True}})
    assert updated["flags"] == {"door_open": True, "malachar_defeated": True}


def test_update_world_then_event_and_archive_use_real_turn(server, storage):
    call(server, "create_character", name="Aldric")
    call(server, "update_world", changes={"turn": 12, "current_location": "grey_summit"})

    # register_event stamps the persisted turn (not a narrated number).
    event = call(server, "register_event", type="checkpoint", data={})
    assert event["turn"] == 12

    # archive_character records the real turn count and location.
    call(server, "archive_character", destination="hall_of_fame")
    record = storage._archives["hall_of_fame"][0]
    assert record.turns == 12
    assert record.location == "grey_summit"


def test_update_world_unknown_field_leaves_state_unchanged(server, storage):
    call(server, "update_world", changes={"current_location": "grey_gate", "turn": 3})
    before = storage.load_world()
    with pytest.raises(Exception, match="unknown world field"):
        call(server, "update_world", changes={"weather": "stormy"})
    assert storage.load_world() == before


def test_update_world_invalid_turn_leaves_state_unchanged(server, storage):
    call(server, "update_world", changes={"turn": 3})
    before = storage.load_world()
    with pytest.raises(Exception):  # dominio invariant: turn >= 0
        call(server, "update_world", changes={"turn": -1})
    assert storage.load_world() == before


def test_update_and_read_summary(server):
    ack = call(server, "update_summary", text="The hero reached the gate.")
    assert ack == {"ok": True}
    summary = call(server, "read_summary")
    assert "gate" in summary


# --------------------------------------------------------------------------- combat helpers
def test_start_combat_rejects_empty_enemy_list(server, storage):
    call(server, "create_character", name="Aldric")
    with pytest.raises(Exception, match="at least one enemy"):
        call(server, "start_combat", enemies=[], flee_allowed=True)


def test_start_combat_rejects_all_dead_enemies(server, storage):
    call(server, "create_character", name="Aldric")
    with pytest.raises(Exception, match="at least one enemy"):
        call(
            server,
            "start_combat",
            enemies=[{"name": "Husk", "skill": 5, "stamina": 0}],
            flee_allowed=True,
        )


def test_flee_combat_costs_two_stamina(server, storage):
    call(server, "create_character", name="Aldric")
    before = storage.load_character().stamina.current
    combat = call(
        server,
        "start_combat",
        enemies=[{"name": "Troll", "skill": 9, "stamina": 12}],
        flee_allowed=True,
    )
    flee = call(server, "flee_combat", combat_id=combat["combat_id"])
    assert flee["damage_taken"] == 2
    assert flee["ended"] is True
    assert flee["hero_alive"] is True  # safe escape: still standing
    assert storage.load_character().stamina.current == before - 2


def test_fatal_flee_reports_hero_not_alive_and_enemy_winner(server, storage):
    call(server, "create_character", name="Aldric")
    # Drop the hero to 1 stamina so the fixed 2 flee-damage is lethal.
    call(server, "update_character_sheet", changes={"stamina": {"current": 1}})
    combat = call(
        server,
        "start_combat",
        enemies=[{"name": "Wraith", "skill": 10, "stamina": 8}],
        flee_allowed=True,
    )
    flee = call(server, "flee_combat", combat_id=combat["combat_id"])
    assert flee["hero_alive"] is False
    assert flee["hero_stamina"] == 0
    assert storage.load_character().alive is False

    # A fatal flee resolves as a defeat, not a safe escape.
    final = call(server, "end_combat", combat_id=combat["combat_id"])
    assert final["winner"] == "enemy"


# --------------------------------------------------------------------------- end states / session
def test_archive_character_to_hall_of_fame(server, storage):
    call(server, "create_character", name="Hero")
    ack = call(server, "archive_character", destination="hall_of_fame")
    assert ack == {"ok": True}


def test_archive_invalid_destination_raises(server):
    call(server, "create_character", name="Hero")
    with pytest.raises(Exception, match="invalid destination"):
        call(server, "archive_character", destination="trash")


def test_save_and_load_progress_roundtrip(server, storage):
    call(server, "create_character", name="Aldric")
    saved = call(server, "save_progress", slot=None)
    assert saved == {"ok": True, "slot": "autosave"}

    # Mutate, then restore the snapshot.
    call(server, "update_character_sheet", changes={"gold": 999})
    assert storage.load_character().gold == 999

    loaded = call(server, "load_progress", slot=None)
    assert loaded == {"ok": True, "slot": "autosave"}
    assert storage.load_character().gold == 0  # restored pre-mutation state


def test_save_progress_named_slot(server):
    call(server, "create_character", name="Aldric")
    saved = call(server, "save_progress", slot="checkpoint1")
    assert saved == {"ok": True, "slot": "checkpoint1"}
