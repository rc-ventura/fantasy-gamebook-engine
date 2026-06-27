# ADR-013: Async Alembic env.py pattern with asyncpg and DATABASE_URL

**Status**: Accepted
**Date**: 2026-06-27
**Related spec**: [specs/002-persistence-foundation/tasks.md](../../specs/002-persistence-foundation/tasks.md) T002
**Code**: `alembic/env.py`, `alembic.ini`

---

## Context

T002 initializes Alembic under `alembic/` wired to `DATABASE_URL`.  Three decisions had to
be made that are not captured in `research.md` §1 (which covers _what_ backend to use, not
the migration runner shape):

1. **Sync vs async migration runner.** The chosen driver is `asyncpg`, which is async-only
   and cannot be used with SQLAlchemy's default sync `engine_from_config()` / `engine.connect()`
   pattern that Alembic generates in `env.py`.

2. **Where to read `DATABASE_URL`.** Alembic's generated template reads the URL from
   `alembic.ini` via `config.get_main_option("sqlalchemy.url")`.  Putting credentials in a
   versioned config file is rejected on security grounds; environment variables are the
   standard 12-factor secret-delivery mechanism.

3. **Eagerly vs lazily read the URL.** If `DATABASE_URL` is read at module import time,
   `alembic/env.py` crashes on every `uv run pytest` invocation (no live Postgres in CI),
   breaking the test suite even though pytest never calls migration functions.

## Decision

### Async migration runner (online mode)

Use Alembic's documented async migration pattern:

```python
async def run_migrations_online() -> None:
    connectable = create_async_engine(url, poolclass=NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

`connection.run_sync(do_run_migrations)` bridges the async/sync boundary — Alembic's migration
execution is inherently synchronous, but it runs inside an async connection context.
`NullPool` is correct for one-shot migration scripts (no persistent connection pool needed).

### `DATABASE_URL` read lazily from environment

`DATABASE_URL` is read inside `_get_url()`, called only from `run_migrations_offline()` and
`run_migrations_online()` — never at module top level.  This means:

- Importing `alembic/env.py` (or pytest collecting it) never raises.
- A missing `DATABASE_URL` produces a clear `RuntimeError` at migration time, not a cryptic
  SQLAlchemy error later.

### `alembic.ini` `sqlalchemy.url` left empty

```ini
sqlalchemy.url =
```

`env.py` reads `DATABASE_URL` directly from `os.environ`; it never consults `sqlalchemy.url`
from the ini file.  The empty value prevents Alembic from complaining about the key being
absent while ensuring no one accidentally bakes a URL into the config.

## Alternatives considered

### Alternative A: read DATABASE_URL at module top level

```python
DATABASE_URL = os.environ["DATABASE_URL"]   # top of env.py
```

**Why not chosen**: `uv run pytest -q` would fail with `KeyError` on every run without a live
Postgres.  The test suite must stay green (green-gate rule) and no test needs a real DB in T002.

### Alternative B: use psycopg2 (sync driver)

**Why not chosen**: `asyncpg` is the chosen async Postgres driver (research §1); the Phase-2
FastAPI stack is async throughout.  Introducing a second driver for migrations adds a dep and
contradicts the "async-first" constraint.

### Alternative C: store URL in `alembic.ini`

**Why not chosen**: Credentials in a version-controlled file violate the 12-factor
configuration principle and the team security posture.  The `alembic.ini` does not go into
`.gitignore` — it is version-controlled as part of the migration framework setup.

### Alternative D: offline-only mode (no async needed)

Running all migrations via `alembic upgrade head --sql` (piped to psql) avoids the async
issue entirely.  **Why not chosen**: the CLAUDE.md Phase-2 command is
`DATABASE_URL=... uv run alembic upgrade head` (online mode); offline-only would require
a different operational flow and blocks `--autogenerate` from T003.

## Consequences

### Accepted

- `uv run pytest -q` and `uv run pytest tests/qa/ -q` stay green — `alembic/env.py` is
  never executed by the test suite, only importable.
- `DATABASE_URL=postgresql+asyncpg://... uv run alembic upgrade head` works as documented
  in `CLAUDE.md`.
- T003 (schema migration) and T004 (`PostgresStorage`) slot in cleanly: T003 sets
  `target_metadata` in `env.py` and adds a `versions/` file; T004 uses the same
  `AsyncEngine` pattern.

### Trade-offs

- `asyncio.run()` at the module bottom means `env.py` cannot be used in an already-running
  event loop (e.g. inside an async test).  This is acceptable: migrations are CLI tools, not
  called programmatically from the engine.
- `NullPool` means Alembic opens and closes a TCP connection per `upgrade head` call.  The
  CLI is a one-shot process, so this is correct and desirable.

### Conditions that invalidate this decision

1. The driver changes from `asyncpg` to a sync driver (e.g. `psycopg2`) — async pattern
   would be unnecessary.
2. Alembic adopts a first-class async runner that replaces `asyncio.run()` + `run_sync()`.

## References

- Alembic async migration docs: https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
- `research.md` §1 — storage backend decision (SQLAlchemy Core + asyncpg)
- `CLAUDE.md` Phase-2 web service section — `DATABASE_URL=... uv run alembic upgrade head`
- `specs/002-persistence-foundation/tasks.md` T002
