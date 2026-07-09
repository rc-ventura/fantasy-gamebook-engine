# Data Model: Real OIDC Login Flow (Frontend) — 008

**Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

This slice introduces no backend/domain entities (`docs/CONTRACTS.md` §2 is unchanged)
— it is purely a frontend auth-flow change. The two "Key Entities" named in the spec map
onto browser-side, library-managed state:

---

## Player Session (browser-side)

Spec definition: "Whether the current browser tab/app instance is authenticated, and
whatever is needed to make authenticated calls on the player's behalf."

Concretely, this is `oidc-client-ts`'s `User` object, held in the configured
`WebStorageStateStore` (`sessionStorage`):

| Field | Type | Notes |
|---|---|---|
| `id_token` | `string` (JWT) | Sent as `Authorization: Bearer <id_token>` on every API call — see [research.md](./research.md) for why `id_token` rather than `access_token`. |
| `access_token` | `string` | Retained by the library for its own use (e.g. potential silent-renew bookkeeping); not sent to this project's backend. |
| `profile.sub` | `string` | Same `sub` the backend already resolves to an `account_id` (ADR-022) — no change to account resolution. |
| `profile.aud` | `string` | Must equal `gamebook` (the Dex client_id / `OIDC_AUDIENCE`). |
| `profile.iss` | `string` | Must equal `OIDC_ISSUER` (`http://dex:5556/dex` as seen by the backend container). |
| `expires_at` | `number` (unix seconds) | Drives `automaticSilentRenew` and the app's own "session expired → back to login" routing (FR-005). |

**Lifecycle**: created after a successful `/callback` round trip (User Story 1);
refreshed silently before `expires_at` while the tab is open (Story 2); cleared on
explicit sign-out (`removeUser()`) or when a silent-renew attempt itself fails (expired
IdP-side session → app treats as signed-out, FR-005).

**State transitions**:

```
signed-out --signinRedirect()--> pending (at Dex, outside the app)
pending --successful /callback--> signed-in
pending --error/cancel at Dex--> signed-out (with error surfaced, FR-006)
signed-in --silent renew succeeds--> signed-in (transparent)
signed-in --silent renew fails / expires_at passed--> signed-out (routed to login, FR-005)
signed-in --removeUser()--> signed-out
```

---

## Authorization Handoff

Spec definition: "The transient, one-time-use link between the outgoing redirect to the
identity provider and the matching incoming return trip. Must not be guessable or
reusable once consumed."

Concretely, this is `oidc-client-ts`'s internal `SigninState`, written to
`sessionStorage` under a library-managed key when `signinRedirect()` is called and
consumed (then deleted) when `/callback` is processed. It bundles:

| Field | Purpose |
|---|---|
| `state` | Opaque, unguessable value round-tripped through Dex; the library rejects a `/callback` whose `state` doesn't match a pending entry (covers the "replayed return trip" edge case, FR-008). |
| `code_verifier` | PKCE secret (RFC 7636) generated per attempt; exchanged with `code_challenge` sent on the outgoing `authorize` request. Never leaves the browser except as a `code_verifier` value posted directly to Dex's `token` endpoint. |
| `nonce` | Bound into the returned `id_token` to prevent token substitution. |

**Lifecycle**: created on `signinRedirect()`; consumed and deleted on the first
successful `/callback` processing. A second hit on the same callback URL (browser
back/forward, bookmarked link) finds no matching pending entry and fails cleanly — the
app's `/callback` route sends the player back to `/auth` with an error, never a second
sign-in (edge case in spec 008).

---

## No backend/domain changes

- `docs/CONTRACTS.md` §2 (domain schema) — unchanged.
- `docs/CONTRACTS.md` §6 (MCP tool contract) — unchanged.
- `src/gamebook_web/auth/oidc_auth.py` (ADR-022) — unchanged; continues to validate
  whatever bearer JWT it's given the same way regardless of how the browser obtained it.
