# Quickstart: Real OIDC Login Flow (Frontend) — 008

**Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

Validates User Stories 1–3 end-to-end against a real Dex instance and a real backend —
no mocks, no manual token entry. See [contracts/oidc-client-contract.md](./contracts/oidc-client-contract.md)
for the exact request/response shapes and [ADR-034](../../docs/adrs/ADR-034-oidc-frontend-spa-pkce-public-client.md)
for why this flow is structured this way.

## Prerequisites

- `docker compose --profile gameobs up` running (Postgres + Dex + OTel collector +
  backend + frontend, per `docker-compose.yml`) — or Dex + backend running natively with
  `frontend` started via `npm run dev` (port `5173`).
- `docker/dex/config.yaml`'s `gamebook` client converted to `public: true` with
  corrected `redirectURIs` (this slice's Dex config change — see the contract doc).
- Dex test credentials from `docker/dex/config.yaml`: `player1@example.com` /
  `gamebook-test-1` (local fixture only).

## Story 1 — sign in with real credentials through the browser

1. Open the app (`http://localhost:5173` dev, or `http://localhost:8080` compose) at
   `/auth` while signed out.
2. Click **Login**. Confirm the browser navigates to Dex's own `/auth` page (URL host
   changes to `localhost:5556`) — no in-app token field is shown on this path.
3. Sign in with `player1@example.com` / `gamebook-test-1`.
4. Confirm the browser lands back on the app's `/callback` route and then on
   `/dashboard`, already authenticated — inspect the Network tab and confirm a
   subsequent API call (e.g. `GET /me`) carries `Authorization: Bearer <JWT>` and
   returns `200`.

**Expected**: SC-001, SC-005 — zero manual token entry, first authenticated call
succeeds.

## Story 1 (edge case) — invalid credentials

1. From `/auth`, click **Login**, and on Dex's page submit a wrong password.
2. **Expected**: Dex shows its own error and lets you retry without the app reloading
   or entering a broken state (SC-002).

## Story 2 — session persists across reload; expiry routes back to login

1. Complete Story 1. Reload the tab.
2. **Expected**: still signed in, `/dashboard` renders without a redirect to `/auth`
   (FR-004).
3. Clear the `sessionStorage` OIDC user entry via devtools (simulating expiry), then
   trigger an API call (e.g. navigate to `/play`).
4. **Expected**: routed back to `/auth`, not an unhandled error (FR-005).

## Story 3 — no long-lived secret reaches the browser

1. Repeat Story 1 with the Network tab recording and "preserve log" on.
2. Inspect every request in the login flow (the `authorize` redirect, the `token` POST,
   the subsequent API calls) and the built JS bundle
   (`frontend/dist/assets/*.js` after `npm run build`).
3. **Expected**: no `gamebook-secret-dev` (or any client secret) appears anywhere
   (SC-003). The `token` POST body has no `client_secret` field — only
   `code_verifier`.

## Replay edge case

1. Complete Story 1. Copy the `/callback?code=...&state=...` URL from history.
2. Open it again in a new tab (simulating browser back/forward replay).
3. **Expected**: fails cleanly, routed to `/auth` with an error — does not silently sign
   in a second time (FR-008).

## Backward compatibility (dev stub)

1. Run `npm run dev` (not a production build). Confirm the dev token-paste field is
   still present on `/auth` (`import.meta.env.DEV` gate).
2. Run `npm run build && npm run preview`. Confirm the token-paste field is **absent**
   (FR-009 — not reachable in a production build).

## Automated coverage

- `frontend/e2e/` (Playwright): a full Story-1 browser flow against the compose stack
  (`gameobs` profile), asserting no manual token entry and a successful first
  authenticated call — this is the "browser automation, zero backdoors" proof required
  by SC-005.
- `frontend/src/hooks/useAuth.test.tsx` (or equivalent): unit coverage for the
  `useAuth()` seam against a mocked `react-oidc-context` provider — signed-out →
  pending → signed-in → expired transitions from [data-model.md](./data-model.md).
