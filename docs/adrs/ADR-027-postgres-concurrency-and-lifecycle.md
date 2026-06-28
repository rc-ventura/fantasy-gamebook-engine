# ADR-027: PostgresStorage concurrency-safe sequence allocation and deterministic lifecycle

**Status**: Accepted
**Date**: 2026-06-28
**Related spec**: [specs/006-cycle1-remediation/tasks.md](../../specs/006-cycle1-remediation/tasks.md) T073, T074, T075, T076
**Related report**: [reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md](../../reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md)
**Code**: `src/gamebook/storage/postgres.py`

---

## Context

The `002-persistence-foundation` implementation introduced `PostgresStorage` behind the
`StorageBackend` interface. The SDD cycle-1 review found three production-readiness gaps:

1. **Concurrency-unsafe sequence allocation.** `append_event` selects the next `seq` with
   `SELECT MAX(seq) FROM event WHERE campaign_id = :cid` and then INSERTs. The SELECT is not
   locked; two concurrent writers can read the same `MAX`, both try to insert the same `seq`,
   and one rolls back on the unique constraint. The inline comment claiming the row-level lock
   from the INSERT prevents races is misleading.
2. **No deterministic lifecycle.** `PostgresStorage` starts a private daemon thread and async
   engine but never closes them. Per-test fixtures leak threads and DB connections; the
   production MCP server relies on process exit to clean up.
3. **Inconsistent snapshot reads.** `_build_snapshot` reads character, world, events, and slot
   data across multiple tables without an explicit transaction boundary, so a save slot may
   capture a partially-mutated campaign state.

## Decision

### 1. Concurrency-safe event sequence allocation

`append_event` must allocate the next `seq` in a serializable way. We choose
**`SELECT MAX(seq) FROM event WHERE campaign_id = :cid FOR UPDATE`** as the minimal fix
because it locks the range for the specific campaign without adding new sequences or tables.

Rejected alternatives:
- **PostgreSQL sequence object per campaign** — requires DDL per campaign or a global sequence
  with a campaign partition, more complex than necessary.
- **Advisory lock per campaign** — works but requires explicit lock management and a matching
  unlock path; `FOR UPDATE` is simpler and self-contained in the transaction.
- **Retry on unique-constraint violation** — masks the race instead of preventing it.

### 2. Deterministic `PostgresStorage` lifecycle

`PostgresStorage` exposes a `close()` method that:
- Disposes the `AsyncEngine` and its connection pool.
- Stops the private daemon event loop and joins the thread.

Live-Postgres test fixtures call `close()` in teardown. The MCP server composition root calls
it on graceful shutdown.

### 3. Consistent snapshot reads

`_build_snapshot` wraps all its SELECTs in a single read-only transaction
(`async with session.begin()`), ensuring the saved snapshot reflects a single point in time.

## Consequences

**Positive**
- Concurrent writers append events without duplicate `seq` values or spurious rollbacks.
- Tests and long-running servers stop leaking threads and DB connections.
- Save slots capture internally consistent campaign state.

**Negative / trade-offs**
- `FOR UPDATE` serializes appends per campaign, which is acceptable because the event log is
  append-mostly and the MCP server processes one turn at a time per campaign.
- Callers must remember to invoke `close()`; fixtures get this via autouse teardown.

## Notes

- This ADR was created during the `006-cycle1-remediation` slice, which absorbs the
  `002-persistence-foundation` cycle-1 findings.
- The misleading inline comment in `append_event` is removed or corrected.
- Identifier validation (empty/`None`/`/`/`\`/`..`) for `slot` and `combat_id` is added to
  match `JSONStorage` parity and avoid obscure SQLAlchemy errors.
