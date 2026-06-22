"""Cycle-1 HIGH regression — World writes persist end-to-end via MCP (victory reachable).

The cycle-1 gap: the harness could *read* the world but had no tool to *write* it,
so the turn counter stayed 0, archived runs recorded `turns=0`/no location, and the
victory flag (`malachar_defeated`) was **unreachable** — the adventure could never
be won through the engine. Wave A added the 18th tool `update_world(changes)->World`
(CONTRACTS §6, amended).

This is the QA *guardian / end-to-end* evidence the HIGH is closed: it drives a
full mini-arc through the real MCP server and proves world writes survive,
re-read, stamp events, feed the archive, and make the victory flag reachable. It
complements (does not duplicate) the infra server-level unit tests by asserting
the whole chain holds together after real progress.
"""

from __future__ import annotations

import pytest

# --- Blocked-on-server guard (same pattern as test_mcp_integration) ----------
pytest.importorskip(
    "gamebook.mcp.server",
    reason="MCP server not built yet — world-persistence e2e blocked on server.py",
)
import _mcp  # noqa: E402  (shared in-process MCP plumbing)

SEED = 70707


# ---------------------------------------------------------------- the headline regression
def test_victory_path_world_writes_persist_end_to_end() -> None:
    """Full arc: create -> explore (world writes) -> win a fight -> set victory flag -> archive.

    Every world mutation must persist and be observable, the victory flag must be
    *reachable*, and the archived record must carry the real turn/location.
    """
    server, storage = _mcp.build_test_server(SEED)

    # 1. A living hero exists.
    hero = _mcp.call(server, "create_character", name="Aldric")
    assert hero["alive"] is True

    # 2. Explore: write location, visited list, flags, and advance the turn — the
    #    cycle-1 gap was that NONE of this was writable through the engine.
    updated = _mcp.call(
        server,
        "update_world",
        changes={
            "current_location": "grey_gate",
            "visited_locations": ["foothills", "grey_gate"],
            "flags": {"gate_unlocked": True},
            "turn": 4,
        },
    )
    assert updated["current_location"] == "grey_gate"
    assert updated["turn"] == 4

    # 3. read_world reflects every written field (it persisted, not just echoed).
    world = _mcp.call(server, "read_world")
    assert world["current_location"] == "grey_gate"
    assert world["visited_locations"] == ["foothills", "grey_gate"]
    assert world["flags"]["gate_unlocked"] is True
    assert world["turn"] == 4

    # 4. register_event now stamps the REAL turn (4), not 0 — the visible symptom
    #    of the cycle-1 bug is gone.
    event = _mcp.call(server, "register_event", type="enter_zone", data={"zone": "grey_gate"})
    assert event["turn"] == 4

    # 5. Win a fight against a weak foe (engine math, never narrated).
    combat = _mcp.call(
        server,
        "start_combat",
        enemies=[{"name": "Gate Sentry", "skill": 1, "stamina": 2}],
        flee_allowed=False,
    )
    final = None
    for _ in range(80):
        outcome = _mcp.call(server, "resolve_combat_round", combat_id=combat["combat_id"], use_luck=False)
        if outcome["ended"]:
            final = _mcp.call(server, "end_combat", combat_id=combat["combat_id"])
            break
    assert final is not None and final["winner"] == "hero"

    # 6. THE victory flag is reachable: set it, and it is visible via read_world.
    after_victory = _mcp.call(server, "update_world", changes={"flags": {"malachar_defeated": True}})
    assert after_victory["flags"]["malachar_defeated"] is True
    # Flags merge key-wise: the earlier flag survives alongside the victory flag.
    assert after_victory["flags"]["gate_unlocked"] is True
    assert _mcp.call(server, "read_world")["flags"]["malachar_defeated"] is True

    # 7. Archive the win: the record carries the REAL turn and location (not 0/"").
    assert _mcp.call(server, "archive_character", destination="hall_of_fame") == {"ok": True}
    record = storage._archives["hall_of_fame"][-1]
    assert record.outcome == "victory"
    assert record.turns == 4
    assert record.location == "grey_gate"
    assert record.name == "Aldric"


# ---------------------------------------------------------------- guardian: writes can't corrupt
def test_bad_world_write_after_real_progress_leaves_state_intact() -> None:
    """An invalid `update_world` must not clobber already-accumulated world state.

    End-to-end angle: build up real progress first, then prove an unknown field
    and an invariant violation each raise *and* leave the full world untouched —
    no partial write, no soft-corruption mid-adventure.
    """
    server, _storage = _mcp.build_test_server(SEED)
    _mcp.call(server, "create_character", name="Aldric")
    _mcp.call(
        server,
        "update_world",
        changes={"current_location": "grey_summit", "turn": 9, "flags": {"door_open": True}},
    )
    before = _mcp.call(server, "read_world")

    with pytest.raises(Exception, match="unknown world field"):
        _mcp.call(server, "update_world", changes={"weather": "stormy"})
    assert _mcp.call(server, "read_world") == before  # nothing changed

    with pytest.raises(Exception):  # dominio invariant: turn >= 0
        _mcp.call(server, "update_world", changes={"turn": -1})
    assert _mcp.call(server, "read_world") == before  # still nothing changed


# ---------------------------------------------------------------- guardian: no combat soft-lock
def test_rejected_start_combat_does_not_soft_lock_the_session() -> None:
    """An unfightable encounter is refused cleanly and the session can continue.

    Proves the rejected `start_combat` neither corrupts state nor blocks a
    subsequent *valid* fight — the anti-soft-lock guarantee end to end.
    """
    server, _storage = _mcp.build_test_server(SEED)
    _mcp.call(server, "create_character", name="Aldric")
    _mcp.call(server, "update_world", changes={"turn": 2})

    with pytest.raises(Exception, match="at least one enemy"):
        _mcp.call(server, "start_combat", enemies=[], flee_allowed=True)
    with pytest.raises(Exception, match="at least one enemy"):
        _mcp.call(
            server,
            "start_combat",
            enemies=[{"name": "Husk", "skill": 5, "stamina": 0}],
            flee_allowed=True,
        )

    # World untouched by the rejected calls, and a valid fight still starts.
    assert _mcp.call(server, "read_world")["turn"] == 2
    combat = _mcp.call(
        server,
        "start_combat",
        enemies=[{"name": "Goblin", "skill": 4, "stamina": 5}],
        flee_allowed=True,
    )
    assert combat["combat_id"]
    assert combat["ended"] is False
