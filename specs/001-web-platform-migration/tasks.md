---
description: "Task list for Web Platform Migration (Phase 2)"
---

# Tasks: Web Platform Migration

**Input**: Design documents from `specs/001-web-platform-migration/`

**Prerequisites**: plan.md, spec.md (5 user stories), research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included **selectively** — only the test tasks mandated by the constitution
(`.specify/memory/constitution.md`): the plugability audit, the storage contract suite through the
consumer (ADR-009), and the success-criteria gates (numbers-never-in-prose, atomic writes,
isolation, observability). Not full per-endpoint TDD.

**Organization**: Tasks are grouped by user story. **MVP = User Story 1** (play in the browser).

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1–US5 (user-story phases only)

## Path Conventions
Engine (unchanged behavior): `src/gamebook/`. New backend: `src/gamebook_web/`. Frontend:
`frontend/`. Tests: `tests/{engine,server,qa}/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization for the Phase-2 stack.

- [ ] T001 Add backend dependencies via `uv` (fastapi, uvicorn, sqlalchemy, asyncpg, alembic, pydantic-ai, anthropic, opentelemetry-sdk + instrumentation) in `pyproject.toml`, and record them in `docs/CONTRACTS.md` (constitution: no `uv add` without a CONTRACTS update)
- [ ] T002 [P] Scaffold the `src/gamebook_web/` package (`api/`, `harness/`, `auth/`, `sessions/`, `observability/` with `__init__.py`)
- [ ] T003 [P] Scaffold the `frontend/` SPA project (React + Vite + TypeScript) under `frontend/`
- [ ] T004 [P] Add dev `docker-compose.yml` at repo root (PostgreSQL, OIDC provider, OTLP collector)
- [ ] T005 Initialize Alembic in `alembic/` wired to `DATABASE_URL`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared plumbing every user story depends on.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [ ] T006 Define Postgres schema/migrations for engine tables + `account` + `campaign` + `session_lease` in `alembic/versions/` (data-model.md §B)
- [ ] T007 Implement `PostgresStorage(StorageBackend)` in `src/gamebook/storage/postgres.py` — one transaction per state change (atomic), round-trips the domain (Principles II & V; swap boundary #1)
- [ ] T008 [P] Extend the storage contract suite to run against `PostgresStorage` **through the consumer** (mcp/combat) in `tests/server/` (ADR-009), including a mid-write-failure no-corruption case
- [ ] T009 FastAPI app skeleton with the consistent error envelope, `/health`, and OpenAPI in `src/gamebook_web/api/app.py` (contracts/http-api.md)
- [ ] T010 MCP host wiring: launch the engine FastMCP server and expose a client session (`MCPToolset` over `StdioTransport`) in `src/gamebook_web/mcp_host.py` (ADR-011)
- [ ] T011 OIDC auth: JWT validation (JWKS, aud/exp) + account resolution from `sub` + a per-account scoping dependency in `src/gamebook_web/auth/` (FR-007/009/010)
- [ ] T012 Account + Campaign persistence and ownership/scoping helpers in `src/gamebook_web/` (data-model.md §C.1/C.2)
- [ ] T013 Fold the `contracts/` drafts (HTTP API, `Scene`, Postgres mapping) into `docs/CONTRACTS.md` (Principle III; plan ACTION item)
- [ ] T014 [P] Extend the plugability audit (`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`) to cover `src/gamebook_web` — no module reaches past an interface (Principle IV, merge gate)

**Checkpoint**: persistence, auth, MCP host, and the API skeleton exist; engine still green.

---

## Phase 3: User Story 1 — Play the gamebook in a web browser (Priority: P1) 🎯 MVP

**Goal**: A player plays the full loop (start/resume → explore → combat → end-state) in a polished
UI, with every number engine-authoritative.

**Independent Test**: Load the app as a seeded/authenticated player, play opening → one exploration
turn → one combat → a clean end-state, and confirm every number traces to an MCP tool result.

- [ ] T015 [P] [US1] Define the `Scene` Pydantic schema (narrative, choices[], effects[] discriminated union) in `src/gamebook_web/harness/scene.py` (contracts/scene.md)
- [ ] T016 [US1] `NarratorBackend` port (Protocol) + deterministic `FakeNarrator` in `src/gamebook_web/harness/base.py` (ADR-011; Principle IV testability)
- [ ] T017 [US1] PydanticAI `AnthropicNarrator(NarratorBackend)` Agent — `output_type=Scene`, `MCPToolset` over the engine, `deps_type` for campaign context, model string injected, and **loads the active adventure module as lore (swap boundary #2, FR-019)** — in `src/gamebook_web/harness/agent.py` (ADR-011)
- [ ] T018 [US1] `output_validator` raising `ModelRetry` to reject any `Scene` carrying a literal number, in `src/gamebook_web/harness/agent.py` (Principle I, enforced in code)
- [ ] T019 [US1] Combat subagent via agent delegation (asks the player whether to test luck each round) in `src/gamebook_web/harness/combat_subagent.py` (ADR-001 pattern)
- [ ] T020 [US1] Play endpoints `POST /campaigns`, `POST /campaigns/{id}/character`, `POST /campaigns/{id}/turn`, `GET /campaigns/{id}`, `GET /campaigns/{id}/scene` in `src/gamebook_web/api/play.py` (FR-001/003/004)
- [ ] T021 [US1] Combat endpoints `POST /campaigns/{id}/combat/round` and `/flee` in `src/gamebook_web/api/combat.py` (FR-005)
- [ ] T022 [P] [US1] Test: a `Scene` with a literal stat value is rejected (`422 invalid_scene`) and never persisted; all shown numbers trace to MCP results, in `tests/server/test_scene_numbers.py` (SC-003, FR-014)
- [ ] T023 [P] [US1] Frontend: scene view + numbered choices + free-text input + character sheet + combat panel, rendering only engine state, in `frontend/src/` (FR-020/021)
- [ ] T024 [US1] Wire the typed API client from OpenAPI in `frontend/src/api/` and play opening → exploration → combat → end-state end to end

**Checkpoint**: US1 is fully playable and independently testable — the MVP.

---

## Phase 4: User Story 2 — Account + progress that follows me (Priority: P1)

**Goal**: Players sign in via the auth service, progress is durably saved to their account, and they
resume across devices.

**Independent Test**: Create an account, play several turns, sign out, sign in on another session,
and resume the exact recorded state.

- [ ] T025 [P] [US2] Sign-up / sign-in UI flow against the OIDC provider in `frontend/src/` (FR-008)
- [ ] T026 [US2] Session lease (single active session) + `POST /campaigns/{id}/session`, `/session/takeover`, `DELETE /campaigns/{id}/session` in `src/gamebook_web/sessions/` + `api/` (FR-025)
- [ ] T027 [US2] Gate state-changing routes on lease ownership (`409 not_session_holder`) in `src/gamebook_web/api/` (FR-025)
- [ ] T028 [US2] `POST /campaigns/{id}/save` checkpoint + resume from the exact recorded point via `GET /campaigns/{id}` in `src/gamebook_web/api/play.py` (FR-003/011)
- [ ] T029 [P] [US2] Privacy endpoints `GET /me`, `GET /me/export`, `DELETE /me` with cascade account → campaigns → engine rows in `src/gamebook_web/api/account.py` (research.md §8)
- [ ] T030 [P] [US2] Test: resume across devices (sign out on A, sign in on B, state intact) and a second concurrent session is read-only until takeover, in `tests/server/test_session_resume.py` (FR-025, SC-002)

**Checkpoint**: US1 + US2 both work independently.

---

## Phase 5: User Story 3 — Reliable, production-grade service (Priority: P2)

**Goal**: Concurrency isolation, no save corruption under failure, graceful degradation.

**Independent Test**: Run concurrent campaigns, induce a mid-write failure, confirm no corruption and
a clean resume; confirm malformed exchanges are rejected.

- [ ] T031 [US3] Harden the atomic write boundary in `PostgresStorage` (all-or-nothing per state change) in `src/gamebook/storage/postgres.py` (Principle V)
- [ ] T032 [P] [US3] Test: induced mid-write failure → no partial/corrupted save; campaign resumes at last consistent state, in `tests/server/test_atomic_writes.py` (SC-004)
- [ ] T033 [P] [US3] Test: concurrent campaigns stay isolated/consistent, no cross-account leakage, in `tests/server/test_isolation_concurrency.py` (SC-005, FR-009)
- [ ] T034 [US3] Graceful degradation when the OIDC service is unavailable (signed-in players continue read-only to token expiry; new sign-ins → `503 auth_unavailable`) in `src/gamebook_web/auth/` (FR-024)
- [ ] T035 [US3] Reject acting on an ended run (`409 run_ended`) and honor recorded facts when adventure content changed, in `src/gamebook_web/api/` (spec Edge Cases)

**Checkpoint**: the P1 experience is safe under production conditions.

---

## Phase 6: User Story 4 — Documented API (Priority: P3)

**Goal**: External clients drive the full play loop via a documented, authenticated API.

**Independent Test**: Complete a full play loop using only the published API docs, no browser.

- [ ] T036 [US4] Ensure OpenAPI documents every operation, input, and output; publish API docs from `src/gamebook_web/api/` (FR-016)
- [ ] T037 [US4] Token auth for external API clients, same rules as the UI (no privileged hidden path), in `src/gamebook_web/auth/` (FR-015/017)
- [ ] T038 [P] [US4] Test: full play loop via the documented API only (no browser) in `tests/server/test_api_external_client.py` (SC-007, FR-015)

**Checkpoint**: the engine is usable as a standalone documented API.

---

## Phase 7: User Story 5 — Operators can observe and operate (Priority: P3)

**Goal**: Operators see health/error/latency + basic play metrics and can trace a failing turn.

**Independent Test**: Trigger an error and a slow turn; confirm both surface in telemetry and a trace
locates the cause.

- [ ] T039 [US5] OpenTelemetry setup (traces/metrics/logs via OTLP) + health/error-rate/latency + basic play metrics in `src/gamebook_web/observability/` (FR-022)
- [ ] T040 [US5] Per-request traces that locate a failing turn without exposing corrupted state to the player, in `src/gamebook_web/observability/` + `api/` (FR-023)
- [ ] T041 [P] [US5] Test: an induced error + slow turn surface in telemetry and a trace locates the cause, in `tests/server/test_observability.py` (SC-009)

**Checkpoint**: the service is operable in production.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T042 [P] Finalize `docs/CONTRACTS.md` (HTTP API §, `Scene` §, Postgres mapping §) and update `README`/`quickstart`
- [ ] T043 [P] Frontend polish: loading/empty/error states + professional styling in `frontend/src/` (FR-020)
- [ ] T044 Performance pass: 95% of turns reflected < 2 s under normal load; validate ≥ 1,000 concurrent campaigns (SC-005/006)
- [ ] T045 Run the full suite + plugability audit gate green, then the SDD review pipeline (`/sdd-qa` + `/sdd-security` → `/sdd-tech`) before merge (constitution Development Workflow)

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**.
- **User Stories (Phases 3–7)**: all depend on Foundational; then proceed by priority
  (US1 → US2 → US3 → US4 → US5) or in parallel by separate developers.
  - US2 builds on US1 routes but is independently testable (account lifecycle + resume).
  - US3 hardens US1/US2 paths; US4 and US5 wrap the existing API.
- **Polish (Phase 8)**: depends on the desired user stories being complete.

### Within each story
- Models/schemas → narrator/services → endpoints → frontend → story test.
- US1: `Scene` (T015) → port/agent (T016–T019) → endpoints (T020–T021) → frontend (T023–T024); test T022 can run alongside once the agent exists.

### Parallel opportunities
- Setup: T002, T003, T004 in parallel.
- Foundational: T008 and T014 (tests) parallel with each other; T007/T009/T010/T011 touch different files but T008 depends on T007.
- US1: T015, T022, T023 are [P]; T023 (frontend) parallels backend tasks.
- US2: T025, T029, T030 are [P].
- US3: T032, T033 [P]. US4: T038 [P]. US5: T041 [P].

## Parallel Example: User Story 1
```text
# After Foundational is done, these can start together:
T015 [P] [US1] Scene schema            (src/gamebook_web/harness/scene.py)
T023 [P] [US1] Frontend scene view     (frontend/src/)
# Then, once the agent exists:
T022 [P] [US1] numbers-never-in-prose test (tests/server/test_scene_numbers.py)
```

## Implementation Strategy

### MVP first (User Story 1 only)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **stop & validate** the full play loop
in the browser with engine-authoritative numbers → demo.

### Incremental delivery
Foundational → US1 (MVP) → US2 (accounts/resume) → US3 (production hardening) → US4 (API) →
US5 (observability) → Polish. Each story is an independently testable increment.

## Notes
- The engine (`src/gamebook/`) stays behavior-unchanged; only `storage/postgres.py` is added behind
  the existing interface.
- Every state change still flows through MCP — the harness never invents numbers (Principle I,
  enforced by T018 + T022).
- Keep the plugability audit and full suite green at every checkpoint (constitution gate, T014/T045).
