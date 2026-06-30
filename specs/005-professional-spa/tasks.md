---
description: "Task list for Professional SPA — epic 001 slice, consumes 003's documented API"
---

# Tasks: Professional SPA (Browser Frontend)

**Input**: Design documents from `specs/005-professional-spa/` and the shared epic artifacts in
`specs/001-web-platform-migration/` (research.md §5, contracts/http-api.md, contracts/scene.md,
data-model.md §A, quickstart.md Frontend section). Consumes `003-web-backend-mvp`'s documented
API; the auth/accounts hardening is `004-accounts-hardening-obs`.

**Prerequisites**: spec.md, plan.md; epic research.md §5, contracts/http-api.md,
contracts/scene.md, data-model.md §A; `003`'s frozen OpenAPI contract available. US2 sign-in UI
additionally requires `004`'s real OIDC.

**Tests**: Included — vitest (unit/component) + Playwright (E2E) are first-class tasks here:
the browser play loop (SC-004), the numbers-never-fabricated audit (SC-003), resume-across-
devices (SC-002), and the single-active-session UX.

**Organization**: Tasks are grouped by user story. **MVP = User Story 1** (play loop in the
browser, first against a mock then against the live `003` API).

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1–US3

## Path Conventions
Frontend SPA: `frontend/`. Tests: `frontend/tests/`. No backend, storage, or engine changes in
this feature.

---

## Phase 1: Setup

**Purpose**: Frontend scaffolding, test runners, and the typed API client.

- [x] T001 Scaffold the `frontend/` SPA project (React + Vite + TypeScript) under `frontend/` — `package.json`, `tsconfig`, Vite config, entry point
- [x] T002 [P] Set up vitest (unit/component runner) + Playwright (E2E) in `frontend/`
- [x] T003 Generate the typed API client from `003`'s frozen OpenAPI schema into `frontend/src/api/` (keeps the UI honest to the contract; regenerable when `003` updates)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared plumbing the play loop depends on.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [x] T004 Wire the typed API client in `frontend/src/api/` with a configurable base URL + auth-token injection seam
- [x] T005 [P] Add a mock mode for dev against `003`'s frozen OpenAPI contract (deterministic mock responses) so the UI is testable without the backend (Principle IV)
- [x] T006 App shell + routing (landing/play views, campaign list/open) in `frontend/src/pages/`
- [x] T007 Dev-auth-stub integration: sign-in UI against `003`'s dev auth stub, token storage/injection, designed so `004`'s real OIDC swaps in without touching the play loop

**Checkpoint**: typed client + mock mode + app shell + dev auth exist; the UI is testable against the mock.

---

## Phase 3: User Story 1 — Play the gamebook in a web browser (Priority: P1) 🎯 MVP

**Goal**: A player plays the full loop (opening → exploration → combat → end-state) in the
browser, with every number engine-authoritative.

**Independent Test**: Load the app (mock or live `003`), play opening → one exploration turn →
one combat → a clean end-state; confirm every number shown traces to an engine result, no
UI-fabricated values.

- [x] T008 [P] [US1] Scene view: render narration + numbered choices + free-text input in `frontend/src/components/` (FR-004)
- [x] T009 [P] [US1] Character sheet panel rendering only real engine state in `frontend/src/components/` (FR-007/008)
- [x] T010 [P] [US1] Inventory/backpack panel rendering only real engine state in `frontend/src/components/` (FR-007/008)
- [x] T011 [P] [US1] Map panel rendering only real engine state (current location, visited) in `frontend/src/components/` (FR-007/008)
- [x] T012 [P] [US1] Combat panel: rounds, optional luck tests, final outcome — all engine-computed — in `frontend/src/components/` (FR-005)
- [x] T013 [US1] Play-loop wiring: create/resume campaign → character creation → take turn (choice/free text) → combat → end-state, calling the typed API client (FR-001/003/006)
- [x] T014 [US1] E2E (Playwright): opening → exploration → combat → end-state in the browser against the mock (then the live `003` API), in `frontend/tests/` (SC-004)
- [x] T015 [P] [US1] Audit test: every number shown in the UI traces to an engine result from the API — zero UI-fabricated values — in `frontend/tests/` (SC-003, FR-002/008)

**Checkpoint**: US1 fully playable in the browser against the mock (then the live `003` API), numbers engine-authoritative.

---

## Phase 4: User Story 2 — Account sign-in + resume in the UI (Priority: P2)

**Goal**: Players sign in, progress follows them, resume across devices, and a single active
session per campaign.

