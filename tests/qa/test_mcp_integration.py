"""End-to-end MCP server test (the full Phase-1 flow through the tool façade).

Builds the real MCP server via ``build_server(storage, combat, rng)`` with an
``InMemoryStorage`` + ``CombatService`` + seeded RNG, then drives a complete play
session purely through the MCP tools (``docs/CONTRACTS.md`` Section 6):

    create_character -> read_character_sheet -> roll_dice -> start_combat
    -> resolve_combat_round (with and without luck) -> end_combat
    -> archive_character

It also asserts that an **invalid tool input** raises a clear error *without
corrupting* persisted state -- the engine's robustness guarantee.

This test depends on ``gamebook.mcp.server`` (owned by backend-infra). Until that
module exposes ``build_server``, the whole module is **skipped** (reported as
"blocked on server"); it will start running automatically the moment the server
lands, with no edits needed here.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import pytest

# --- Blocked-on-server guard -------------------------------------------------
_server_mod = pytest.importorskip(
    "gamebook.mcp.server",
    reason="MCP server not built yet (backend-infra) — e2e blocked on server.py",
)
build_server = getattr(_server_mod, "build_server", None)
if build_server is None:  # module exists but the composition root isn't wired yet
    pytest.skip(
        "gamebook.mcp.server has no build_server() yet — e2e blocked on server",
        allow_module_level=True,
    )

from gamebook.combat.implementation import CombatService  # noqa: E402
from gamebook.storage.in_memory import InMemoryStorage  # noqa: E402

SEED = 20260621


# --- Tool-call plumbing ------------------------------------------------------
def _normalize(raw: Any) -> Any:
    """Normalize a FastMCP ``call_tool`` return into a plain Python value.

    FastMCP returns either ``(unstructured_content, structured_dict)`` for a
    typed tool, a bare ``dict``, or a sequence of content blocks. Reduce all of
    them to the underlying JSON value.
    """
    if isinstance(raw, tuple) and len(raw) == 2:
        return _unwrap(raw[1])
    if isinstance(raw, dict):
        return _unwrap(raw)
    # Sequence of content blocks — pull the first text payload and parse it.
    for block in list(raw):
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return _unwrap(json.loads(text))
            except (ValueError, TypeError):
                return text
    return raw


def _unwrap(value: Any) -> Any:
    """FastMCP wraps non-object return types as ``{"result": ...}`` — unwrap it."""
    if isinstance(value, dict) and set(value.keys()) == {"result"}:
        return value["result"]
    return value


def _call(server: Any, tool: str, **arguments: Any) -> Any:
    """Invoke an MCP tool by name and return its normalized result.

    The tool-name parameter is ``tool`` (not ``name``) so it can't collide with a
    tool argument literally called ``name`` (e.g. ``create_character(name=...)``).
    """
    return _normalize(asyncio.run(server.call_tool(tool, arguments)))


def _build() -> Any:
    storage = InMemoryStorage()
    rng = random.Random(SEED)
    combat = CombatService(storage, rng)
    return build_server(storage=storage, combat=combat, rng=rng)


# --- Tests -------------------------------------------------------------------
def test_full_session_flow_through_mcp_tools() -> None:
    server = _build()

    # 1. Create the hero. Attributes are rolled server-side and within range.
    sheet = _call(server, "create_character", name="Aldric")
    assert sheet["name"] == "Aldric"
    assert sheet["alive"] is True
    assert 7 <= sheet["skill"]["initial"] <= 12
    assert 14 <= sheet["stamina"]["initial"] <= 24
    assert 7 <= sheet["luck"]["initial"] <= 12
    for attr in ("skill", "stamina", "luck"):
        assert sheet[attr]["current"] == sheet[attr]["initial"]

    # 2. read_character_sheet reflects the same persisted hero.
    again = _call(server, "read_character_sheet")
    assert again == sheet

    # 3. roll_dice goes through the engine (never narrated).
    dice = _call(server, "roll_dice", notation="2d6")
    assert 2 <= dice["total"] <= 12
    assert len(dice["rolls"]) == 2

    # 4. World + events + summary round-trip through the tools.
    event = _call(server, "register_event", type="enter_zone", data={"zone": "foothills"})
    assert event["type"] == "enter_zone"
    events = _call(server, "read_events")
    assert any(e["type"] == "enter_zone" for e in events)

    _call(server, "update_summary", text="Aldric enters the foothills.")
    assert _call(server, "read_summary") == "Aldric enters the foothills."

    world = _call(server, "read_world")
    assert "current_location" in world

    # 5. A full fight against a weak foe so the hero is sure to win.
    combat = _call(
        server,
        "start_combat",
        enemies=[{"name": "Goblin", "skill": 1, "stamina": 3}],
        flee_allowed=True,
    )
    combat_id = combat["combat_id"]
    assert combat["enemies"][0]["name"] == "Goblin"

    final = None
    for i in range(80):
        use_luck = bool(i % 2)  # alternate luck/no-luck rounds
        outcome = _call(server, "resolve_combat_round", combat_id=combat_id, use_luck=use_luck)
        assert outcome["hitter"] in ("hero", "enemy", "tie")
        # When luck was requested and the round produced a hit, it must be recorded.
        if use_luck and outcome["hitter"] != "tie":
            assert outcome["luck_used"] is not None
        if outcome["ended"]:
            final = _call(server, "end_combat", combat_id=combat_id)
            break
    assert final is not None, "combat did not conclude through the MCP tools"
    assert final["winner"] in ("hero", "enemy")
    assert final["rounds"] >= 1

    # 6. End-state archival.
    archived = _call(server, "archive_character", destination="hall_of_fame")
    assert archived == {"ok": True} or archived.get("ok") is True


def test_invalid_input_errors_without_corrupting_state() -> None:
    server = _build()
    created = _call(server, "create_character", name="Borin")

    # Invalid dice notation must raise a clear error...
    with pytest.raises(Exception):
        _call(server, "roll_dice", notation="not-a-dice")

    # ...and an over-heal that violates the Attribute invariant must also raise...
    bad_current = created["stamina"]["initial"] + 5
    with pytest.raises(Exception):
        _call(server, "update_character_sheet", changes={"stamina": {"current": bad_current}})

    # ...with the persisted sheet left exactly as it was before either bad call.
    after = _call(server, "read_character_sheet")
    assert after == created


def test_create_character_rejects_overwriting_a_living_hero() -> None:
    server = _build()
    _call(server, "create_character", name="First")

    # A second create while a *living* hero exists must be refused (no clobber).
    with pytest.raises(Exception):
        _call(server, "create_character", name="Second")

    assert _call(server, "read_character_sheet")["name"] == "First"
