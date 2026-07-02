---
description: "Task list for Accounts, Hardening & Observability — epic 001 slice, depends on 002 and 003"
---

# Tasks: Accounts, Hardening & Observability

**Input**: Design documents from `specs/004-accounts-hardening-obs/` and the shared epic artifacts in
`specs/001-web-platform-migration/` (research.md §3/§6/§7/§8, data-model.md §B.1/§C.1/§C.2/§C.3/§E,
contracts/http-api.md, tasks.md T011/T012/T025–T041). Depends on `002-persistence-foundation` and
`003-web-backend-mvp` being merged. The browser SPA is a separate feature, `005-professional-spa`;
sign-up/sign-in UI belongs to `005`, not here.

**Prerequisites**: spec.md, plan.md; epic research.md §3/§6/§7/§8, data-model.md
§B.1/§C.1/§C.2/§C.3/§E, contracts/http-api.md; `002` (PostgresStorage) and `003` (web backend MVP,
dev auth stub, documented API) merged.

**Tests**: Included — the constitution-mandated and success-criteria gates are first-class tasks:
resume-across-devices + session-lease (SC-001/002), per-account isolation (SC-003), atomic writes
under concurrency (SC-004), concurrent-campaign isolation (SC-005), graceful degradation (SC-006),
ended-run guarding (SC-007), observability (SC-008), and erasure/export (SC-009), plus the
plugability audit gate.

**Organization**: Tasks are grouped by user story. **MVP = User Story 1** (accounts + progress that
follows me: real auth, ownership, session lease, save/resume, privacy).

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1–US3 (user-story phases only)

## Path Conventions
Engine (unchanged): `src/gamebook/`. Backend (extended from `003`): `src/gamebook_web/`. Migrations:
`alembic/`. Tests: `tests/{server,qa}/`. No `frontend/` in this feature.

---

## Phase 1: Setup

**Purpose**: Auth + observability dependencies and dev infrastructure.