**Independent Test**: Sign in, play several turns, sign out, sign in on another session/device,
resume the exact recorded state; open a second tab and confirm it is read-only until takeover.

- [x] T016 [US2] Sign-up / sign-in UI flow against the OIDC provider in `frontend/src/` (gated on `004`'s real OIDC; dev auth stub until then) (FR-010/011)
- [x] T017 [US2] "My campaigns" view showing only the signed-in player's campaigns in `frontend/src/pages/` (FR-011)
- [x] T018 [US2] Single-active-session UX: acquire/refresh/takeover/release session lease; second tab read-only until takeover, in `frontend/src/components/` (FR-013)
- [ ] T019 [P] [US2] E2E (Playwright): resume across devices — sign out on A, sign in on B, state intact — in `frontend/tests/` (FR-012, SC-002)
- [ ] T020 [P] [US2] E2E (Playwright): single active session — second tab read-only until takeover — in `frontend/tests/` (FR-013)

**Checkpoint**: US2 — sign-in, resume, and single-active-session UX work in the browser.

---

## Phase 5: User Story 3 — A polished, professional UI (Priority: P2)

**Goal**: Loading/empty/error states + professional styling + accessibility; every value
engine-real.

**Independent Test**: Exercise each panel and state; confirm clear loading/empty/error and no
fabricated values.

- [x] T021 [P] [US3] Loading states for every async operation in `frontend/src/components/` (FR-009)
- [x] T022 [P] [US3] Empty states (no character yet, empty inventory, no map data) in `frontend/src/components/` (FR-009)
- [x] T023 [P] [US3] Error states for API errors (auth unavailable, run ended, not session holder) — safe, no corrupted game state — in `frontend/src/components/` (FR-009/015)
- [x] T024 [US3] Professional styling pass across all panels/views in `frontend/src/` (epic FR-020)
- [ ] T025 [US3] Accessibility pass (keyboard navigation, semantics, contrast) across the play loop in `frontend/src/`

**Checkpoint**: US3 — a polished, professional, accessible UI.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T026 [P] Finalize `frontend/` docs/README for running the SPA (dev against the mock, dev against live `003`, running vitest + Playwright)
- [ ] T027 Run vitest + Playwright green against the mock, then against the live `003` API; run the SDD review pipeline (`/sdd-qa` + `/sdd-security` → `/sdd-tech`) before merge (constitution Development Workflow)

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001 first; T002 parallel; T003 depends on `003`'s frozen OpenAPI being
  available.
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**. T005 (mock) lets
  US1 develop without the live backend.
- **User Stories (Phases 3–5)**: depend on Foundational; US1 (MVP) first against the mock, then
  against live `003`; US3 (polish) can run alongside US1/US2.
  - US2 sign-in UI (T016) **additionally depends on `004`'s real OIDC**; resume-across-devices
    (T019) and single-active-session (T018/T020) are exercisable against `003`'s API now.
- **Polish (Phase 6)**: depends on the desired user stories; T027 is the final gate.

### Within US1
Panels (T008–T012) parallel → play-loop wiring (T013) → E2E (T014); the audit (T015) can run
alongside once the panels exist.

### Parallel opportunities
- Setup: T002 parallel.
- Foundational: T005 parallel; T004/T006/T007 touch different files.
- US1: T008–T012 panels parallel; T015 audit parallel.
- US2: T019, T020 parallel.
- US3: T021, T022, T023 parallel; Polish: T026 parallel.

## Implementation Strategy

### MVP first (User Story 1, against the mock)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 against the mock → **stop &
   validate** the full browser play loop with engine-authoritative numbers → then validate
   against the live `003` API → demo.

### Incremental delivery
Foundational → US1 (MVP: mock then live `003`) → US2 (sign-in/resume/session, sign-in gated on
`004`) → US3 (polish) → Polish. `004` adds real OIDC; `005`'s sign-in UI swaps the dev stub for
the real provider without touching the play loop.

## Notes
- The SPA consumes only `003`'s documented HTTP API; it adds no new cross-module contract
  (Principle III) and no persistence (Principle V).
- Every value shown comes from the API — the UI never invents numbers (Principle I, FR-002/008).
- `005` can develop against `003`'s frozen OpenAPI using a mock, **in parallel with `004`**.
- The sign-up/sign-in UI (T016) is gated on `004`'s real OIDC; until then the SPA uses `003`'s
  dev auth stub. Keep the auth seam clean so the play loop is untouched by that swap.
- Keep vitest + Playwright green at every checkpoint (constitution gate, T027).
