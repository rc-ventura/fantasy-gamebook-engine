# Quickstart — Validating the Web Platform Migration

Feature: Web Platform Migration · Date: 2026-06-26

This is a **validation/run guide** proving the feature works end to end. It references the contracts
(`contracts/http-api.md`, `contracts/scene.md`) and data model rather than restating them.
Implementation detail belongs in `tasks.md` / the implementation phase, not here.

## Prerequisites
- `uv` environment for the engine + backend (`uv run ...`), Python 3.12.
- A running PostgreSQL instance and `DATABASE_URL`.
- An OIDC auth service reachable, plus client config (issuer, audience, JWKS URL).
- `ANTHROPIC_API_KEY` for the narrator (`claude-opus-4-8`).
- Node toolchain for the `frontend/` SPA.
- OTLP endpoint for telemetry (optional locally).

## The engine still passes in isolation (Principles I, IV)
The engine must remain green and deterministic — Phase 2 changes nothing here:
```bash
uv run pytest tests/engine -q                                   # pure rules, seeded RNG, in-memory
uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q   # plugability gate
```
Expected: all green; no module reaches past an interface.

## Swap boundary #1 — PostgresStorage behind the same interface (Principle II/V)
Prove the consumer (mcp/combat) works against the new backend with no engine change:
```bash
uv run pytest tests/server -q          # storage + MCP suite, now incl. PostgresStorage
```
Expected: the storage contract suite passes for `JSONStorage`, in-memory, **and** `PostgresStorage`
(ADR-009 style — through the consumer). Induce a mid-write failure in the Postgres suite and confirm
no partially-applied save (SC-004).

## Backend up — API + MCP host + narrator
```bash
uv run uvicorn gamebook_web.api:app   # serves the HTTP API (OpenAPI at /docs)
```
- Visit `/docs` → every operation in `contracts/http-api.md` is present and documented (FR-016).

## End-to-end play loop (FR-001–006, FR-025)
With a valid bearer token:
```bash
# 1. Identity
GET  /me                                  # account created from JWT sub

# 2. Start a campaign + character (engine rolls the stats, not the client)
POST /campaigns                           # → campaign id
POST /campaigns/{id}/session              # acquire the session lease (FR-025)
POST /campaigns/{id}/character            # engine-rolled skill/stamina/luck

# 3. Take turns — each returns a validated Scene; numbers come from the engine
POST /campaigns/{id}/turn  {choice:"1"}   # narrator emits Scene; effects applied via MCP

# 4. A fight resolves through the engine
POST /campaigns/{id}/turn                 # narrator delegates to the combat subagent
#    (or stepwise) POST /campaigns/{id}/combat/round {test_luck:true}

# 5. Reach an end-state
#    death or victory → campaign 'ended', ArchiveRecord written; further turns → 409 run_ended
```
**Audit (SC-003)**: every number shown traces to an MCP tool result — no value originates in the
narrator or UI. Feed the narrator a `Scene` with a literal stat value and confirm it is rejected
`422 invalid_scene` and never persisted (FR-014).

## Resume across devices (FR-003, FR-011, SC-002)
```bash
DELETE /campaigns/{id}/session            # release on device A
# On device B with the same account:
POST   /campaigns/{id}/session            # acquire lease
GET    /campaigns/{id}                    # resumes exact recorded point — stats/inventory/events intact
```

## Single active session (FR-025)
Open the same campaign in two clients: the second is read-only (writes → `409 not_session_holder`)
until `POST /campaigns/{id}/session/takeover`, which demotes the first. Confirm no corruption.

## Identity, isolation, auth-down (FR-009, FR-010, FR-024)
- Call any campaign route for a campaign owned by another account → `403/404`.
- Call any route without a token → `401`.
- Stop the IdP: already-signed-in players continue read-only until token expiry; new sign-ins fail
  with a clear `503 auth_unavailable` (graceful degradation).

## Privacy (research §8)
```bash
GET    /me/export                         # returns this account's game data, portable
DELETE /me                                # cascades: campaigns + character/world/events/combat/archive
```

## Observability (FR-022/023, SC-009)
Trigger a representative error and a slow turn; confirm health, error rate, and latency are visible
in the telemetry backend and that a trace locates the failing turn — without the player seeing a
corrupted state.

## Frontend
```bash
cd frontend && npm install && npm run dev
```
Play a full opening → exploration → combat → end-state in the browser; confirm the UI renders only
real engine values (FR-021) and the play loop matches the API contract.

## Done when
- Engine + plugability gates green; PostgresStorage passes the storage contract suite.
- Full play loop works via the API and the SPA; all numbers are engine-authoritative (SC-003).
- Accounts/auth/isolation, single-active-session, resume, export/erasure, and telemetry behave per
  the requirements above.
