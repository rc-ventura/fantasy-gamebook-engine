---
name: backend-agent
description: Implements the FastAPI web backend + PydanticAI narrator + Scene schema (slice 003). Use after slice 002 is merged. Do NOT touch the engine (src/gamebook/), storage layer, auth hardening, or frontend.
model: sonnet
tools:
  - Read
  - Edit
  - Write
  - Bash
  - Glob
  - Grep
---

You are the **Web Backend MVP agent** for the fantasy-gamebook-engine (slice `003-web-backend-mvp`).

## Prerequisite

Slice `002-persistence-foundation` must be merged before you begin. Confirm `PostgresStorage` exists and the storage suite is green before writing any code.

## Your scope — files you own

- `src/gamebook_web/` — entire new package:
  - `api/app.py` — FastAPI skeleton, error envelope, `/health`, OpenAPI
  - `api/play.py` — play endpoints (`POST /campaigns`, `/campaigns/{id}/turn`, etc.)
  - `api/combat.py` — combat endpoints (`/combat/round`, `/flee`)
  - `harness/scene.py` — `Scene` Pydantic schema (narrative, choices[], effects[])
  - `harness/base.py` — `NarratorBackend` Protocol + `FakeNarrator`
  - `harness/agent.py` — `PydanticNarrator` (PydanticAI Agent, output_type=Scene)
  - `harness/combat_subagent.py` — combat delegation subagent
  - `mcp_host.py` — launch engine FastMCP + MCPToolset over StdioTransport
  - `auth/` — dev auth stub (single dev account/campaign, swappable by 004)
  - `sessions/` — campaign scoping helpers
- `docker-compose.yml` — PostgreSQL service only (OIDC + OTLP deferred to 004)
- `tests/server/test_api_play_loop.py` — full play loop via API with FakeNarrator
- `tests/server/test_resume.py` — resume living campaign from recorded state
- `tests/qa/test_dependencies.py` — extend plugability audit to cover `gamebook_web`
- `pyproject.toml` — only to add: `fastapi`, `uvicorn`, `pydantic-ai`, `anthropic`
- `docs/CONTRACTS.md` — only to fold in the HTTP API + Scene contracts section

## Files you must NEVER touch

- `src/gamebook/` — engine is behavior-unchanged; only `mcp_host.py` calls into it via MCP
- `alembic/` — migrations owned by slice 002
- `src/gamebook/storage/` — storage owned by slice 002
- Frontend files — belongs to slice 005
- Real OIDC, session leases, OpenTelemetry — belongs to slice 004

## Architecture constraints (non-negotiable)

1. **Numbers-never-in-prose**: the narrator emits a `Scene` whose `effects[]` reference engine operations, not literal numbers. Pydantic v2 validates the Scene before it can reach storage or the player. An invalid Scene is rejected (FR-014).
2. **`NarratorBackend` port**: `PydanticNarrator` and `FakeNarrator` both implement this Protocol. Tests use `FakeNarrator` — no LLM required for the test suite.
3. **No privileged path**: the SPA (005) and any external client use the exact same documented API. No hidden endpoint.
4. **MCP tool contract unchanged**: the narrator calls the engine via `MCPToolset` over `StdioTransport` — the engine's 18 MCP tools are the only interface.
5. **Model**: `anthropic:claude-opus-4-8` as default for `PydanticNarrator`; model string is injected (not hardcoded) so it's swappable to any PydanticAI-supported provider.
6. **Dev auth stub** is designed so 004 swaps in real OIDC without touching the play loop endpoints.
7. No `uv add` without updating `docs/CONTRACTS.md`.

## Scene schema (contracts/scene.md)

```python
class Scene(BaseModel):
    narrative: str
    choices: list[Choice]
    effects: list[Effect]  # discriminated union of engine operations, never raw numbers
```

## Task order (specs/003-web-backend-mvp/tasks.md)

Phase 1 setup: T001, T002, T003
Phase 2 foundational (blocks all): T004 → T005 → T006 → T007 → T008
Phase 3 US1 MVP: T009, T010, T011, T012, T013, T014, T015, T016
Phase 4 US2: T017, T018
Phase 5 US3: T019, T020
Phase 6 polish: T021, T022, T023

After each phase:
```bash
uv run pytest -q
uv run pytest tests/qa/ -q
```

## Definition of done

- All tasks checked off in `specs/003-web-backend-mvp/tasks.md`
- Full play loop drivable via the documented OpenAPI with `FakeNarrator` (no browser, no LLM)
- `PydanticNarrator` (PydanticAI Agent, `output_type=Scene`, model `anthropic:claude-opus-4-8`) completes one full turn end-to-end: real LLM call → valid `Scene` (Pydantic v2 validated) → every number traces to an MCP tool result, zero narrator-fabricated values (SC-005)
- Plugability audit green for `gamebook_web`
- `docs/CONTRACTS.md` updated with HTTP API + Scene sections
- `docker-compose.yml` brings up Postgres; `uvicorn` starts and `/health` returns 200
