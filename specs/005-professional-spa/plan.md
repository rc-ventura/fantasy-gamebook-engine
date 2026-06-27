# Implementation Plan: Professional SPA (Browser Frontend)

**Branch**: `005-professional-spa` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-professional-spa/spec.md` (decomposition slice
of epic `001-web-platform-migration`; consumes `003-web-backend-mvp`'s documented API. The
auth/accounts hardening is `004-accounts-hardening-obs`).

## Summary

Build the professional single-page web application that is one client of `003`'s documented HTTP
API — a React + Vite + TypeScript SPA under `frontend/` consuming the API via a typed client
generated from `003`'s frozen OpenAPI schema. It renders the full play loop — scene view
(narration + numbered choices + free-text input), character sheet, inventory/backpack, map, and
combat panel — all from real engine state, never fabricated values (epic FR-020/021). The play
loop runs in the browser: opening → exploration → combat → end-state, with every number shown
tracing to an engine result (epic US1 / SC-003). Loading/empty/error states and professional
styling are first-class. The sign-up/sign-in UI flow against the OIDC provider is gated on
`004`; until then the SPA uses `003`'s dev auth stub, with the auth seam designed to swap
cleanly. Resume-across-devices and the single-active-session read-only-until-takeover UX are
exercisable against `003`'s API. Tests: vitest (unit) + Playwright (E2E).

This is the **frontend slice** of the epic and can be developed against `003`'s frozen OpenAPI
using a mock, **in parallel with `004`**. The dependency chain is `002 → 003 → 004 // 005`.

## Technical Context

**Language/Version**: TypeScript (frontend).

**Primary Dependencies**:
- *New (frontend only)*: React + Vite + TypeScript; a typed API client generated from `003`'s
  frozen OpenAPI schema; vitest (unit/component tests) + Playwright (E2E browser tests).
- *Consumed, not owned*: the documented HTTP API + OpenAPI contract from `003`. The backend
  (FastAPI, narrator) is `003`; real OIDC is `004`.

**Storage**: N/A — the SPA consumes the API and holds no durable state; all game state is read
from / written through the HTTP API (Principle V).

**Testing**: vitest (frontend unit/component) + Playwright (E2E: play loop, resume-across-
devices, single-active-session). The frontend is testable against a mock OpenAPI client without
the backend or an LLM (Principle IV).

**Target Platform**: modern evergreen web browsers.

**Project Type**: web frontend SPA (separate from the engine and backend).

**Performance Goals**: 95% of turns reflected in the UI within 2 s under normal load (epic
SC-006); first in-game choice from landing in under 3 min (epic SC-001).

**Constraints**: renders only real engine state (no fabricated values, epic FR-021); consumes
only the frozen OpenAPI contract from `003` (no privileged/hidden path, epic FR-017); no
persistence in the UI (Principle V); sign-up/sign-in UI gated on `004`'s real OIDC (dev auth
stub from `003` until then).

**Scale/Scope**: one playable adventure module's UI; the panels (scene, character sheet,
inventory, map, combat); one SPA. Full concurrency/observability is `004`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0:

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| **I. Numbers Never in Prose** | PASS | The UI renders only engine-produced numbers returned by the API; it never invents, rolls, or fabricates values (epic FR-021). All stats, rolls, luck tests, and combat outcomes come from API responses that carry engine-produced values. |
| **II. Dependency on Interfaces Only** | PASS | The SPA consumes only the HTTP API contract from `003` (the frozen OpenAPI); it never reaches into engine internals, storage, or backend code. A mock OpenAPI client keeps it testable without the backend. |
| **III. CONTRACTS.md is the Single Source of Truth** | PASS | The SPA consumes `003`'s contract and adds no new cross-module contract; the HTTP API and `Scene` contracts are folded into `docs/CONTRACTS.md` by `003`. This feature references, not amends, the contract. |
| **IV. Determinism and Isolated Testing** | PASS | The frontend is testable against a mock OpenAPI client without the backend or an LLM; vitest unit tests + Playwright E2E run against the mock or the live API. |
| **V. Domain Invariants and Atomic Persistence** | PASS | No persistence in the UI; all durable game state lives behind the API (`003`/`002`). The SPA holds no durable game state — it renders and submits through the API. |

**Verdict**: No violations requiring Complexity Tracking justification. This feature adds no
new contract and no persistence, so there is no Principle III action item here.

## Project Structure

### Documentation (this feature)

```text
specs/005-professional-spa/
├── spec.md
├── plan.md              # This file
├── tasks.md
└── checklists/
    └── requirements.md
```

Shared design artifacts live in the epic and are referenced (not duplicated):

- Frontend decision: [../001-web-platform-migration/research.md](../001-web-platform-migration/research.md) §5
- HTTP API contract (consumed): [../001-web-platform-migration/contracts/http-api.md](../001-web-platform-migration/contracts/http-api.md)
- `Scene` contract (rendered): [../001-web-platform-migration/contracts/scene.md](../001-web-platform-migration/contracts/scene.md)
- Entities displayed: [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §A
- Validation guide: [../001-web-platform-migration/quickstart.md](../001-web-platform-migration/quickstart.md) (Frontend section)

### Source Code (repository root)

```text
frontend/                       # NEW: the professional SPA (separate from the engine/backend)
├── src/
│   ├── components/             # scene view, numbered choices, free-text input, character sheet,
│   │                           # inventory/backpack, map, combat panel, loading/empty/error states
│   ├── pages/                  # app shell, routing, landing/play views, campaign list/open
│   └── api/                    # typed API client generated from 003's frozen OpenAPI; mock mode for dev
└── tests/                      # vitest unit/component tests + Playwright E2E config

# NO backend, NO storage, NO engine here — those are 003/002/004. The SPA consumes the HTTP API only.
```

**Structure Decision**: Add `frontend/` as a separate web frontend SPA, consuming `003`'s
documented HTTP API via a typed OpenAPI client. No `src/gamebook_web`, no engine changes, no
storage. The dependency arrow points only at the HTTP API contract (Principle II):
`frontend/src/{components,pages,api}/` + `frontend/tests/`.

## Complexity Tracking

> No Constitution Check violations — this section is intentionally empty.

This feature adds no new contract and no persistence, so there is no tracked documentation
obligation.
