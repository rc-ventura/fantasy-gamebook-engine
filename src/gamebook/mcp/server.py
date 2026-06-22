"""MCP server — the façade that exposes the engine to a harness (swap point #3).

This module is the *only* place the AI narrator talks to the engine. It contains
**no game rules of its own**: every tool merely orchestrates the pure ``regras``
math, the ``combate`` lifecycle, and a ``StorageBackend``. This is what makes the
hard rule of the project enforceable — "the AI never rolls dice in prose", because
all randomness and state flow through these tools.

Layering / golden rule
----------------------
``build_server`` takes only *interfaces* (``StorageBackend``, ``CombatEngine``,
``RandomSource``) and never constructs a concrete implementation. The single
exception is :func:`main`, the **composition root**, which is the one place
allowed to build concretes (``JSONStorage``, ``CombatService``, ``random.Random``)
and inject them. Those concrete imports live *inside* ``main`` precisely so that
merely importing this module never drags a storage backend into ``sys.modules``.

At module scope we import only ``dominio`` (persistent entities), the stable pure
core ``regras`` (allowed cross-import — it is not a swap boundary), and the
``*.interfaces`` result types used as tool return annotations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from gamebook.combate.interfaces import FinalResult, FleeResult, RoundOutcome
from gamebook.dominio.models import (
    ArchiveRecord,
    CharacterSheet,
    Combat,
    Enemy,
    Event,
    World,
)
from gamebook.regras import implementation as rules
from gamebook.regras.interfaces import DiceResult, LuckTestResult

if TYPE_CHECKING:
    from gamebook.combate.interfaces import CombatEngine
    from gamebook.regras.interfaces import RandomSource
    from gamebook.storage.interfaces import StorageBackend

SERVER_NAME = "gamebook"
_DEFAULT_SLOT = "autosave"

# Patch surface for ``update_character_sheet`` (kept in sync with CharacterSheet).
_ATTRIBUTE_FIELDS = frozenset({"skill", "stamina", "luck"})
_SCALAR_FIELDS = frozenset(
    {"name", "inventory", "gold", "provisions", "conditions", "alive"}
)
_UPDATABLE_FIELDS = _ATTRIBUTE_FIELDS | _SCALAR_FIELDS

# Patch surface for ``update_world`` (kept in sync with World). ``flags`` is merged
# key-wise; the rest are shallow-replaced.
_UPDATABLE_WORLD_FIELDS = frozenset(
    {"current_location", "visited_locations", "known_npcs", "flags", "turn"}
)

# Which archive a final state belongs to, and the outcome it records.
_ARCHIVE_OUTCOME = {"hall_of_fame": "victory", "graveyard": "death"}

_INSTRUCTIONS = (
    "Engine tools for a solo-play gamebook. The narrator must route every dice "
    "roll, luck test, and state change through these tools and never invent "
    "numbers in prose. Read state (character sheet, world, events, summary) "
    "before narrating a session."
)


def build_server(
    storage: StorageBackend,
    combat: CombatEngine,
    rng: RandomSource,
) -> FastMCP:
    """Build the MCP server, wiring all 18 tools onto injected collaborators.

    Takes interfaces only; constructs no concretes. Returns a ready-to-run
    :class:`FastMCP` instance (call ``.run()`` for stdio transport).
    """

    server: FastMCP = FastMCP(name=SERVER_NAME, instructions=_INSTRUCTIONS)

    def _require_character() -> CharacterSheet:
        sheet = storage.load_character()
        if sheet is None:
            raise ValueError("no character sheet exists yet; create one first")
        return sheet

    # --- Dice / luck ------------------------------------------------------
    @server.tool(name="roll_dice", description="Roll a dice expression like '2d6' or '1d6+6'.")
    def roll_dice(notation: str) -> DiceResult:
        return rules.roll_dice(notation, rng)

    @server.tool(
        name="test_luck",
        description="Test the hero's luck (2d6 <= current luck); always spends one luck.",
    )
    def test_luck() -> LuckTestResult:
        sheet = _require_character()
        result = rules.test_luck(sheet.luck.current, rng)
        # Testing luck always spends one point; floor at 0 to honour the
        # Attribute invariant (0 <= current <= initial).
        sheet.luck = sheet.luck.model_copy(
            update={"current": max(0, result.luck_after)}
        )
        storage.save_character(sheet)
        return result

    # --- Character sheet --------------------------------------------------
    @server.tool(
        name="create_character",
        description="Roll a new hero's attributes and persist a living character sheet.",
    )
    def create_character(name: str) -> CharacterSheet:
        existing = storage.load_character()
        if existing is not None and existing.alive:
            raise ValueError(
                "a living character already exists; archive or kill it before creating a new one"
            )
        attributes = rules.generate_attributes(rng)
        sheet = CharacterSheet(
            name=name,
            skill=attributes.skill,
            stamina=attributes.stamina,
            luck=attributes.luck,
            alive=True,
        )
        storage.save_character(sheet)
        return sheet

    @server.tool(name="read_character_sheet", description="Return the hero's full character sheet.")
    def read_character_sheet() -> CharacterSheet:
        return _require_character()

    @server.tool(
        name="update_character_sheet",
        description=(
            "Patch the character sheet. Scalars/lists are replaced; attribute "
            "sub-dicts (skill/stamina/luck) are merged. Invariants are validated; "
            "on error the state is left unchanged."
        ),
    )
    def update_character_sheet(changes: dict[str, Any]) -> CharacterSheet:
        sheet = _require_character()

        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise ValueError(
                f"unknown character field(s): {sorted(unknown)}; "
                f"allowed: {sorted(_UPDATABLE_FIELDS)}"
            )

        data = sheet.model_dump()
        for field, value in changes.items():
            if field in _ATTRIBUTE_FIELDS:
                if not isinstance(value, dict):
                    raise ValueError(
                        f"attribute field {field!r} expects a partial object "
                        f"(e.g. {{'current': 18}}), got {type(value).__name__}"
                    )
                data[field] = {**data[field], **value}
            else:
                data[field] = value

        # ``model_validate`` runs the dominio invariants. If it raises (e.g.
        # healing past ``initial``), nothing was persisted, so state is unchanged.
        updated = CharacterSheet.model_validate(data)
        storage.save_character(updated)
        return updated

    # --- World / events / summary ----------------------------------------
    @server.tool(name="read_world", description="Return the current world state.")
    def read_world() -> World:
        return storage.load_world()

    @server.tool(
        name="update_world",
        description=(
            "Patch the world. Scalars/lists (current_location, visited_locations, "
            "known_npcs, turn) are replaced; 'flags' is merged key-wise so one flag "
            "can be set without dropping others. Invariants are validated; on error "
            "the state is left unchanged. Sole legal path to set the victory flag "
            "and advance the turn counter."
        ),
    )
    def update_world(changes: dict[str, Any]) -> World:
        world = storage.load_world()

        unknown = set(changes) - _UPDATABLE_WORLD_FIELDS
        if unknown:
            raise ValueError(
                f"unknown world field(s): {sorted(unknown)}; "
                f"allowed: {sorted(_UPDATABLE_WORLD_FIELDS)}"
            )

        data = world.model_dump()
        for field, value in changes.items():
            if field == "flags":
                if not isinstance(value, dict):
                    raise ValueError(
                        "world field 'flags' expects an object of boolean flags, "
                        f"got {type(value).__name__}"
                    )
                data["flags"] = {**data["flags"], **value}
            else:
                data[field] = value

        # ``model_validate`` runs the dominio invariants (e.g. turn >= 0). If it
        # raises, nothing was persisted, so the world is left unchanged.
        updated = World.model_validate(data)
        storage.save_world(updated)
        return updated

    @server.tool(
        name="register_event",
        description="Append a hard fact to the chronicle, stamped with the current turn.",
    )
    def register_event(type: str, data: dict[str, Any]) -> Event:
        world = storage.load_world()
        event = Event(
            turn=world.turn,
            type=type,
            data=data,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        storage.append_event(event)
        return event

    @server.tool(name="read_events", description="Return the full chronicle of events, in order.")
    def read_events() -> list[Event]:
        return storage.load_events()

    @server.tool(name="read_summary", description="Return the running narrative summary.")
    def read_summary() -> str:
        return storage.load_summary()

    @server.tool(name="update_summary", description="Replace the running narrative summary.")
    def update_summary(text: str) -> dict[str, Any]:
        storage.save_summary(text)
        return {"ok": True}

    # --- Combat (delegated to the combat engine) -------------------------
    @server.tool(name="start_combat", description="Start a fight against one or more living enemies.")
    def start_combat(enemies: list[dict[str, Any]], flee_allowed: bool) -> Combat:
        # Parse the enemy dicts; the empty / all-defeated invariant is enforced
        # by CombatService.start_combat. We surface that ValueError cleanly
        # (never swallow it) so an unfightable encounter can't silently soft-lock.
        parsed = [Enemy.model_validate(enemy) for enemy in enemies]
        return combat.start_combat(parsed, flee_allowed)

    @server.tool(
        name="resolve_combat_round",
        description="Resolve one combat round, optionally testing luck on the hit.",
    )
    def resolve_combat_round(combat_id: str, use_luck: bool) -> RoundOutcome:
        return combat.resolve_round(combat_id, use_luck)

    @server.tool(name="flee_combat", description="Flee the combat (if allowed); costs 2 stamina.")
    def flee_combat(combat_id: str) -> FleeResult:
        return combat.flee(combat_id)

    @server.tool(name="end_combat", description="Conclude a combat and return its final result.")
    def end_combat(combat_id: str) -> FinalResult:
        return combat.end_combat(combat_id)

    # --- End states / session --------------------------------------------
    @server.tool(
        name="archive_character",
        description="Archive the hero to the graveyard (death) or hall_of_fame (victory).",
    )
    def archive_character(destination: str) -> dict[str, Any]:
        outcome = _ARCHIVE_OUTCOME.get(destination)
        if outcome is None:
            raise ValueError(
                f"invalid destination {destination!r}; "
                "expected 'graveyard' or 'hall_of_fame'"
            )
        sheet = _require_character()
        world = storage.load_world()
        record = ArchiveRecord(
            name=sheet.name,
            turns=world.turn,
            outcome=outcome,  # type: ignore[arg-type]
            location=world.current_location,
            cause=None,
            final_inventory=list(sheet.inventory),
        )
        storage.archive(record, destination)  # type: ignore[arg-type]
        return {"ok": True}

    @server.tool(name="save_progress", description="Snapshot all state to a named slot (default 'autosave').")
    def save_progress(slot: str | None = None) -> dict[str, Any]:
        name = slot or _DEFAULT_SLOT
        storage.save_slot(name)
        return {"ok": True, "slot": name}

    @server.tool(name="load_progress", description="Restore all state from a named slot (default 'autosave').")
    def load_progress(slot: str | None = None) -> dict[str, Any]:
        name = slot or _DEFAULT_SLOT
        storage.load_slot(name)
        return {"ok": True, "slot": name}

    return server


def main() -> None:
    """Composition root: build concretes, inject them, and serve over stdio.

    This is the ONLY place allowed to import/construct concrete implementations.
    The imports are local so that importing this module never pulls a storage
    backend into ``sys.modules`` (keeps the façade import-isolated).
    """
    import random

    from gamebook.combate.implementation import CombatService
    from gamebook.storage.json_storage import JSONStorage

    storage = JSONStorage("estado")
    rng = random.Random()
    combat = CombatService(storage, rng)
    build_server(storage, combat, rng).run(transport="stdio")


if __name__ == "__main__":
    main()
