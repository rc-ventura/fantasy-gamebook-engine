from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from mcp.server.fastmcp import FastMCP

from gamebook.combat.interfaces import FinalResult, FleeResult, RoundOutcome
from gamebook.domain.models import (
    ArchiveRecord,
    Attribute,
    CharacterSheet,
    Combat,
    Enemy,
    Event,
    World,
)
from gamebook.rules import implementation as rules
from gamebook.rules.interfaces import DiceResult, LuckTestResult

if TYPE_CHECKING:
    from gamebook.rules.interfaces import RandomSource
    from gamebook.storage.interfaces import StorageBackend

SERVER_NAME = "gamebook"
_DEFAULT_SLOT = "autosave"

# Patch surface for ``update_character_sheet`` — derived from CharacterSheet.model_fields
_ATTRIBUTE_FIELDS = frozenset(
    name for name, field in CharacterSheet.model_fields.items()
    if field.annotation is Attribute
)
_UPDATABLE_FIELDS = frozenset(CharacterSheet.model_fields.keys())

# Patch surface for ``update_world`` — derived from World.model_fields. ``flags`` is
_UPDATABLE_WORLD_FIELDS = frozenset(World.model_fields.keys())

# Which archive a final state belongs to, and the outcome it records.
_ARCHIVE_OUTCOME = {"hall_of_fame": "victory", "graveyard": "death"}

_INSTRUCTIONS = (
    "Engine tools for a solo-play gamebook. The narrator must route every dice "
    "roll, luck test, and state change through these tools and never invent "
    "numbers in prose. Read state (character sheet, world, events, summary) "
    "before narrating a session."
)


