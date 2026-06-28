---
description: "Task list for Web Backend MVP — epic 001 slice, depends on 002; SPA is 005"
---

# Tasks: Web Backend MVP

**Input**: Design documents from `specs/003-web-backend-mvp/` and the shared epic artifacts in
`specs/001-web-platform-migration/` (research.md §2/§4, contracts/http-api.md, contracts/scene.md,
data-model.md §C.4, quickstart.md). Depends on `002-persistence-foundation` being merged. The browser
SPA is a separate feature, `005-professional-spa`, which consumes this feature's documented API.

**Prerequisites**: spec.md, plan.md; epic research.md §2/§4, contracts/http-api.md,
contracts/scene.md, data-model.md §C.4; `002` (PostgresStorage) merged.

**Tests**: Included — the constitution-mandated gates are first-class tasks here: the API play loop
(SC-001), numbers-never-in-prose (SC-002), invalid-`Scene` rejection (SC-003), and the plugability
audit extended to `src/gamebook_web` (SC-004).

**Organization**: Tasks are grouped by user story. **MVP = User Story 1** (play loop drivable through
the documented API with the `FakeNarrator`).

## Format: `[ID] [P?] [Story] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)
- **[Story]**: US1–US3

## Path Conventions
Engine (unchanged): `src/gamebook/`. New backend: `src/gamebook_web/`. Tests: `tests/{server,qa}/`.
No `frontend/` in this feature.

---

## Phase 1: Setup

**Purpose**: Backend scaffolding and web dependencies.

