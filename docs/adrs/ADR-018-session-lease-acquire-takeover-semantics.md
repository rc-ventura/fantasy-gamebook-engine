# ADR-018: Session lease — single active session per campaign

**Status**: Accepted | **Date**: 2026-06-28 | **Branch**: `feat/004-auth-obs`

## Context

Multiple browser tabs or devices can open the same campaign concurrently. Without coordination, two simultaneous writes (e.g., "go north" + "go south" in different tabs) could corrupt state or silently discard one player action.

Options evaluated:

| Option | Notes |
|---|---|
| **DB-backed session lease with explicit takeover** (chosen) | Atomic, durable, observable; integrates with Postgres transactions |
| Client-side last-write-wins | Simple but allows silent data loss |
| WebSocket pub/sub per campaign | Complex; requires WebSocket infra not in scope |
| HTTP long-polling | Extra complexity; lease is simpler and sufficient |

## Decision

### `session_lease` table

```sql
session_lease (
  campaign_id UUID PK FK→campaign ON DELETE CASCADE,
  lease_token UUID NOT NULL,
  acquired_at TIMESTAMPTZ NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  holder_account_id UUID NOT NULL FK→account
)
```

One row per campaign; the row is created on first `acquire` and replaced atomically on `takeover`.

### Lifecycle

`acquire(campaign_id, account_id)`:
- If no row exists: INSERT (new lease).
- If row exists and holder == account_id: UPDATE to renew.
- If row exists and holder != account_id and lease not expired: `409 not_session_holder`.
- If row exists and lease expired (any account): UPDATE (replace).

`validate(campaign_id, lease_token)`:
- Token mismatch → `409 not_session_holder`.
- Token matches but `expires_at < NOW()` → `409 lease_expired`.

`takeover(campaign_id, account_id, current_token)`:
- `acquire(..., force_takeover=True)` — always replaces regardless of holder.

All operations use `SELECT ... FOR UPDATE` inside a single transaction to prevent race conditions.

### Lease enforcement

`LeaseGuardMiddleware` intercepts all mutating HTTP requests (`POST`, `DELETE`, `PATCH`, `PUT`) to `/campaigns/{id}/**` (except exempt paths: session endpoints themselves, character creation, campaign deletion). It reads `X-Session-Lease` from the request header and calls `LeaseService.validate()` before passing to the route. On success, it renews the lease TTL.

### TTL

Default 30 minutes, renewed on every successful state-changing request. Expiry means the lease is "orphaned" — any account can claim it via `acquire`.

### Reads remain available

GET endpoints never require a lease; a second session can always read the campaign state.

## Consequences

**Positive**:
- Atomic: `SELECT FOR UPDATE` prevents two concurrent acquires from both succeeding.
- Durable: lease survives process restart (DB-backed).
- Explicit: the player knows they need to take over (409 with a clear message).
- Transparent: the middleware enforces the lease without touching play.py / combat.py.

**Negative**:
- Adds one round-trip per mutating request (lease validate + renew).
- Force-takeover is unconditional (any account can take over any campaign they own); a future refinement could require the current token.

## Related

- T006 (LeaseService), T007 (LeaseGuardMiddleware), T009 (session API endpoints)
- T013 (session lease tests)
