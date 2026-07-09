# Research: Real OIDC Login Flow (Frontend) — 008

**Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

Full rationale for the headline architecture call is recorded in
[ADR-034](../../docs/adrs/ADR-034-oidc-frontend-spa-pkce-public-client.md). This
document covers the remaining implementation-level unknowns the plan needs resolved.

---

## Decision: flow architecture — SPA-direct Authorization Code + PKCE

**Decision**: The browser talks to Dex's `authorize`/`token` endpoints directly
(Authorization Code + PKCE, RFC 7636); no backend `/callback` route is added.

**Rationale**: `src/gamebook_web/auth/oidc_auth.py` (ADR-022) only ever validates an
`Authorization: Bearer <JWT>` header — no cookies, no server-side session, no existing
`/callback` route. A backend-mediated exchange would require building that
infrastructure from scratch for no requirement that demands it; PKCE removes the need
for a client secret entirely, which satisfies FR-002 more directly than moving the
secret server-side would.

**Alternatives considered**: backend-mediated (BFF) exchange — rejected, see ADR-034.

---

## Decision: client library — `react-oidc-context`

**Decision**: Use `react-oidc-context` (wraps `oidc-client-ts`) rather than hand-rolling
PKCE with `crypto.subtle`.

**Rationale** (confirmed against current library docs via Context7,
`/authts/react-oidc-context`):
- Defaults to Authorization Code + PKCE for a client with no `client_secret` configured.
- Manages the transient `state`/`code_verifier`/nonce handoff itself (one-time use,
  stored and cleared internally) — this is exactly FR-008's replay-protection
  requirement, and it's security-sensitive code better left to a maintained library.
- `automaticSilentRenew` + a configurable `userStore` cover Story 2 (session survives
  reload) without custom polling/refresh logic.
- Exposes a hook (`useAuth()` from the library) whose surface —
  `isAuthenticated`, `signinRedirect()`, `removeUser()`, `error`, `isLoading` — maps
  almost 1:1 onto this project's existing `useAuth()` seam
  (`frontend/src/hooks/useAuth.ts`), so the swap stays localized the way the seam was
  designed for.

**Alternatives considered**:
- `axa-fr/oidc-client` — comparable feature set, less direct hook-for-hook fit with the
  existing `useAuth()` shape.
- `oidc-spa` — newer, smaller community footprint (medium reputation, no long track
  record); no advantage here over the widely-adopted `authts` project.
- Hand-rolled PKCE — rejected, see ADR-034.

---

## Decision: bearer credential — `id_token`, not `access_token`

**Decision**: The value sent as `Authorization: Bearer <...>` to the backend is the
OIDC **`id_token`**.

**Rationale**: the backend checks `aud == OIDC_AUDIENCE` (the client_id, `gamebook`)
and `iss == OIDC_ISSUER`. Per the OIDC Core spec, the `id_token`'s `aud` claim MUST
equal the client_id and it MUST always be a signed JWT — exactly what the backend
already assumes. `access_token` format/claims are opaque per RFC 6749; Dex happens to
issue JWT access tokens today, but relying on that would silently break against "any
OIDC-compliant provider" (spec 008's own assumption) and is not something the current
`oidc_auth.py` was written to depend on.

**Alternatives considered**: `access_token` — rejected (not spec-guaranteed to carry
`aud`/`iss`/JWT format across providers). Backend-minted session token — rejected (no
requirement drives adding backend session state).

---

## Decision: Dex configuration changes

**Decision**: Convert the existing `gamebook` static client in
`docker/dex/config.yaml` to a **public client** (`public: true`, drop `secret`) and fix
`redirectURIs` to the origins that actually run in this repo:
- `http://localhost:5173/callback` (Vite dev server, `frontend/vite.config.ts` pins
  port `5173`)
- `http://localhost:8080/callback` (docker-compose `gameobs` profile frontend, mapped
  `8080:80`)

**Rationale**: Dex has supported `public: true` static clients (no secret required,
PKCE-only token exchange) since PKCE landed in v2.26; this repo pins `ghcr.io/dexidp/dex:v2.41.1`
(`docker-compose.yml`), well past that. Nothing in the codebase currently reads
`gamebook-secret-dev` (`grep` across `docker-compose.yml`, `docs/`, `tests/` finds zero
references) — it is unused dead configuration. The existing `redirectURIs`
(`localhost:3000/callback`, `localhost:8000/callback`) match no service that actually
runs, so this is also a correctness fix, not just a hardening one.