- [X] T001 Add OIDC client library + `opentelemetry-*` dependencies via `uv` in `pyproject.toml`, recorded in `docs/CONTRACTS.md` (constitution: no `uv add` without a CONTRACTS update). (Storage deps from `002`, web deps from `003` are already present.)
- [X] T002 [P] Add the OIDC provider + OTLP collector to `docker-compose.yml` at repo root (Postgres already added in `003`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Real auth, account ownership, and session-lease gating that every user story depends on.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [X] T003 Real OIDC authentication: JWT validation (JWKS, aud/exp) + account resolution from `sub` + a per-account scoping dependency in `src/gamebook_web/auth/` — replacing `003`'s dev auth stub behind the same seam (epic T011; FR-001/002/003)
- [X] T004 Account + Campaign persistence and ownership/scoping helpers in `src/gamebook_web/` (data-model §C.1/C.2; epic T012; FR-004)
- [X] T005 Alembic migration adding `account`, `campaign.account_id`, and `session_lease` in `alembic/versions/` (data-model §B.1/C.3; the `account`/`session_lease` rows deferred from `002`)
- [X] T006 Session-lease enforcement (single active session per campaign; acquire/takeover/release logic) in `src/gamebook_web/sessions/` (FR-005; epic T026 core)
- [X] T007 Gate state-changing routes on lease ownership (`409 not_session_holder`; stale-lease writes rejected) in `src/gamebook_web/api/` (FR-006; epic T027; depends on T006)
- [X] T008 [P] Confirm/extend the plugability audit (`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`) to cover the new `auth/` and `observability/` modules — no module reaches past the MCP/HTTP API interface (Principle IV, merge gate)

**Checkpoint**: real auth, account ownership, and session-lease gating exist; the `003` play loop still works through the new auth seam.

---

## Phase 3: User Story 1 — Accounts + progress that follows me (Priority: P1) 🎯 MVP

**Goal**: A player is authenticated by the dedicated service, progress is durably saved to their
account, they resume across devices, concurrent sessions are lease-controlled, and they can
export/delete their data. (Sign-up/sign-in UI is `005`; here it is the backend.)

**Independent Test**: Using the documented API with a real authenticated token, create an account on
first access, play several turns, end the session, re-authenticate on another session/device, and
resume the exact recorded state; confirm a second session on the same campaign is read-only until
takeover; confirm export returns the data and deletion cascades.

- [X] T009 [P] [US1] Session-lease endpoints `POST /campaigns/{id}/session`, `/session/takeover`, `DELETE /campaigns/{id}/session` in `src/gamebook_web/sessions/` + `api/` (FR-005; epic T026)
- [X] T010 [US1] Save/resume checkpoint `POST /campaigns/{id}/save` + resume from the exact recorded point via `GET /campaigns/{id}` in `src/gamebook_web/api/play.py` (FR-007/008; epic T028)
- [X] T011 [P] [US1] Privacy endpoints `GET /me`, `GET /me/export`, `DELETE /me` with cascade account → campaigns → engine rows in `src/gamebook_web/api/account.py` (FR-009; epic T029; research §8)
- [X] T012 [P] [US1] Test: resume across devices (sign out on A, re-authenticate on B, state intact; another account's data never visible) in `tests/server/test_session_resume.py` (SC-001/002/003, FR-003)
- [X] T013 [P] [US1] Test: a second concurrent session on the same campaign is read-only until takeover, then the prior session becomes read-only, in `tests/server/test_session_lease.py` (FR-005/006, SC-002)

**Checkpoint**: US1 provable — accounts, ownership, resume, session lease, and privacy work independently.

---

## Phase 4: User Story 2 — Reliable, production-grade service (Priority: P2)

**Goal**: Atomic writes under concurrency, isolated concurrent campaigns with no cross-account
leakage, graceful degradation when auth is down, and ended-run guarding with recorded-facts honor.

**Independent Test**: Run concurrent accounts/campaigns, induce a mid-write failure, confirm no
corruption and a clean resume; confirm isolation with no leakage; take auth down and confirm safe
degradation; confirm acting on an ended run is rejected and recorded facts survive adventure changes.

- [X] T014 [US2] Harden the atomic-write boundary in `PostgresStorage` (all-or-nothing per state change) in `src/gamebook/storage/postgres.py` — extend `002`'s single-write case to the concurrency/multi-account setting (Principle V; epic T031; FR-010)
- [X] T015 [P] [US2] Test: induced mid-write failure at concurrency → no partial/corrupted save; campaign resumes at last consistent state, in `tests/server/test_atomic_writes_concurrency.py` (SC-004, FR-010; epic T032)
- [X] T016 [P] [US2] Test: concurrent campaigns across accounts stay isolated/consistent with no cross-account leakage, in `tests/server/test_isolation_concurrency.py` (SC-005, FR-011; epic T033)
- [X] T017 [US2] Graceful degradation when the OIDC service is unavailable (signed-in players continue read-only to token expiry; new sign-ins → `503 auth_unavailable`) in `src/gamebook_web/auth/` (FR-012; epic T034)
- [X] T018 [US2] Reject acting on an ended run (`409 run_ended`) and honor recorded facts when adventure content changed, in `src/gamebook_web/api/` (FR-013; epic T035)

**Checkpoint**: the P1 experience is safe under production conditions.

---

## Phase 5: User Story 3 — Operators can observe and operate (Priority: P3)

**Goal**: Operators see health/error/latency + basic play metrics and can trace a failing turn without
exposing corrupted state to the player.

**Independent Test**: Trigger an induced error and a slow turn; confirm both surface in telemetry and
a trace locates the cause.

- [X] T019 [US3] OpenTelemetry setup (traces/metrics/logs via OTLP) + health/error-rate/latency + basic play metrics in `src/gamebook_web/observability/` (FR-014; epic T039)
- [X] T020 [US3] Per-request traces that locate a failing turn without exposing corrupted state to the player, in `src/gamebook_web/observability/` + `api/` (FR-015; epic T040)
- [X] T021 [P] [US3] Test: an induced error + slow turn surface in telemetry and a trace locates the cause, in `tests/server/test_observability.py` (SC-008; epic T041)

**Checkpoint**: the service is operable in production.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T022 [P] Finalize `docs/CONTRACTS.md` (account, session-lease, privacy `/me`, and observability sections; record the OIDC client + `opentelemetry-*` deps) and update `README`/`quickstart` (Principle III; FR-016; plan ACTION item)
- [X] T023 Run the full suite + plugability audit gate green, then the SDD review pipeline (`/sdd-qa` + `/sdd-security` → `/sdd-tech`) before merge (constitution Development Workflow)

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001 → T002 (parallel after deps).
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**. T003 (auth) and T004
  (account persistence) and T005 (migration) are the prerequisites; T006 (lease) depends on T004/T005;
  T007 (route gating) depends on T006.
- **User Stories (Phases 3–5)**: depend on Foundational; US1 (MVP) first; US2 (hardening) builds on
  US1's auth/lease/ownership paths; US3 (observability) wraps the existing API and can run alongside
  US2.
- **Polish (Phase 6)**: T022 (CONTRACTS) can start once the foundational + US1 contracts land; T023 is
  the final gate.

### Within each story
- US1: lease endpoints (T009) → save/resume (T010); privacy (T011) independent; tests (T012/T013)
  parallel once the endpoints exist.
- US2: harden atomic boundary (T014) before its test (T015); isolation (T016), degradation (T017),
  ended-run (T018) touch distinct files.
- US3: setup (T019) → per-request traces (T020) → test (T021).

### Parallel opportunities
- Setup: T002 [P].
- Foundational: T008 (audit) [P]; T003/T004/T005 touch different files but T004/T005 feed T006.
- US1: T009, T011, T012, T013 are [P] where distinct files.
- US2: T015, T016 are [P].
- US3: T021 [P].
- Polish: T022 [P].

## Implementation Strategy

### MVP first (User Story 1 only — accounts + resume)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **stop & validate** real auth, account
ownership, session lease, save/resume across devices, and privacy endpoints through the documented API
(no browser) → demo multi-account play.

### Incremental delivery
Foundational → US1 (accounts/resume — MVP) → US2 (production hardening) → US3 (observability) →
Polish. `005` then builds the SPA (including sign-up/sign-in UI) against `003`'s frozen OpenAPI
contract plus the account/session/privacy endpoints added here — without reworking the play loop.

## Notes
- The engine (`src/gamebook/`) stays behavior-unchanged; only `storage/postgres.py`'s atomic boundary
  is hardened, behind the same `StorageBackend` interface (Principle II/V).
- The auth integration sits behind the same seam `003` stubbed — swapping the stub for real OIDC does
  not touch the narrator or play loop (Principle II).
- Sign-up/sign-in UI is `005`'s concern; `004` delivers the backend auth, accounts, hardening, and
  observability. Do not pull frontend work in here.
- Every state change still flows through MCP — the harness never invents numbers (Principle I, enforced
  in `003` and unchanged here).
- Keep the plugability audit and full suite green at every checkpoint (constitution gate, T008/T023).
