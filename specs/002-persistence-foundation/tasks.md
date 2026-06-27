---
description: "Task list for Persistence Foundation (PostgresStorage) — epic 001 slice"
---

# Tasks: Persistence Foundation (PostgresStorage)

**Input**: Design documents from `specs/002-persistence-foundation/` and the shared epic artifacts
in `specs/001-web-platform-migration/` (research.md §1, data-model.md §A/§B, quickstart.md).

**Prerequisites**: spec.md, plan.md; epic research.md §1 and data-model.md §A/§B.

**Tests**: Included — the storage contract suite through the consumer (ADR-009), the
mid-write-failure no-corruption case (SC-002), and the plugability audit gate (SC-004) are
constitution-mandated and are first-class tasks here.

**Organization**: Tasks are grouped by user story. **MVP = User Story 1** (engine runs on Postgres,
behavior-identical, through the consumer).

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1–US3

## Path Conventions
Engine (unchanged behavior): `src/gamebook/`. New storage impl: `src/gamebook/storage/postgres.py`.
Migrations: `alembic/`. Tests: `tests/{server,qa}/`.

---

## Phase 1: Setup

**Purpose**: Storage dependencies and migration framework.

- [ ] T001 Add storage dependencies via `uv` (`sqlalchemy`, `asyncpg`, `alembic`) in `pyproject.toml`, and record them in `docs/CONTRACTS.md` (constitution: no `uv add` without a CONTRACTS update). Web deps (`fastapi`, `pydantic-ai`, `opentelemetry-*`) are NOT added here — they belong to `003`/`004`.
- [ ] T002 Initialize Alembic in `alembic/` wired to `DATABASE_URL`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The durable backend and its schema, before any contract proof.

**⚠️ CRITICAL**: No user-story verification begins until this phase is complete.

- [ ] T003 Alembic migration: minimal `campaign (id PK, status, created_at)` + engine tables scoped to `campaign_id` (`character_sheet`, `world`, `event`, `combat`, `archive_record`) in `alembic/versions/` (data-model.md §B engine rows; `account`/`session_lease` deferred to `004`)
- [ ] T004 Implement `PostgresStorage(StorageBackend)` in `src/gamebook/storage/postgres.py` — scoped to a `campaign_id` supplied at construction, one transaction per state change (atomic, all-or-nothing), round-trips the domain (Principles II & V; swap boundary #1)

**Checkpoint**: a durable, behavior-identical backend exists behind the interface.

---

## Phase 3: User Story 1 — Engine runs on Postgres, behavior-identical, through the consumer (Priority: P1) 🎯 MVP

**Goal**: Prove swap boundary #1 — the consumer (mcp/combat) works against `PostgresStorage` with no
engine change, identical to `JSONStorage` and the in-memory backend.

**Independent Test**: Run the storage + MCP suite through the consumer against all three backends
(ADR-009); run the Phase-1 MCP path with `DATABASE_URL` + `GAMEBOOK_CAMPAIGN_ID`, play several turns,
restart, and confirm the campaign resumes at the exact recorded state.

- [ ] T005 [P] [US1] Extend the storage contract suite to run against `PostgresStorage` **through the consumer** (mcp/combat) in `tests/server/` (ADR-009), asserting identical outcomes to `JSONStorage` and the in-memory backend
- [ ] T006 [US1] Wire the Phase-2 MCP server path: `PostgresStorage` constructed with `DATABASE_URL` + `GAMEBOOK_CAMPAIGN_ID` (per `CLAUDE.md` Phase-2 path), JSON path still default
- [ ] T007 [P] [US1] Test: restart-resume — play turns, kill the process, reopen the same campaign, confirm state intact (FR-003, SC-001)

**Checkpoint**: US1 provable — the engine is durable and behavior-identical on Postgres.

---

## Phase 4: User Story 2 — A save survives a mid-write failure uncorrupted (Priority: P2)

**Goal**: Atomic, all-or-nothing writes; no corruption under induced failure.

**Independent Test**: Induce a failure mid-transaction during a state change; confirm the save is not
partially applied and the campaign resumes at the last consistent state.

- [ ] T008 [P] [US2] Test: induced mid-write failure → no partial/corrupted save; campaign resumes at last consistent state, in `tests/server/test_atomic_writes.py` (FR-004, SC-002)
- [ ] T009 [P] [US2] Test: domain object round-trip (object → DB → object) with invariants intact across all entity types, in `tests/server/test_storage_roundtrip.py` (FR-005, SC-003)

**Checkpoint**: US2 — unconditional integrity under failure.

---

## Phase 5: User Story 3 — The engine stays plugable with the new backend (Priority: P2)

**Goal**: The new module lives behind the interface; no module reaches past it.

**Independent Test**: Run the plugability audit; confirm no module imports a concrete storage impl.

- [ ] T010 [P] [US3] Confirm/extend the plugability audit (`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`) covers `src/gamebook/storage/postgres.py` — `mcp`/`combat` depend on `StorageBackend`, not on `PostgresStorage`/`JSONStorage` (Principle IV, merge gate; SC-004)

**Checkpoint**: US3 — architecture preserved.

---

## Phase 6: Polish & Contracts

- [ ] T011 [P] Fold the Postgres mapping § (table/column layout, transaction semantics, campaign scoping) into `docs/CONTRACTS.md` (Principle III; plan ACTION item; FR-008)
- [ ] T012 [P] Update `README`/`CLAUDE.md` Phase-2 storage commands if needed and run the quickstart storage validation (`uv run pytest tests/server -q` incl. Postgres suite; engine + audit green)
- [ ] T013 Run the full suite + plugability audit gate green, then the SDD review pipeline (`/sdd-qa` + `/sdd-security` → `/sdd-tech`) before merge (constitution Development Workflow)

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001 → T002.
- **Foundational (Phase 2)**: T003 (migration) and T004 (impl) depend on Setup; T004 depends on T003.
- **User Stories (Phases 3–5)**: all depend on Foundational; US1 (MVP) first, then US2 and US3 (US3's
  audit can run alongside US1/US2).
- **Polish (Phase 6)**: T011 (CONTRACTS) can start once T004 lands; T013 is the final gate.

### Parallel opportunities
- T005, T007, T008, T009, T010, T011, T012 are [P] where they touch distinct files.

## Implementation Strategy

### MVP first (User Story 1 only)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **stop & validate** the engine on
Postgres through the consumer, behavior-identical, restart-resilient → demo the Phase-2 MCP path.

### Incremental delivery
Foundational → US1 (durable + identical) → US2 (atomic under failure) → US3 (plugability) → Polish.
Each story is an independently testable increment.

## Notes
- The engine (`src/gamebook/`) stays behavior-unchanged; only `storage/postgres.py` and `alembic/`
  are added behind the existing interface.
- Account ownership, session leases, the web API, harness, and UI are deliberately deferred to
  `003`/`004`; do not pull them in here.
- Keep the plugability audit and full suite green at every checkpoint (constitution gate, T010/T013).