**Alternatives considered**: registering a second client id (`gamebook-spa`) — rejected
as unneeded complexity; nothing else uses the `gamebook` client, so converting it in
place is safe and keeps `OIDC_AUDIENCE=gamebook` unchanged.

**Verification note (Dex `public: true` support)**: confirmed via web search against
`dexidp/dex` project docs/issues (PKCE support since v2.26; public clients declared with
`public: true` and no `secret`/`secretEnv` field). Re-verify against the pinned
`v2.41.1` `staticClients` schema during implementation before relying on it in code.

---

## Decision: production guard for the dev token-paste affordance (FR-009)

**Decision**: Gate the existing token-entry UI in `AuthPage.tsx` behind
`import.meta.env.DEV` (Vite's built-in "this is a dev server / non-production build"
flag).

**Rationale**: This is the exact mechanism the codebase already uses for other dev-only
paths (`frontend/src/components/ErrorBoundary.tsx`, `frontend/src/hooks/useGame.ts`).
Reusing it avoids introducing a second convention for the same concept, and satisfies
spec 008's Assumption that the dev affordance follow "the same kind of production guard
already established elsewhere in this project."

---

## Decision: token storage — `sessionStorage`

**Decision**: Configure `react-oidc-context`'s `userStore` as
`new WebStorageStateStore({ store: window.sessionStorage })`.

**Rationale**: matches the storage the dev stub already used
(`frontend/src/api/client.ts`: `sessionStorage.getItem('auth_token')` /
`setAuthToken()`), so reload/tab-close semantics are unchanged from what's already
shipped (satisfies FR-004 — survives reload — without silently upgrading persistence to
`localStorage`, which would be a scope increase spec 008 doesn't ask for).

---

## Decision: sign-out is local-only (no IdP-initiated logout)

**Decision**: Sign-out calls the library's `removeUser()` (clears the local token) and
does not redirect to Dex's `end_session_endpoint`.

**Rationale**: Dex's RP-initiated logout support is inconsistent across
versions/connectors, and nothing in spec 008's acceptance criteria requires ending the
identity provider's own session — only that the app stops holding/sending a token. This
keeps the sign-out path simple and avoids a dependency on a Dex feature that would need
separate verification.

---

## Addendum (implementation): browser-unreachable issuer requires hand-seeded metadata

**Found during implementation, not anticipated in the plan.** Dex's configured
`issuer` (`http://dex:5556/dex`) is the compose-network hostname the backend uses —
it's also, unavoidably, the exact value Dex bakes into every issued token's `iss`
claim, and the base URL Dex's own `.well-known/openid-configuration` response
constructs every endpoint URL from (`authorization_endpoint`, `token_endpoint`,
`jwks_uri`). A browser cannot resolve the `dex` hostname at all — so if the SPA's
OIDC client did standard discovery from the browser-reachable
`http://localhost:5556/dex`, it would receive back endpoint URLs
(`http://dex:5556/dex/auth`, ...) it could never actually call.

**Resolution**: `frontend/src/auth/oidcConfig.ts` hand-seeds `UserManagerSettings.metadata`
(confirmed as a supported, documented `oidc-client-ts` pattern — "If the OIDC/OAuth2
provider's metadata endpoint does not support CORS, additional settings can be
manually configured... seeding the metadata property") with the browser-reachable
endpoint URLs, while `metadata.issuer` still matches the real `iss` claim in issued
tokens. This only activates when a new `VITE_OIDC_ISSUER` env var differs from
`VITE_OIDC_AUTHORITY` — which is only true by default for local Dex (zero config).
A real production provider (only `VITE_OIDC_AUTHORITY` set) gets ordinary
`.well-known` discovery; nothing Dex-specific leaks into that path.

This was invisible at planning time because nothing in the codebase had yet
exercised a real browser round trip against the compose Dex instance — the same
category of gap as ADR-033 (found via live E2E, not by inspection).

## Out of scope / noted but not addressed by 008

- `frontend/src/api/client.ts`'s `acquireSession` / `takeoverSession` /
  `releaseSession` stub comments still say "real impl in slice 004," but the backend
  session-lease routes (`/me/game/session*`) already exist for real
  (`src/gamebook_web/api/sessions.py`). Wiring the frontend to the real session-lease
  endpoints is a separate, pre-existing gap unrelated to the login flow — not addressed
  here.
