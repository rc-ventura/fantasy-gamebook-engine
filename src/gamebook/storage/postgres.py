"""PostgresStorage — ``StorageBackend`` backed by PostgreSQL (swap boundary #1).

This is the Phase-2 production backend.  It is injected into the engine at the
MCP composition root (``mcp.server.main``) when ``DATABASE_URL`` +
``GAMEBOOK_CAMPAIGN_ID`` are both set; **no other engine module imports this
file**.

Design principles honoured:
  Principle II  — depends only on ``domain`` models and the ``StorageBackend``
                  interface; the rest of the engine stays behaviour-unchanged.
  Principle V   — every state change commits in a single transaction (atomic,
                  all-or-nothing).  A crash mid-write leaves the previous state
                  intact; the next ``load_*`` sees the last fully-committed row.

Sync/async bridge
-----------------
The ``StorageBackend`` protocol is synchronous (the MCP server runs sync tool
functions inside FastMCP's async loop).  asyncpg/SQLAlchemy-asyncio is async.
To bridge these without touching the interface we run a private asyncio event
loop in a daemon thread and submit every async operation to it via
``asyncio.run_coroutine_threadsafe``, which blocks the caller until the
coroutine completes.  This is safe from any calling context — whether the
caller itself is sync or already inside an event loop.

See ADR-014 for the rationale.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from gamebook.domain.models import (
    ArchiveRecord,
    CharacterSheet,
    Combat,
    Event,
    World,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ARCHIVE_DESTINATIONS = frozenset({"graveyard", "hall_of_fame"})

# Identifiers that would allow path traversal or cause storage confusion if
# used as slot names, combat IDs, etc.
_INVALID_IDENTIFIERS = frozenset({"", ".", ".."})


def _validate_identifier(value: str | None, label: str = "identifier") -> None:
    """Raise ValueError for empty, None, or path-traversal identifiers (T076)."""
    if value is None or value in _INVALID_IDENTIFIERS or "/" in value or "\\" in value:
        raise ValueError(f"invalid {label}: {value!r}")


def _new_id() -> str:
    return str(uuid.uuid4())


class PostgresStorage:
    """A ``StorageBackend`` that persists all state in PostgreSQL.

    Parameters
    ----------
    url:
        A SQLAlchemy-compatible async connection URL, e.g.
        ``postgresql+asyncpg://user:pass@host/db``.
    campaign_id:
        The UUID string that scopes every read/write to a single campaign.
        The campaign row is upserted on construction so FK constraints are
        satisfied before any other method is called.
    """

    def __init__(self, url: str, campaign_id: str, account_id: str | None = None) -> None:
        self._campaign_id = campaign_id
        # Owning account for this campaign (FR-024).  When provided, the campaign
        # row is created/healed with this account_id so the storage never leaves
        # an orphan (NULL-owner) campaign that ownership checks would reject.
        # Optional for pure-storage tests that don't exercise ownership.
        self._account_id = account_id

        # TLS enforcement (ADR-026, T072): require SSL by default.
        # Set POSTGRES_SSL_MODE=disable for local dev/test without TLS.
        ssl_mode = os.getenv("POSTGRES_SSL_MODE", "require")
        connect_args: dict[str, Any] = {
            # asyncpg default connect_timeout is None (blocks forever). Set a
            # reasonable bound so __init__ fails fast on an unresponsive DB
            # rather than hanging the MCP server process at startup (finding #3).
            "timeout": float(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
        }
        if ssl_mode != "disable":
            connect_args["ssl"] = ssl_mode  # asyncpg accepts "require" / True
        self._engine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

        # Private event loop in a daemon thread so we can safely submit async
        # work from any calling context (including an already-running loop).
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="postgres-storage-loop",
        )
        self._thread.start()

        # Guarantee the campaign row exists before any FK-dependent insert.
        self._run(self._ensure_campaign())

    # ------------------------------------------------------------------
    # Sync bridge
    # ------------------------------------------------------------------

    _RUN_TIMEOUT = float(os.getenv("POSTGRES_OP_TIMEOUT", "30"))

    def _run(self, coro) -> Any:
        """Submit *coro* to the background loop and block until it finishes.

        Raises ``TimeoutError`` after ``POSTGRES_OP_TIMEOUT`` seconds (default 30)
        so a hung DB operation never permanently stalls the calling thread.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self._RUN_TIMEOUT)

    def _session(self) -> AsyncSession:  # pragma: no cover — thin factory
        return AsyncSession(self._engine, expire_on_commit=False)

    def close(self) -> None:
        """Dispose the async engine and stop the daemon event loop (T074 / ADR-027).

        Must be called on MCP server graceful shutdown and in live-Postgres test
        teardown to prevent resource leaks.  Safe to call more than once.
        """
        async def _dispose() -> None:
            await self._engine.dispose()

        try:
            if self._loop.is_running():
                self._run(_dispose())
        finally:
            # Stop the loop even if dispose raised (finding #5 — try/finally).
            self._loop.call_soon_threadsafe(self._loop.stop)
            # Wait for the thread to finish so teardown doesn't race the next
            # PostgresStorage construction in the same test session (finding #9).
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Campaign bootstrap
    # ------------------------------------------------------------------

    async def _ensure_campaign(self) -> None:
        """Upsert the campaign row so all FK references succeed.

        When an owning ``account_id`` is known (FR-024), the row is created with
        it and — on an existing row — its owner is healed only if currently NULL
        (``COALESCE`` never overwrites an established owner, so a mis-scoped
        storage instance can't reassign someone else's campaign).
        """
        async with self._session() as session:
            async with session.begin():
                if self._account_id:
                    await session.execute(
                        text(
                            """
                            INSERT INTO campaign (id, account_id, status, created_at, updated_at, summary_text)
                            VALUES (:id, :account_id, 'active', NOW(), NOW(), '')
                            ON CONFLICT (id) DO UPDATE
                              SET account_id = COALESCE(campaign.account_id, EXCLUDED.account_id)
                            """
                        ),
                        {"id": self._campaign_id, "account_id": self._account_id},
                    )
                else:
                    await session.execute(
                        text(
                            """
                            INSERT INTO campaign (id, status, created_at, updated_at, summary_text)
                            VALUES (:id, 'active', NOW(), NOW(), '')
                            ON CONFLICT (id) DO NOTHING
                            """
                        ),
                        {"id": self._campaign_id},
                    )

    # ------------------------------------------------------------------
    # Character
    # ------------------------------------------------------------------

    def load_character(self) -> CharacterSheet | None:
        return self._run(self._load_character())

    async def _load_character(self) -> CharacterSheet | None:
        async with self._session() as session:
            row = await session.execute(
                text("SELECT data FROM character_sheet WHERE campaign_id = :cid"),
                {"cid": self._campaign_id},
            )
            result = row.fetchone()
            if result is None:
                return None
            data = result[0]
            if isinstance(data, str):
                data = json.loads(data)
            return CharacterSheet.model_validate(data)

    def save_character(self, character: CharacterSheet) -> None:
        self._run(self._save_character(character))

    async def _save_character(self, character: CharacterSheet) -> None:
        payload = json.dumps(character.model_dump(mode="json"))
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO character_sheet (campaign_id, data, alive)
                        VALUES (:cid, CAST(:data AS jsonb), :alive)
                        ON CONFLICT (campaign_id)
                        DO UPDATE SET data = CAST(EXCLUDED.data AS jsonb),
                                      alive = EXCLUDED.alive
                        """
                    ),
                    {
                        "cid": self._campaign_id,
                        "data": payload,
                        "alive": character.alive,
                    },
                )

    # ------------------------------------------------------------------
    # World
    # ------------------------------------------------------------------

    def load_world(self) -> World:
        return self._run(self._load_world())

    async def _load_world(self) -> World:
        async with self._session() as session:
            row = await session.execute(
                text("SELECT data FROM world WHERE campaign_id = :cid"),
                {"cid": self._campaign_id},
            )
            result = row.fetchone()
            if result is None:
                return World()
            data = result[0]
            if isinstance(data, str):
                data = json.loads(data)
            return World.model_validate(data)

    def save_world(self, world: World) -> None:
        self._run(self._save_world(world))

    async def _save_world(self, world: World) -> None:
        dump = world.model_dump(mode="json")
        payload = json.dumps(dump)
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO world (campaign_id, location, visited, flags, turn, data)
                        VALUES (:cid, :loc, CAST(:vis AS jsonb), CAST(:flags AS jsonb),
                                :turn, CAST(:data AS jsonb))
                        ON CONFLICT (campaign_id)
                        DO UPDATE SET location = EXCLUDED.location,
                                      visited   = CAST(EXCLUDED.visited AS jsonb),
                                      flags     = CAST(EXCLUDED.flags AS jsonb),
                                      turn      = EXCLUDED.turn,
                                      data      = CAST(EXCLUDED.data AS jsonb)
                        """
                    ),
                    {
                        "cid": self._campaign_id,
                        "loc": world.current_location,
                        "vis": json.dumps(dump.get("visited_locations", [])),
                        "flags": json.dumps(dump.get("flags", {})),
                        "turn": world.turn,
                        "data": payload,
                    },
                )

    # ------------------------------------------------------------------
    # Events (append-only)
    # ------------------------------------------------------------------

    def append_event(self, event: Event) -> None:
        self._run(self._append_event(event))

    async def _append_event(self, event: Event) -> None:
        payload = json.dumps(event.model_dump(mode="json"))
        event_id = _new_id()
        async with self._session() as session:
            async with session.begin():
                # Acquire a transaction-scoped advisory lock keyed by campaign_id
                # hash to serialize concurrent appends for the same campaign
                # (ADR-027, T073). The prior MAX(seq)+1 approach had a race:
                # two concurrent transactions could compute the same MAX before
                # either committed, producing duplicate seq values.
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:cid))"),
                    {"cid": self._campaign_id},
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO event (id, campaign_id, seq, payload, created_at)
                        VALUES (
                            :eid,
                            :cid,
                            COALESCE(
                                (SELECT MAX(seq) FROM event WHERE campaign_id = :cid),
                                -1
                            ) + 1,
                            CAST(:payload AS jsonb),
                            NOW()
                        )
                        """
                    ),
                    {"eid": event_id, "cid": self._campaign_id, "payload": payload},
                )

    def load_events(self) -> list[Event]:
        return self._run(self._load_events())

    async def _load_events(self) -> list[Event]:
        async with self._session() as session:
            rows = await session.execute(
                text(
                    "SELECT payload FROM event WHERE campaign_id = :cid ORDER BY seq ASC"
                ),
                {"cid": self._campaign_id},
            )
            result: list[Event] = []
            for (payload,) in rows:
                if isinstance(payload, str):
                    payload = json.loads(payload)
                result.append(Event.model_validate(payload))
            return result

    # ------------------------------------------------------------------
    # Narrative summary
    # ------------------------------------------------------------------

    def load_summary(self) -> str:
        return self._run(self._load_summary())

    async def _load_summary(self) -> str:
        async with self._session() as session:
            row = await session.execute(
                text("SELECT summary_text FROM campaign WHERE id = :cid"),
                {"cid": self._campaign_id},
            )
            result = row.fetchone()
            return "" if result is None else (result[0] or "")

    def save_summary(self, text_: str) -> None:
        self._run(self._save_summary(text_))

    async def _save_summary(self, text_: str) -> None:
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "UPDATE campaign SET summary_text = :txt, updated_at = NOW() "
                        "WHERE id = :cid"
                    ),
                    {"txt": text_, "cid": self._campaign_id},
                )

    # ------------------------------------------------------------------
    # In-progress combat
    # ------------------------------------------------------------------

    def load_combat(self, combat_id: str) -> Combat | None:
        _validate_identifier(combat_id, "combat_id")
        return self._run(self._load_combat(combat_id))

    async def _load_combat(self, combat_id: str) -> Combat | None:
        async with self._session() as session:
            row = await session.execute(
                text("SELECT state FROM combat WHERE campaign_id = :cid"),
                {"cid": self._campaign_id},
            )
            result = row.fetchone()
            if result is None or result[0] is None:
                return None
            state = result[0]
            if isinstance(state, str):
                state = json.loads(state)
            # state is a dict {combat_id: <Combat JSON>}
            combat_data = state.get(combat_id)
            if combat_data is None:
                return None
            return Combat.model_validate(combat_data)

    def save_combat(self, combat: Combat) -> None:
        self._run(self._save_combat(combat))

    async def _save_combat(self, combat: Combat) -> None:
        async with self._session() as session:
            async with session.begin():
                # Load existing state dict
                row = await session.execute(
                    text("SELECT state FROM combat WHERE campaign_id = :cid FOR UPDATE"),
                    {"cid": self._campaign_id},
                )
                result = row.fetchone()
                if result is None:
                    state: dict[str, Any] = {}
                else:
                    state = result[0] or {}
                    if isinstance(state, str):
                        state = json.loads(state)

                state[combat.combat_id] = combat.model_dump(mode="json")
                new_state = json.dumps(state)

                if result is None:
                    await session.execute(
                        text(
                            "INSERT INTO combat (campaign_id, state) "
                            "VALUES (:cid, CAST(:state AS jsonb))"
                        ),
                        {"cid": self._campaign_id, "state": new_state},
                    )
                else:
                    await session.execute(
                        text(
                            "UPDATE combat SET state = CAST(:state AS jsonb) "
                            "WHERE campaign_id = :cid"
                        ),
                        {"state": new_state, "cid": self._campaign_id},
                    )

    def remove_combat(self, combat_id: str) -> None:
        _validate_identifier(combat_id, "combat_id")
        self._run(self._remove_combat(combat_id))

    async def _remove_combat(self, combat_id: str) -> None:
        async with self._session() as session:
            async with session.begin():
                row = await session.execute(
                    text("SELECT state FROM combat WHERE campaign_id = :cid FOR UPDATE"),
                    {"cid": self._campaign_id},
                )
                result = row.fetchone()
                if result is None or result[0] is None:
                    return
                state = result[0]
                if isinstance(state, str):
                    state = json.loads(state)
                state.pop(combat_id, None)
                await session.execute(
                    text(
                        "UPDATE combat SET state = CAST(:state AS jsonb) "
                        "WHERE campaign_id = :cid"
                    ),
                    {"state": json.dumps(state), "cid": self._campaign_id},
                )

    # ------------------------------------------------------------------
    # End states (archive)
    # ------------------------------------------------------------------

    def archive(
        self,
        record: ArchiveRecord,
        destination: Literal["graveyard", "hall_of_fame"],
    ) -> None:
        if destination not in _VALID_ARCHIVE_DESTINATIONS:
            raise ValueError(f"unknown archive destination: {destination!r}")
        self._run(self._archive(record, destination))

    async def _archive(self, record: ArchiveRecord, destination: str) -> None:
        payload = json.dumps(record.model_dump(mode="json"))
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO archive_record
                            (id, campaign_id, destination, payload, archived_at)
                        VALUES (:id, :cid, :dest, CAST(:payload AS jsonb), NOW())
                        """
                    ),
                    {
                        "id": _new_id(),
                        "cid": self._campaign_id,
                        "dest": destination,
                        "payload": payload,
                    },
                )

    # ------------------------------------------------------------------
    # Save slots
    # ------------------------------------------------------------------

    def save_slot(self, name: str) -> None:
        _validate_identifier(name, "slot_name")
        self._run(self._save_slot(name))

    async def _save_slot(self, name: str) -> None:
        snapshot = await self._build_snapshot()
        payload = json.dumps(snapshot)
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO save_slot (campaign_id, name, snapshot, created_at)
                        VALUES (:cid, :name, CAST(:snapshot AS jsonb), NOW())
                        ON CONFLICT (campaign_id, name)
                        DO UPDATE SET snapshot = CAST(EXCLUDED.snapshot AS jsonb),
                                      created_at = NOW()
                        """
                    ),
                    {"cid": self._campaign_id, "name": name, "snapshot": payload},
                )

    def load_slot(self, name: str) -> None:
        _validate_identifier(name, "slot_name")
        self._run(self._load_slot(name))

    async def _load_slot(self, name: str) -> None:
        # Read the snapshot in one session, restore in a second (separate) session
        # to avoid the "transaction already begun" error from mixing read + write
        # inside a single AsyncSession context.
        async with self._session() as read_session:
            row = await read_session.execute(
                text(
                    "SELECT snapshot FROM save_slot "
                    "WHERE campaign_id = :cid AND name = :name"
                ),
                {"cid": self._campaign_id, "name": name},
            )
            result = row.fetchone()
            if result is None:
                raise FileNotFoundError(f"save slot not found: {name!r}")
            snapshot = result[0]
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)

        # Restore in its own session/transaction
        await self._restore_snapshot(snapshot)

    # ------------------------------------------------------------------
    # Snapshot helpers (for save/load slot)
    # ------------------------------------------------------------------

    async def _build_snapshot(self) -> dict[str, Any]:
        """Capture the full mutable campaign state as a serialisable dict.

        All reads execute inside a single read-only transaction (T075 / ADR-027)
        so they see a consistent point-in-time view even if concurrent writes
        are in flight.  The ``SET TRANSACTION READ ONLY`` and every SELECT are
        inside the same ``async with session.begin():`` block.
        """
        async with self._session() as session:
            async with session.begin():
                await session.execute(text("SET TRANSACTION READ ONLY"))

                # character
                char_row = await session.execute(
                    text("SELECT data FROM character_sheet WHERE campaign_id = :cid"),
                    {"cid": self._campaign_id},
                )
                char_result = char_row.fetchone()
                character = None if char_result is None else char_result[0]
                if isinstance(character, str):
                    character = json.loads(character)

                # world
                world_row = await session.execute(
                    text("SELECT data FROM world WHERE campaign_id = :cid"),
                    {"cid": self._campaign_id},
                )
                world_result = world_row.fetchone()
                world = None if world_result is None else world_result[0]
                if isinstance(world, str):
                    world = json.loads(world)

                # events
                ev_rows = await session.execute(
                    text(
                        "SELECT payload FROM event WHERE campaign_id = :cid ORDER BY seq ASC"
                    ),
                    {"cid": self._campaign_id},
                )
                events = []
                for (payload,) in ev_rows:
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    events.append(payload)

                # summary
                sum_row = await session.execute(
                    text("SELECT summary_text FROM campaign WHERE id = :cid"),
                    {"cid": self._campaign_id},
                )
                sum_result = sum_row.fetchone()
                summary = "" if sum_result is None else (sum_result[0] or "")

                # active combats
                combat_row = await session.execute(
                    text("SELECT state FROM combat WHERE campaign_id = :cid"),
                    {"cid": self._campaign_id},
                )
                combat_result = combat_row.fetchone()
                combats: dict[str, Any] = {}
                if combat_result is not None and combat_result[0] is not None:
                    state = combat_result[0]
                    if isinstance(state, str):
                        state = json.loads(state)
                    combats = state

        return {
            "character": character,
            "world": world,
            "events": events,
            "summary": summary,
            "combats": combats,
        }

    async def _restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Restore campaign state from a snapshot dict in a single transaction."""
        async with self._session() as session:
            async with session.begin():
                # character_sheet
                if snapshot.get("character") is not None:
                    char_data = snapshot["character"]
                    char_json = json.dumps(char_data)
                    alive = char_data.get("alive", True)
                    await session.execute(
                        text(
                            """
                            INSERT INTO character_sheet (campaign_id, data, alive)
                            VALUES (:cid, CAST(:data AS jsonb), :alive)
                            ON CONFLICT (campaign_id)
                            DO UPDATE SET data = CAST(EXCLUDED.data AS jsonb),
                                          alive = EXCLUDED.alive
                            """
                        ),
                        {"cid": self._campaign_id, "data": char_json, "alive": alive},
                    )
                else:
                    await session.execute(
                        text("DELETE FROM character_sheet WHERE campaign_id = :cid"),
                        {"cid": self._campaign_id},
                    )

                # world
                if snapshot.get("world") is not None:
                    wd = snapshot["world"]
                    w_json = json.dumps(wd)
                    await session.execute(
                        text(
                            """
                            INSERT INTO world (campaign_id, location, visited, flags, turn, data)
                            VALUES (:cid, :loc, CAST(:vis AS jsonb), CAST(:flags AS jsonb),
                                    :turn, CAST(:data AS jsonb))
                            ON CONFLICT (campaign_id)
                            DO UPDATE SET location = EXCLUDED.location,
                                          visited   = CAST(EXCLUDED.visited AS jsonb),
                                          flags     = CAST(EXCLUDED.flags AS jsonb),
                                          turn      = EXCLUDED.turn,
                                          data      = CAST(EXCLUDED.data AS jsonb)
                            """
                        ),
                        {
                            "cid": self._campaign_id,
                            "loc": wd.get("current_location", ""),
                            "vis": json.dumps(wd.get("visited_locations", [])),
                            "flags": json.dumps(wd.get("flags", {})),
                            "turn": wd.get("turn", 0),
                            "data": w_json,
                        },
                    )
                else:
                    await session.execute(
                        text("DELETE FROM world WHERE campaign_id = :cid"),
                        {"cid": self._campaign_id},
                    )

                # events — delete and re-insert in order
                await session.execute(
                    text("DELETE FROM event WHERE campaign_id = :cid"),
                    {"cid": self._campaign_id},
                )
                for seq, ev_data in enumerate(snapshot.get("events", [])):
                    ev_json = json.dumps(ev_data)
                    await session.execute(
                        text(
                            """
                            INSERT INTO event (id, campaign_id, seq, payload, created_at)
                            VALUES (:eid, :cid, :seq, CAST(:payload AS jsonb), NOW())
                            """
                        ),
                        {
                            "eid": _new_id(),
                            "cid": self._campaign_id,
                            "seq": seq,
                            "payload": ev_json,
                        },
                    )

                # summary
                await session.execute(
                    text(
                        "UPDATE campaign SET summary_text = :txt, updated_at = NOW() "
                        "WHERE id = :cid"
                    ),
                    {"txt": snapshot.get("summary", ""), "cid": self._campaign_id},
                )

                # combats — NULL means no active fight
                combats = snapshot.get("combats") or {}
                combat_state = json.dumps(combats) if combats else None
                await session.execute(
                    text(
                        """
                        INSERT INTO combat (campaign_id, state)
                        VALUES (:cid, CAST(:state AS jsonb))
                        ON CONFLICT (campaign_id)
                        DO UPDATE SET state = CAST(EXCLUDED.state AS jsonb)
                        """
                    ),
                    {"cid": self._campaign_id, "state": combat_state},
                )
