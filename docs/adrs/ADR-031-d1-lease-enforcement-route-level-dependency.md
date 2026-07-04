# ADR-031: D1 lease enforcement via route-level `require_lease` dependency

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-02 |
| **Supersedes** | ADR-023 enforcement section (amended) |
| **Related** | ADR-023 (session lease semantics), ADR-025 (DB-backed campaign registry) |

## Context

ADR-023 specified `LeaseGuardMiddleware` as the enforcement mechanism for the session lease: "intercepts all mutating HTTP requests... calls `LeaseService.validate()` before passing to the route." This was designed for the original `/campaigns/{id}/**` route scheme, where `campaign_id` is extracted directly from the URL path.

The D1 redesign (Phase 2a) changed the route scheme to `/me/game/**`, where `campaign_id` is resolved from the caller's **account** (via `CampaignRegistry.get_active_for_account(account_id)`), not from the URL. This created a fundamental problem:

1. **`LeaseGuardMiddleware` cannot resolve `campaign_id` safely.** It runs as plain ASGI middleware, *before* FastAPI's dependency injection graph. To get the account, it would need to call `get_current_account` directly as a plain function — but `app.dependency_overrides` (which swaps the dev stub for real OIDC in production) only intercepts `Depends()` resolution, not direct function calls. The middleware would always hit the dev stub, creating a **silent auth bypass** in production.

2. **The middleware was patched with an exemption.** Rather than being refactored, `_EXEMPT_SUFFIX_PATTERNS = [^/me.*$]` was added to exempt all `/me/**` routes. This made the lease subsystem **functionally inert in production** — no mutating route called `validate()`. The SDD final review (cycle-1) escalated this to CRITICAL (C-01).

## Decision

Replace middleware-based lease enforcement with a **route-level FastAPI dependency**: `require_lease`.

```python
async def require_lease(
    request: Request,
    account: Account = Depends(get_current_account),
    x_session_lease: str | None = Header(default=None, alias="X-Session-Lease"),
) -> None:
    ...
```

`require_lease` is added via `dependencies=[Depends(require_lease)]` (or as a parameter) on every mutating `/me/game/**` route:

- `POST /me/game` (create game)
- `POST /me/game/turn` (take turn)
- `POST /me/game/character` (create character)
- `POST /me/game/save` (save game)
- `DELETE /me/game` (abandon game)

**Not** wired on session lifecycle routes (`POST /me/game/session`, `POST /me/game/session/takeover`, `DELETE /me/game/session`) — these manage the lease itself and have their own internal validation (acquire checks for existing holder, takeover validates `current_token`, release validates account + token).

### How it works

1. `account` is resolved via `Depends(get_current_account)` — the same dependency every route already uses. FastAPI's `app.dependency_overrides` applies here exactly as it does everywhere else: dev stub in tests, real OIDC in production.

2. The dependency resolves the caller's active `campaign_id` from `CampaignRegistry.get_active_for_account(account.account_id)`.

3. If no lease exists for that campaign yet, enforcement is a **no-op** (the lease is opt-in: it starts enforcing exclusivity only after a session calls `POST /me/game/session` to acquire one).

4. If a lease exists, the `X-Session-Lease` header is validated via `LeaseService.validate(campaign_id, account_id, lease_token)`. A missing or stale token → `409 not_session_holder`.

5. On success, the lease TTL is renewed (best-effort, never breaks the request).

### `LeaseGuardMiddleware` retained as fail-closed guard

The middleware is retained but reduced to a single responsibility: **fail closed on misconfiguration**. If `OIDC_JWKS_URI` is set (OIDC expected) but `DATABASE_URL` is missing (lease state cannot be tracked), every mutating request gets `503 auth_unavailable`. This catches the deployment misconfiguration case without attempting per-request lease validation.

## Consequences

- **Lease enforcement works in production.** A concurrent write from two sessions on the same campaign is rejected with `409` for the non-holder.
- **Auth dependency override is respected.** `require_lease` goes through the normal DI graph, so `app.dependency_overrides` works correctly.
- **No silent auth bypass.** The middleware's direct-call approach (which would bypass `dependency_overrides`) is eliminated.
- **Lease is opt-in.** Sessions that never call `POST /me/game/session` are not lease-enforced. This matches the SPA's `VITE_SESSION_LEASE=true` opt-in gate.
- **`LeaseGuardMiddleware` is simpler.** It no longer attempts URL-based `campaign_id` extraction or token validation — it only guards against the DB-misconfiguration case.
