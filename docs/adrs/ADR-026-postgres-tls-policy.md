# ADR-026: PostgreSQL TLS policy

**Status**: Accepted
**Date**: 2026-06-28
**Related spec**: [specs/006-cycle1-remediation/tasks.md](../../specs/006-cycle1-remediation/tasks.md) T072
**Related report**: [reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md](../../reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md)
**Code**: `src/gamebook/storage/postgres.py`

---

## Context

`PostgresStorage` creates its async engine with `create_async_engine(url, pool_pre_ping=True)`.
The URL comes directly from `DATABASE_URL`. If the URL omits `sslmode=require` (or equivalent),
`asyncpg` falls back to an unencrypted TCP connection, exposing database credentials and all
campaign/game state in plaintext.

The SDD cycle-1 review for `002-persistence-foundation` flagged this as **HIGH A02/A05**.
The fix must be default-on so an operator cannot accidentally deploy to production without TLS.

## Decision

All `PostgresStorage` engines use TLS by default. Plaintext connections are allowed only
when an explicit, documented non-production override is set.

### Implementation

1. Parse `DATABASE_URL` and ensure `sslmode` is set to `require` (or add `ssl=True` to the
   `create_async_engine` call) before constructing the engine.
2. When `ENV=production` (or `GAMEBOOK_ENV=production`), raise `RuntimeError` at startup if the
   URL does not contain `sslmode=require` and the override is not set.
3. Provide a local-development override `POSTGRES_SSL_MODE=disable` (or similar) that is
   **only** honored in non-production environments.

```python
ssl_mode = os.getenv("POSTGRES_SSL_MODE", "require")
if os.getenv("ENV") == "production" and ssl_mode != "require":
    raise RuntimeError("PostgreSQL TLS must be enabled in production (sslmode=require or POSTGRES_SSL_MODE=require)")
engine = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": ssl_mode})
```

(The exact SQLAlchemy/asyncpg API may vary; the intent is to enforce TLS by default.)

## Consequences

**Positive**
- No production deployment can silently use plaintext database connections.
- Credentials and player data are encrypted in transit by default.
- Local development remains convenient with an explicit, documented opt-out.

**Negative / trade-offs**
- Operators must ensure their Postgres server is configured with a valid TLS certificate.
- Local test setups that do not use TLS must set the override env var explicitly.

## Notes

- This ADR was created during the `006-cycle1-remediation` slice, which absorbs the
  `002-persistence-foundation` cycle-1 findings.
- The override is intentionally named `POSTGRES_SSL_MODE` (not `DATABASE_URL_SSL`) to make
  the TLS choice explicit and separate from connection routing.