def build_server(
    storage_factory: Callable[[str], StorageBackend],
    rng: RandomSource,
) -> FastMCP:
    """Build the MCP server, wiring all 18 tools onto injected collaborators.

    Takes a ``storage_factory`` callable (returns a ``StorageBackend`` scoped to
    the given ``campaign_id``) and a ``RandomSource``. Returns a ready-to-run
    :class:`FastMCP` instance (call ``.run()`` for stdio transport).

    Every tool takes ``campaign_id: str`` as its first parameter and resolves its
    storage backend on each call via ``storage_factory(campaign_id)``. This makes
    a single server process serve all campaigns with full isolation (ADR-018).
    """
    from gamebook.combat.implementation import CombatService

    server: FastMCP = FastMCP(name=SERVER_NAME, instructions=_INSTRUCTIONS)

    def _require_character(campaign_id: str) -> CharacterSheet:
        sheet = storage_factory(campaign_id).load_character()
        if sheet is None:
            raise ValueError("no character sheet exists yet; create one first")
        return sheet

    def _get_combat(campaign_id: str) -> CombatService:
        """Per-campaign CombatService wrapping the campaign's StorageBackend."""
        return CombatService(storage_factory(campaign_id), rng)

    # --- Dice / luck ------------------------------------------------------
    @server.tool(name="roll_dice", description="Roll a dice expression like '2d6' or '1d6+6'.")
    def roll_dice(campaign_id: str, notation: str) -> DiceResult:
        return rules.roll_dice(notation, rng)

    @server.tool(
        name="test_luck",
        description="Test the hero's luck (2d6 <= current luck); always spends one luck.",
    )
    def test_luck(campaign_id: str) -> LuckTestResult:
        storage = storage_factory(campaign_id)
        sheet = _require_character(campaign_id)
        result = rules.test_luck(sheet.luck.current, rng)
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
    def create_character(campaign_id: str, name: str) -> CharacterSheet:
        storage = storage_factory(campaign_id)
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
    def read_character_sheet(campaign_id: str) -> CharacterSheet:
        return _require_character(campaign_id)

    @server.tool(
        name="update_character_sheet",
        description=(
            "Patch the character sheet. Scalars/lists are replaced; attribute "
            "sub-dicts (skill/stamina/luck) are merged. Invariants are validated; "
            "on error the state is left unchanged."
        ),
    )
    def update_character_sheet(campaign_id: str, changes: dict[str, Any]) -> CharacterSheet:
        storage = storage_factory(campaign_id)
        sheet = _require_character(campaign_id)

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

        updated = CharacterSheet.model_validate(data)
        storage.save_character(updated)
        return updated

    @server.tool(
        name="apply_healing",
        description=(
            "Heal the hero by a relative amount (not an absolute value). Clamped "
            "to stamina.initial — cannot over-heal. Used by the deterministic "
            "dispatcher (spec 009, ADR-033), not narrator-reachable."
        ),
    )
    def apply_healing(campaign_id: str, amount: int, source: str) -> CharacterSheet:
        if amount <= 0:
            raise ValueError(f"amount must be a positive int, got {amount}")
        storage = storage_factory(campaign_id)
        sheet = _require_character(campaign_id)
        new_current = min(sheet.stamina.initial, sheet.stamina.current + amount)
        sheet.stamina = sheet.stamina.model_copy(update={"current": new_current})
        storage.save_character(sheet)
        return sheet

    @server.tool(
        name="apply_damage",
        description=(
            "Damage the hero by a relative amount (not an absolute value). "
            "Clamped to 0 — sets alive=False if stamina reaches 0. Used by the "
            "deterministic dispatcher (spec 009, ADR-033), not narrator-reachable."
        ),
    )
    def apply_damage(campaign_id: str, amount: int, source: str) -> CharacterSheet:
        if amount <= 0:
            raise ValueError(f"amount must be a positive int, got {amount}")
        storage = storage_factory(campaign_id)
        sheet = _require_character(campaign_id)
        new_current = max(0, sheet.stamina.current - amount)
        sheet.stamina = sheet.stamina.model_copy(update={"current": new_current})
        if new_current == 0:
            sheet.alive = False
        storage.save_character(sheet)
        return sheet

    # --- World / events / summary ----------------------------------------
    @server.tool(name="read_world", description="Return the current world state.")
    def read_world(campaign_id: str) -> World:
        return storage_factory(campaign_id).load_world()

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
    def update_world(campaign_id: str, changes: dict[str, Any]) -> World:
        storage = storage_factory(campaign_id)
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

        updated = World.model_validate(data)
        storage.save_world(updated)
        return updated

    @server.tool(
        name="register_event",
        description="Append a hard fact to the chronicle, stamped with the current turn.",
    )
    def register_event(campaign_id: str, type: str, data: dict[str, Any]) -> Event:
        storage = storage_factory(campaign_id)
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
    def read_events(campaign_id: str) -> list[Event]:
        return storage_factory(campaign_id).load_events()

    @server.tool(name="read_summary", description="Return the running narrative summary.")
    def read_summary(campaign_id: str) -> str:
        return storage_factory(campaign_id).load_summary()

    @server.tool(name="update_summary", description="Replace the running narrative summary.")
    def update_summary(campaign_id: str, text: str) -> dict[str, Any]:
        storage_factory(campaign_id).save_summary(text)
        return {"ok": True}

    # --- Combat (delegated to the combat engine) -------------------------
    @server.tool(name="start_combat", description="Start a fight against one or more living enemies.")
    def start_combat(campaign_id: str, enemies: list[dict[str, Any]], flee_allowed: bool) -> Combat:
        parsed = [Enemy.model_validate(enemy) for enemy in enemies]
        return _get_combat(campaign_id).start_combat(parsed, flee_allowed)

    @server.tool(
        name="resolve_combat_round",
        description="Resolve one combat round, optionally testing luck on the hit.",
    )
    def resolve_combat_round(campaign_id: str, combat_id: str, use_luck: bool) -> RoundOutcome:
        return _get_combat(campaign_id).resolve_round(combat_id, use_luck)

    @server.tool(name="flee_combat", description="Flee the combat (if allowed); costs 2 stamina.")
    def flee_combat(campaign_id: str, combat_id: str) -> FleeResult:
        return _get_combat(campaign_id).flee(combat_id)

    @server.tool(name="end_combat", description="Conclude a combat and return its final result.")
    def end_combat(campaign_id: str, combat_id: str) -> FinalResult:
        return _get_combat(campaign_id).end_combat(combat_id)

    # --- End states / session --------------------------------------------
    @server.tool(
        name="archive_character",
        description="Archive the hero to the graveyard (death) or hall_of_fame (victory).",
    )
    def archive_character(campaign_id: str, destination: str) -> dict[str, Any]:
        outcome = _ARCHIVE_OUTCOME.get(destination)
        if outcome is None:
            raise ValueError(
                f"invalid destination {destination!r}; "
                "expected 'graveyard' or 'hall_of_fame'"
            )
        storage = storage_factory(campaign_id)
        sheet = _require_character(campaign_id)
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
    def save_progress(campaign_id: str, slot: str | None = None) -> dict[str, Any]:
        name = slot or _DEFAULT_SLOT
        storage_factory(campaign_id).save_slot(name)
        return {"ok": True, "slot": name}

    @server.tool(name="load_progress", description="Restore all state from a named slot (default 'autosave').")
    def load_progress(campaign_id: str, slot: str | None = None) -> dict[str, Any]:
        name = slot or _DEFAULT_SLOT
        storage_factory(campaign_id).load_slot(name)
        return {"ok": True, "slot": name}

    return server


