# SQLAlchemy AsyncSession: "A transaction is already begun" when reusing a session

**Date**: 2026-06-27
**Discovered during**: T004 PostgresStorage `load_slot` / `_restore_snapshot`

## The gotcha

`AsyncSession` uses **autobegin**: the first `execute()` call (or entering `async with
session.begin()`) on a fresh session implicitly starts a transaction.  If you then call
`session.begin()` again on the *same* session object — even inside a nested `async with`
block — SQLAlchemy raises:

```
sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session.
```

This can happen when:
1. You open an `AsyncSession` via `async with AsyncSession(engine) as session:`
2. Execute some reads (autobegin → transaction started)
3. Pass `session` to a helper that calls `async with session.begin():` again

## The fix

**Never reuse a session across a read and a subsequent write that needs its own
`session.begin()`.** Instead, open a new session for the write:

```python
# WRONG — reuses the session, raises InvalidRequestError
async with self._session() as session:
    row = await session.execute(...)   # autobegin started here
    await self._restore_snapshot(snapshot, session)  # session.begin() → error

# CORRECT — separate sessions for read and write
async with self._session() as read_session:
    row = await read_session.execute(...)
    snapshot = row.fetchone()[0]
# read_session closed here

await self._restore_snapshot(snapshot)  # opens its own session internally
```

## Rule of thumb

Each `AsyncSession` context manager (`async with session.begin():`) should wrap exactly **one
logical transaction**.  If a helper needs to write transactionally, let it open its own
session; do not thread a half-used session through multiple helpers.
