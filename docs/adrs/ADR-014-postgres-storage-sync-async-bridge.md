# ADR-014: PostgresStorage sync/async bridge via dedicated daemon thread

**Status**: Accepted
**Date**: 2026-06-27
**Related spec**: [specs/002-persistence-foundation/tasks.md](../../specs/002-persistence-foundation/tasks.md) T004
**Code**: `src/gamebook/storage/postgres.py`

---

## Context

`PostgresStorage` must implement the synchronous `StorageBackend` protocol (swap boundary #1)
while the only available Postgres driver (`asyncpg`) is async-only.  SQLAlchemy's asyncio
integration (`create_async_engine`, `AsyncSession`) requires async/await throughout.

The MCP server (FastMCP) runs its event loop on the main thread.  FastMCP may call sync tool
functions either:
- directly from inside a coroutine (in which case `asyncio.run()` inside the call would raise
  "This event loop is already running"), or
- from a thread pool thread (in which case `asyncio.run()` would work, but this is an
  internal implementation detail we cannot rely on).

Three approaches were considered:

### Option A — `asyncio.run()` per call
Call `asyncio.run(coro)` inside each sync method.  Simple, but fails if called from inside a
running event loop (the FastMCP case).

### Option B — `nest_asyncio` or `anyio`
Patch the running loop with `nest_asyncio` to allow nested `asyncio.run()` calls, or use
`anyio.from_thread.run_sync()`.  Introduces a third-party dependency (`nest_asyncio`) or
couples us to `anyio`'s threading model; neither is already in the dependency tree.

### Option C — Dedicated daemon thread with its own event loop ✅
Spin up a private `asyncio` event loop in a daemon thread at construction time.  Submit every
async operation to that loop via `asyncio.run_coroutine_threadsafe(coro, loop).result()`,
which blocks the calling thread until the coroutine completes.

## Decision

**Option C** — dedicated daemon thread with its own event loop.

```python
self._loop = asyncio.new_event_loop()
self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, ...)
self._thread.start()

def _run(self, coro):
    return asyncio.run_coroutine_threadsafe(coro, self._loop).result()
```

Every `StorageBackend` method delegates to an `async def _<method>()` counterpart and calls
it via `self._run(...)`.  Each async method opens its own `AsyncSession` and commits a single
transaction.

## Consequences

**Positive**
- Works from any calling context: sync, async, or in a thread pool — the background loop is
  always separate.
- No new dependencies beyond `asyncpg` and `sqlalchemy[asyncio]` (already in `pyproject.toml`).
- The `StorageBackend` interface and every other engine module remain untouched.
- The daemon thread dies automatically when the process exits; no explicit cleanup needed for
  the MCP server (a long-lived process).

**Negative / trade-offs**
- One extra thread per `PostgresStorage` instance (negligible for a single campaign scope).
- Blocking the caller thread per operation introduces latency vs. fully async code — acceptable
  for the Phase-2 MCP server, where throughput is bounded by the narrator's LLM call (seconds),
  not storage (milliseconds).
- `future.result()` surfaces exceptions from async code as the same exception type (not
  wrapped), so error handling is transparent.

## Notes

- `AsyncSession(engine, expire_on_commit=False)` is used to avoid "object detached" errors
  when accessing loaded objects after `session.begin()` exits.
- `_restore_snapshot` opens its own `AsyncSession` (not reused from `_load_slot`) to avoid
  SQLAlchemy's "A transaction is already begun on this Session" error when the second
  `async with session.begin()` is entered.
- The pool (`pool_pre_ping=True`) keeps connections healthy across the MCP server's lifetime.
