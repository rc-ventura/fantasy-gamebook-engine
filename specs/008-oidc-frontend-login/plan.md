# Implementation Plan: Real OIDC Login Flow (Frontend)

**Branch**: `008-oidc-frontend-login` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-oidc-frontend-login/spec.md`. The
architectural decision this plan is built on is recorded in
[ADR-034](../../docs/adrs/ADR-034-oidc-frontend-spa-pkce-public-client.md).

## Summary

Replace the SPA's paste-a-token dev stub with a real, browser-driven OIDC
Authorization Code + PKCE login against Dex (or any OIDC-compliant provider in
production) — no backend mediation, no client secret. The backend's OIDC validation
(ADR-022, slice 004) is already done and needs **no changes**: it only ever validates
`Authorization: Bearer <JWT>`, and the SPA will keep sending exactly that, just sourced
from a real Dex-issued `id_token` instead of a pasted dev token. The existing "auth
seam" (`setTokenProvider()` in `frontend/src/api/client.ts`, designed for this exact
swap since slice 003) is used as intended, so the blast radius is: `useAuth.ts`,
`AuthPage.tsx`, a new `/callback` route, `main.tsx`, and `docker/dex/config.yaml`. One
new frontend dependency (`react-oidc-context` + `oidc-client-ts`) is added.

## Technical Context

**Language/Version**: TypeScript 5.5 (frontend, unchanged); no backend language changes.

**Primary Dependencies**: *New*: `react-oidc-context`, `oidc-client-ts` (frontend only).
*Existing, unchanged*: React 18, react-router-dom 6, Vite, FastAPI OIDC validation
(`PyJWT`, `httpx` — ADR-022).

**Storage**: `sessionStorage` in the browser (via `WebStorageStateStore`) for the OIDC
user/session — no new backend storage; `docs/CONTRACTS.md` unchanged.

**Testing**: `vitest` (unit — `useAuth()` seam against a mocked OIDC provider),
`playwright` (`frontend/e2e/` — full browser-driven login flow against Dex, no mocks,
per spec 008's own acceptance criteria that this be provable via browser automation).

**Target Platform**: Browser SPA (Vite dev server, port `5173`; docker-compose
`gameobs` profile frontend, port `8080`).

**Project Type**: Web application (existing `frontend/` + `src/gamebook_web/` split).

**Performance Goals**: N/A — login is a one-time, human-paced redirect flow; no
throughput/latency target beyond "doesn't feel broken."

**Constraints**: FR-002 (no long-lived secret in browser code or traffic) is the binding
constraint — resolved architecturally by PKCE + public client (ADR-034), not by runtime
checks.

**Scale/Scope**: Single feature slice; touches ~5 frontend files + 1 Dex config file.
No new backend routes, no new domain entities.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Numbers Never in Prose | N/A | This slice touches auth, not narration/dice/combat. |
| II. Dependency on Interfaces Only | **Pass** | The auth seam is exactly this principle applied to the frontend: `useAuth()` / `setTokenProvider()` are the interface; `react-oidc-context` is the swappable implementation behind them, same as `dev_auth.py` ↔ `oidc_auth.py` on the backend (ADR-022) is swap boundary #3's harness-side counterpart. No component outside the seam depends on how the token was obtained. |
| III. CONTRACTS.md is Single Source of Truth | **Pass** | No cross-module interface, domain schema, or MCP tool contract changes — `docs/CONTRACTS.md` needs no edits. This feature's own contract lives in `contracts/oidc-client-contract.md` (external to CONTRACTS.md's scope, which is engine-internal). |
| IV. Determinism and Isolated Testing | N/A | No `rules`/`combat` changes; the plugability audit is unaffected. |
| V. Domain Invariants and Atomic Persistence | N/A | No `StorageBackend` or domain-model changes. |

No violations. Complexity Tracking is empty (see below).

*Post-Phase-1 re-check*: unchanged — Phase 1 design (data-model.md, contracts/) confirms
no domain/engine interface is touched; the only new "interface" is the
`react-oidc-context` library sitting behind the pre-existing `useAuth()` seam, which is
the principle working as intended, not a violation of it.

## Project Structure

### Documentation (this feature)

```text
specs/008-oidc-frontend-login/
├── plan.md              # This file
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── oidc-client-contract.md
└── tasks.md              # Phase 2 output (/speckit-tasks — not yet generated)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── hooks/
│   │   └── useAuth.ts          # CHANGED — backed by react-oidc-context instead of sessionStorage stub
│   ├── pages/
│   │   ├── AuthPage.tsx         # CHANGED — real "Login" redirect; dev token field gated on import.meta.env.DEV
│   │   └── CallbackPage.tsx     # NEW — processes the OIDC redirect return
│   ├── api/
│   │   └── client.ts            # UNCHANGED — setTokenProvider() seam is the extension point, already built
│   ├── App.tsx                  # CHANGED — adds the /callback route
│   └── main.tsx                 # CHANGED — wraps the app in <AuthProvider>
└── package.json                 # CHANGED — adds react-oidc-context, oidc-client-ts

docker/
└── dex/
    └── config.yaml               # CHANGED — gamebook client → public: true, corrected redirectURIs

src/gamebook_web/                 # UNCHANGED — oidc_auth.py already validates any bearer JWT
docs/
├── adrs/
│   └── ADR-034-*.md              # NEW — this plan's architectural decision
└── CONTRACTS.md                  # UNCHANGED
```

**Structure Decision**: Existing Option 2 (web application: `frontend/` +
`src/gamebook_web/`) layout is unchanged. This slice is additive/localized within
`frontend/` plus one Dex config file — no new top-level directories.

## Complexity Tracking

*No entries — Constitution Check has no violations to justify.*
