# Implementation Plan: Web Platform Migration

**Branch**: `001-web-platform-migration` | **Date**: 2026-06-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-web-platform-migration/spec.md`

## Summary

Take the existing, green solo-play gamebook engine (rules / domain / storage / combat / mcp) and
make it a production-ready web product, **without changing the engine's behavior or its tool
contract**. Phase 2 exercises the project's three swap boundaries at once: swap `JSONStorage` →
`PostgresStorage` (behind the existing `StorageBackend` interface), swap the Claude Code terminal
harness → a new agent-based ("deep agents") web narrator that emits a Pydantic-validated `Scene`,
and put a professional web UI in front of it — all consuming the **same MCP tool contract**. A
dedicated authentication service provides identity; the engine is exposed as a documented,
authenticated HTTP API that the UI is simply one client of. The defining rule is preserved end to
end: the narrator never invents numbers; every roll/luck test/combat/state change goes through MCP.

## Technical Context

**Language/Version**: Python 3.12 (existing engine + new backend services); TypeScript for the
web frontend.

**Primary Dependencies**:
- *Existing, unchanged*: `fastmcp` (MCP server, stdio), `pydantic` v2 (domain + validation), `uv`.
- *New backend*: `fastapi` + `uvicorn` (HTTP API + MCP host process), `sqlalchemy` 2.x + `asyncpg`
  (Postgres access behind `StorageBackend`), `alembic` (schema migrations), `pydantic-ai`
  (the new narrator harness — model-agnostic, see ADR-011) with the `anthropic` SDK as the default
  provider (`claude-opus-4-8`), `opentelemetry-*` (traces/metrics/logs).
- *Auth*: a dedicated, separately-deployable OIDC provider (decision in research.md).
- *Frontend*: a single-page app (React + Vite + TypeScript; decision in research.md).

**Storage**: PostgreSQL via a new `PostgresStorage` implementation of the existing
`StorageBackend` interface. `JSONStorage` and the in-memory test backend remain for dev/test.

**Testing**: `pytest` (engine + new backend integration/contract tests; the existing plugability
audit stays a gate); `vitest` + Playwright for the frontend.

**Target Platform**: Linux server, containerized (engine/API/harness as one or more services,
Postgres, auth service, observability backend); modern web browsers for the UI.

**Project Type**: web (backend services + separate frontend) — see Project Structure below.

**Performance Goals**: 95% of player turns reflected in the UI within 2 s under normal load
(SC-006); sustain ≥ 1,000 concurrent active campaigns (SC-005).

**Constraints**: numbers-never-in-prose (Principle I); **single active play session per campaign**
(FR-025, clarified); narrator↔engine exchanges schema-validated before persistence (FR-014);
atomic, non-corrupting writes unconditionally (Principle V) — independent of the best-effort
availability target (clarified); UI shows only real engine state (FR-021).

**Scale/Scope**: initial target ≥ 1,000 concurrent campaigns; one campaign = one account; no
real-time multiplayer.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0:

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| **I. Numbers Never in Prose** | PASS | The new harness still routes every roll/luck/combat/state change through MCP tools; the `Scene` it emits carries `effects[]` that are *applied by the engine*, never narrated numbers. UI renders only engine state. |
| **II. Dependency on Interfaces Only** | PASS | This feature *is* the swap-boundary proof: `PostgresStorage` sits behind `StorageBackend`; the new harness and UI depend only on the MCP tool contract and the HTTP API contract; the in-memory backend keeps working for tests. No module imports a concrete impl. |
| **III. CONTRACTS.md is the Single Source of Truth** | ACTION | New cross-surface contracts (the HTTP API, the `Scene` schema, the `PostgresStorage` mapping) MUST be folded into `docs/CONTRACTS.md` as they are designed (`contracts/` here drafts them; merging is a tracked task). No engine tool-contract change is permitted without a CONTRACTS.md edit in the same change. |
| **IV. Determinism and Isolated Testing** | PASS | `rules`/`combat` stay pure and seed-deterministic; the plugability audit (`tests/qa/test_dependencies.py`, `test_isolation.py`) remains a merge gate and is extended to cover the new modules. New web/harness layers get their own integration tests but never leak into the pure core. |
| **V. Domain Invariants and Atomic Persistence** | PASS | Invariants stay in `domain`; `PostgresStorage` writes inside transactions (atomic, all-or-nothing) — the relational equivalent of temp-file+rename — and round-trips the domain schema. Single-active-session (FR-025) protects against concurrent corruption. |

**Verdict**: No violations requiring Complexity Tracking justification. The only obligation is the
Principle III action item — contracts drafted here must be merged into `docs/CONTRACTS.md`.

## Project Structure

### Documentation (this feature)

```text
specs/001-web-platform-migration/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 output — technology decisions
├── data-model.md        # Phase 1 output — entities + Postgres mapping + Scene
├── quickstart.md        # Phase 1 output — runnable validation guide
├── contracts/           # Phase 1 output — HTTP API + Scene schema drafts
│   ├── http-api.md
│   └── scene.md
├── checklists/
│   └── requirements.md  # from /speckit-specify
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

The repo is a single-project Python engine today. Phase 2 adds a backend service layer around the
engine and a separate frontend, keeping the existing `src/gamebook/` package untouched in behavior.

```text
src/gamebook/                 # EXISTING engine — behavior unchanged
├── domain/                   # data contracts + invariants (Principle V)
├── rules/                    # pure rules, injected RNG (Principle IV)
├── combat/                   # combat lifecycle
├── storage/                  # StorageBackend interface + JSONStorage + in-memory
│   └── postgres.py           # NEW: PostgresStorage impl (swap boundary #1)
└── mcp/                      # FastMCP server (stdio) — tool contract unchanged

src/gamebook_web/             # NEW backend service layer (consumes engine via MCP)
├── api/                      # FastAPI app: HTTP API (the documented engine API)
├── harness/                  # NEW agent-based narrator ("deep agents"); emits Scene
│   ├── scene.py              # Pydantic Scene schema (validated narrator output)
│   ├── agent.py              # planner loop over MCP tools (claude-opus-4-8)
│   └── combat_subagent.py    # delegated combat subagent (maps to existing sub-agent)
├── auth/                     # integration with the separate auth service (OIDC verify)
├── sessions/                 # single-active-session enforcement (FR-025)
└── observability/            # OpenTelemetry setup (traces/metrics/logs)

frontend/                     # NEW professional SPA (separate UI)
├── src/
│   ├── components/           # scene view, choices, character sheet, map, combat
│   ├── pages/
│   └── api/                  # typed client of the HTTP API contract
└── tests/

tests/
├── engine/                   # EXISTING pure-rules tests (seeded, in-memory)
├── server/                   # storage + MCP — extended with PostgresStorage suite
└── qa/                       # plugability audit + isolation + e2e (merge gate)
```

**Structure Decision**: Keep `src/gamebook/` as the untouched engine (only adding
`storage/postgres.py` behind the existing interface). Add a new `src/gamebook_web/` package for the
web/service concerns (API, harness, auth, sessions, observability) so the engine never depends on
the web layer — the dependency arrow points web → MCP/engine-interfaces only (Principle II). The
frontend is a wholly separate `frontend/` project consuming the HTTP API.

## Complexity Tracking

> No Constitution Check violations — this section is intentionally empty.

The migration is large but introduces no principle violation that needs justifying. The one tracked
obligation is documentation, not complexity: fold the `contracts/` drafts (HTTP API, `Scene`,
`PostgresStorage` mapping) into `docs/CONTRACTS.md` (Principle III).