- [x] T001 Add web backend dependencies via `uv` (`fastapi`, `uvicorn`, `pydantic-ai`, `anthropic`) in `pyproject.toml`, recorded in `docs/CONTRACTS.md`. (Storage deps already added in `002`; `opentelemetry-*` deferred to `004`; frontend toolchain deferred to `005`.)
- [x] T002 [P] Scaffold the `src/gamebook_web/` package (`api/`, `harness/`, `auth/`, `sessions/` with `__init__.py`)
- [x] T003 [P] Add dev `docker-compose.yml` at repo root with PostgreSQL (OIDC provider + OTLP collector are added in `004`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared plumbing the play loop depends on.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [x] T004 FastAPI app skeleton with the consistent error envelope, `/health`, and OpenAPI in `src/gamebook_web/api/app.py` (contracts/http-api.md)
- [x] T005 MCP host wiring: launch the engine FastMCP server and expose a client session (`MCPToolset` over `StdioTransport`) in `src/gamebook_web/mcp_host.py` (ADR-011)
- [x] T006 Dev auth stub + minimal campaign scoping helpers in `src/gamebook_web/auth/` + `sessions/` (single development account/campaign context; designed so `004` swaps in real OIDC without touching the play loop)
- [x] T007 [P] Extend the plugability audit (`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`) to cover `src/gamebook_web` — no module reaches past the MCP/HTTP API interface (Principle IV, merge gate; SC-004)
- [x] T008 Fold the `contracts/` drafts (HTTP API, `Scene`) into `docs/CONTRACTS.md` (Principle III; plan ACTION item)

**Checkpoint**: API skeleton, MCP host, dev auth, and audit gate exist; engine still green.

---

## Phase 3: User Story 1 — Play loop drivable through the documented API (Priority: P1) 🎯 MVP

**Goal**: A developer drives the full loop (create/resume → explore → combat → end-state) entirely
through the documented API, with every number engine-authoritative, using the `FakeNarrator` (no LLM,
no browser) and the real PydanticAI narrator for live play.

**Independent Test**: Using only the OpenAPI docs with a dev credential and the `FakeNarrator`,
create a character, advance through exploration, resolve a combat, reach an end-state; confirm every
number traces to an MCP tool result.

- [x] T009 [P] [US1] Define the `Scene` Pydantic schema (narrative, choices[], effects[] discriminated union) in `src/gamebook_web/harness/scene.py` (contracts/scene.md)
- [x] T010 [US1] `NarratorBackend` port (Protocol) + deterministic `FakeNarrator` in `src/gamebook_web/harness/base.py` (ADR-011; Principle IV testability; FR-011)
- [x] T011 [US1] PydanticAI `AnthropicNarrator(NarratorBackend)` Agent — `output_type=Scene`, `MCPToolset` over the engine, `deps_type` for campaign context, model string injected, and **loads the active adventure module as lore (swap boundary #2, FR-019)** — in `src/gamebook_web/harness/agent.py` (ADR-011)
- [x] T012 [US1] Combat subagent via agent delegation (asks the player whether to test luck each round) in `src/gamebook_web/harness/combat_subagent.py` (ADR-001 pattern)
- [x] T013 [US1] Play endpoints `POST /campaigns`, `POST /campaigns/{id}/character`, `POST /campaigns/{id}/turn`, `GET /campaigns/{id}`, `GET /campaigns/{id}/scene` in `src/gamebook_web/api/play.py` (FR-001/003/004)
- [x] T014 [US1] Combat endpoints `POST /campaigns/{id}/combat/round` and `/flee` in `src/gamebook_web/api/combat.py` (FR-005)
- [x] T015 [P] [US1] Test: full play loop via the documented API only (no browser) using the `FakeNarrator`, in `tests/server/test_api_play_loop.py` (SC-001, FR-001/008)
- [x] T016 [US1] Test: resume a living campaign from the exact recorded point (no restart/re-roll/contradiction) via the API, in `tests/server/test_resume.py` (FR-003)

**Checkpoint**: US1 provable — the documented API is playable end to end, numbers engine-authoritative.

---

## Phase 4: User Story 2 — Narrator structurally prevented from inventing numbers (Priority: P1)

**Goal**: The Principle I gate at the harness boundary — a `Scene` with a literal number or impossible
effect is rejected before persistence; accepted scenes carry only engine-produced numbers.

**Independent Test**: Feed the narrator a path producing a `Scene` with a literal stat value or
out-of-range effect; confirm `422 invalid_scene`, never persisted; confirm accepted scenes' numbers
trace to MCP results.

- [x] T017 [US2] `output_validator` raising `ModelRetry` to reject any `Scene` carrying a literal number, in `src/gamebook_web/harness/agent.py` (Principle I, enforced in code; FR-002/007)
- [x] T018 [P] [US2] Test: a `Scene` with a literal stat value or out-of-range effect is rejected (`422 invalid_scene`) and never persisted; all accepted numbers trace to MCP results, in `tests/server/test_scene_numbers.py` (SC-002, SC-003, FR-007)
- [x] T019 [P] [US2] Test: `Scene.effects[]` types are in lockstep with the MCP tool contract (`docs/CONTRACTS.md` §6) — adding an effect type without a contract update fails, in `tests/server/test_scene_effects_contract.py` (Principle III)

**Checkpoint**: US2 — the numbers-never-in-prose gate is enforced structurally and tested.

---

## Phase 5: User Story 3 — Web backend depends only on contracts (Priority: P2)

**Goal**: The web layer lives behind interfaces; the `FakeNarrator` drives the loop with no LLM.

**Independent Test**: Run the plugability audit; confirm no web module imports concrete storage or
engine internals, and the `FakeNarrator` drives the full loop deterministically.

- [x] T020 [P] [US3] Confirm/extend the plugability audit covers `src/gamebook_web` — depends on the MCP/HTTP API contracts only, no concrete storage or engine-internal imports (Principle IV, merge gate; SC-004)

**Checkpoint**: US3 — architecture preserved; the seam is ready for `004`/`005`.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T021 [P] Finalize `docs/CONTRACTS.md` (HTTP API §, `Scene` §) and update `README`/`quickstart` for the backend MVP (freeze the OpenAPI contract so `005` can build against it)
- [x] T022 Run the full suite + plugability audit gate green, then the SDD review pipeline (`/sdd-qa` + `/sdd-security` → `/sdd-tech`) before merge (constitution Development Workflow)

---

## Dependencies & Execution Order

- **Setup (Phase 1)**: T001; T002, T003 parallel.
- **Foundational (Phase 2)**: depends on Setup — **blocks all user stories**.
- **User Stories (Phases 3–5)**: depend on Foundational; US1 (MVP) first; US2 (numbers gate) and US3
  (plugability) run alongside/after US1.
- **Polish (Phase 6)**: depends on US1/US2 being complete; T021 freezes the OpenAPI contract for `005`.

### Within US1
`Scene` (T009) → port/agent (T010–T012) → endpoints (T013–T014) → tests (T015–T016); T015 can run
alongside once the agent + endpoints exist.

### Parallel opportunities
- Setup: T002, T003 parallel.
- Foundational: T007 (audit) parallel; T004/T005/T006 touch different files.
- US1: T009, T015 parallel; US2: T018, T019 parallel; US3: T020 parallel; Polish: T021 parallel.

## Implementation Strategy

### MVP first (User Story 1 only, with the FakeNarrator)
1. Phase 1 Setup → 2. Phase 2 Foundational → 3. Phase 3 US1 → **stop & validate** the full play loop
through the documented API with engine-authoritative numbers (no browser, no LLM) → demo the API.

### Incremental delivery
Foundational → US1 (playable documented API) → US2 (numbers gate) → US3 (plugability) → Polish.
`004` then adds real auth/accounts/hardening/observability; `005` builds the SPA against the frozen
OpenAPI contract — both consume this feature's API without reworking the play loop.

## Notes
- The engine (`src/gamebook/`) stays behavior-unchanged; the harness consumes it via `MCPToolset`.
- Every state change still flows through MCP — the harness never invents numbers (Principle I,
  enforced by T017 + T018).
- `auth/` is a DEV STUB now; `004` swaps in real OIDC. Keep the seam clean so the play loop is
  untouched by that swap.
- No `frontend/` here — `005-professional-spa` consumes the documented API; freeze the OpenAPI
  contract in T021 so `005` can develop against it in parallel.
- Keep the plugability audit and full suite green at every checkpoint (constitution gate, T007/T022).