def main() -> None:
    """Composition root: build concretes, inject them as a factory, and serve over stdio.

    This is the ONLY place allowed to import/construct concrete implementations.
    The imports are local so that importing this module never pulls a storage
    backend into ``sys.modules`` (keeps the façade import-isolated).

    Phase-1 path (default):
        ``DATABASE_URL`` or ``GAMEBOOK_CAMPAIGN_ID`` absent → ``JSONStorage``
        scoped to ``estado/{campaign_id}``.

    Phase-2 path:
        ``DATABASE_URL`` set → ``PostgresStorage(url, campaign_id)`` per campaign.
        The campaign row is upserted automatically; no prior database setup beyond
        ``alembic upgrade head`` is needed.

    The factory caches backends in a dict keyed by ``campaign_id`` so repeated
    calls for the same campaign reuse the same instance.
    # TODO(LRU): replace the dict cache with an LRU(max_size=500) before
    # production at scale — an unbounded dict is a memory leak when many campaigns
    # are created across accounts.
    """
    import os
    import random

    database_url = os.environ.get("DATABASE_URL", "")

    # Per-campaign backend cache (dict MVP; see LRU TODO above).
    _cache: dict[str, Any] = {}

    if database_url:
        from gamebook.storage.postgres import PostgresStorage

        # GAMEBOOK_ACCOUNT_ID: optional owner for campaigns created by this
        # process. Only meaningful when the MCP server is run standalone for a
        # single account — the multi-account web path persists ownership at its
        # own composition root (create_game) since the tool contract carries
        # only campaign_id (ADR-018).
        account_id = os.environ.get("GAMEBOOK_ACCOUNT_ID") or None

        def factory(campaign_id: str) -> PostgresStorage:
            if campaign_id not in _cache:
                _cache[campaign_id] = PostgresStorage(
                    database_url, campaign_id, account_id=account_id
                )
            return _cache[campaign_id]

    else:
        from gamebook.storage.json_storage import JSONStorage

        def factory(campaign_id: str) -> JSONStorage:  # type: ignore[misc]
            if campaign_id not in _cache:
                _cache[campaign_id] = JSONStorage(f"estado/{campaign_id}")
            return _cache[campaign_id]

    rng = random.Random()
    # GAMEBOOK_CAMPAIGN_ID is only used by the Phase-1 terminal harness main()
    # to pre-warm the default campaign on startup; it is NOT read by the web path.
    default_id = os.environ.get("GAMEBOOK_CAMPAIGN_ID", "default")
    _ = factory(default_id)  # pre-warm default campaign backend

    build_server(factory, rng).run(transport="stdio")


if __name__ == "__main__":
    main()
