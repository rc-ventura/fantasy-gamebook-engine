# Implementation Plan: Web Backend MVP

**Branch**: `003-web-backend-mvp` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-web-backend-mvp/spec.md` (decomposition slice of
epic `001-web-platform-migration`, depends on `002-persistence-foundation`; the browser SPA is a
separate feature `005-professional-spa`).

## Summary

Put a **playable web backend** in front of the durable engine (from `002`) — **without changing the
engine's behavior or its MCP tool contract**. Add a new agent-based narrator (PydanticAI, behind a
`NarratorBackend` port with a deterministic `FakeNarrator`) that emits a Pydantic-validated `Scene`
whose `effects[]` reference engine operations (so it cannot fabricate numbers — Principle I), and a
FastAPI HTTP API that consumes the engine via `MCPToolset` over the existing FastMCP server. The MVP
proof is the **full play loop driven entirely through the documented OpenAPI API** with the
`FakeNarrator` (no browser, no LLM), plus the real PydanticAI narrator for live play. Use a dev auth
stub scoping play to a single development account/campaign so the API is exercisable end to end. Real
OIDC, accounts, session leases, hardening, and observability are deferred to `004`; the browser UI is
deferred to `005`. Both seams are designed to swap cleanly.

This is the **backend MVP slice** of the epic and the second feature in its dependency chain
(`002` → `003` → `004` // `005`).

## Technical Context

**Language/Version**: Python 3.12 (backend). No frontend in this feature.

**Primary Dependencies**:
- *Existing, unchanged*: `fastmcp` (engine MCP server, stdio), `pydantic` v2, `uv`, and the
  `PostgresStorage` + Alembic stack from `002`.
- *New*: `fastapi` + `uvicorn` (HTTP API + MCP host process), `pydantic-ai` (narrator harness —
  model-agnostic, see ADR-011) with the `anthropic` SDK as the default provider
  (`claude-opus-4-8`).
- *Deferred to `004`*: OIDC provider integration, `opentelemetry-*`.
- *Deferred to `005`*: the React/Vite SPA and its toolchain.

**Storage**: PostgreSQL via `PostgresStorage` from `002` (this feature does not touch storage).

**Testing**: `pytest` (backend integration + the numbers-never-in-prose + invalid-`Scene` + API
play-loop gates); the plugability audit is extended to cover `src/gamebook_web` and remains a merge
gate. The `FakeNarrator` makes the full loop testable without an LLM.

**Target Platform**: Linux server (backend service); dev `docker-compose` for Postgres (OIDC/OTLP
added in `004`).

**Project Type**: web service (backend only).

**Performance Goals**: 95% of turns reflected in an API response within 2 s under normal load (epic
SC-006, single-account slice; full concurrency validation is `004`).

**Constraints**: numbers-never-in-prose (Principle I — enforced by `Scene` schema +
`output_validator`); narrator↔engine exchanges schema-validated before persistence (FR-014); API
responses show only real engine state (FR-012); web layer depends only on the MCP + HTTP API
contracts (Principle II); `Scene.effects[]` types stay in lockstep with the MCP tool contract
(Principle III).

**Scale/Scope**: a single development account/campaign via the dev auth stub (multi-account at scale
is `004`); one playable adventure module.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0:

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| **I. Numbers Never in Prose** | PASS | The narrator routes every roll/luck/combat/state change through MCP tools; the `Scene` carries `effects[]` that are *applied by the engine*, never narrated numbers. An `output_validator` raises `ModelRetry` on any literal number. API responses carry only engine-produced values. |
| **II. Dependency on Interfaces Only** | PASS | `src/gamebook_web` depends only on the MCP tool contract (`MCPToolset`) and the HTTP API contract; it never imports a concrete storage impl or engine internals. The narrator sits behind a `NarratorBackend` port so a `FakeNarrator` can be injected for tests. The in-memory backend still works. |
| **III. CONTRACTS.md is the Single Source of Truth** | ACTION | The HTTP API and `Scene` schema drafts (`contracts/`) MUST be folded into `docs/CONTRACTS.md` as they are implemented. `Scene.effects[]` types MUST stay in lockstep with the MCP tool contract (§6); adding an effect type requires a CONTRACTS.md update. |
| **IV. Determinism and Isolated Testing** | PASS | `rules`/`combat` stay pure and seed-deterministic; the `FakeNarrator` makes the play loop testable without an LLM; the plugability audit is extended to `src/gamebook_web` and remains a merge gate. |
| **V. Domain Invariants and Atomic Persistence** | PASS | Invariants stay in `domain`; persistence is delegated to `PostgresStorage` from `002` (atomic transactions). The `Scene` is a transport/validation type, not a new engine table. |

**Verdict**: No violations requiring Complexity Tracking justification. The only obligation is the
Principle III action item — fold the HTTP API and `Scene` contracts into `docs/CONTRACTS.md`.

## Project Structure

### Documentation (this feature)

```text
specs/003-web-backend-mvp/
├── spec.md
├── plan.md              # This file
├── tasks.md
└── checklists/
    └── requirements.md
```

Shared design artifacts live in the epic and are referenced (not duplicated):

- Narrator + model decision: [../001-web-platform-migration/research.md](../001-web-platform-migration/research.md) §2 (ADR-011)
- HTTP API decision: research.md §4; contract: [../001-web-platform-migration/contracts/http-api.md](../001-web-platform-migration/contracts/http-api.md)
- `Scene` contract: [../001-web-platform-migration/contracts/scene.md](../001-web-platform-migration/contracts/scene.md)
- Data model: [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §C.4 (Scene)
- Validation guide: [../001-web-platform-migration/quickstart.md](../001-web-platform-migration/quickstart.md) (API/backend sections)

### Source Code (repository root)

```text
src/gamebook/                 # EXISTING engine — behavior unchanged (storage from 002)

src/gamebook_web/             # NEW backend service layer (consumes engine via MCP)
├── api/
│   ├── app.py                # FastAPI app: error envelope, /health, OpenAPI
│   ├── play.py               # campaign/character/turn/scene endpoints
│   └── combat.py             # combat round/flee endpoints
├── harness/
│   ├── scene.py              # Pydantic Scene schema (validated narrator output)
│   ├── base.py               # NarratorBackend port + FakeNarrator
│   ├── agent.py              # PydanticAI PydanticNarrator (output_type=Scene, output_validator)
│   └── combat_subagent.py    # delegated combat subagent (ADR-001 pattern)
├── auth/                     # DEV AUTH STUB (replaced by OIDC in 004)
├── sessions/                 # minimal campaign scoping (session lease enforcement deferred to 004)
└── mcp_host.py               # MCPToolset over the engine FastMCP server (StdioTransport)

# NO frontend/ in this feature — that is 005-professional-spa.

tests/
├── server/                   # backend: numbers-never-in-prose + invalid-Scene + API play-loop tests
└── qa/                       # plugability audit extended to src/gamebook_web
```

**Structure Decision**: Keep `src/gamebook/` as the untouched engine. Add `src/gamebook_web/` for the
API + harness, depending only on the MCP tool contract and the HTTP API contract (Principle II). The
`auth/` module is a dev stub now, designed so `004` swaps in real OIDC without touching the play
loop. No `frontend/`, no `observability/` — those are `005` and `004` respectively.

## Complexity Tracking

> No Constitution Check violations — this section is intentionally empty.

The single tracked obligation is documentation, not complexity: fold the HTTP API and `Scene`
contracts into `docs/CONTRACTS.md` (Principle III).
