# Implementation Plan: Accounts, Hardening & Observability

**Branch**: `004-accounts-hardening-obs` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-accounts-hardening-obs/spec.md` (decomposition slice
of epic `001-web-platform-migration`, depends on `002-persistence-foundation` and
`003-web-backend-mvp`; the browser SPA is a separate feature `005-professional-spa`).

## Summary

Take the playable web backend from `003` (running on the durable `PostgresStorage` from `002`, behind
a dev auth stub) and harden it into a production-grade, multi-account, observable service — **without
changing the engine's behavior or its MCP tool contract**. Replace the dev auth stub with real
authentication from a dedicated service: validate JWTs (JWKS, aud/exp), resolve the account from
`sub`, and scope every read/write to that account. Add the Alembic migration for `account`,
`campaign.account_id`, and `session_lease`; enforce a single active play session per campaign via the
lease and gate state-changing routes on it. Add save/resume checkpointing so progress follows a
player across devices, and privacy endpoints (`GET /me`, `GET /me/export`, `DELETE /me`) with
cascading erasure. Harden the atomic-write boundary in `PostgresStorage` for the concurrency and
multi-account setting, prove isolation with no cross-account leakage, degrade gracefully when the
auth service is down, and guard against acting on an ended run while honoring recorded facts on
adventure changes. Instrument the service with OpenTelemetry (traces/metrics/logs via OTLP) plus
per-request traces that locate a failing turn without exposing corrupted state. Add the OIDC
provider and OTLP collector to `docker-compose.yml`.

This is the **accounts, hardening & observability slice** of the epic and the third feature in its
dependency chain (`002` → `003` → `004` // `005`). The shared design artifacts (technology decisions,
data model, contracts) live in the epic and are referenced, not duplicated.

## Technical Context

**Language/Version**: Python 3.12 (backend). No frontend in this feature.

**Primary Dependencies**:
- *Existing, unchanged*: `fastmcp` (engine MCP server, stdio), `pydantic` v2, `uv`.
- *From `002`*: `sqlalchemy` 2.x Core + `asyncpg` + `alembic` (Postgres behind `StorageBackend`).
- *From `003`*: `fastapi` + `uvicorn` (HTTP API + MCP host), `pydantic-ai` + `anthropic` (narrator
  harness, ADR-011) and the documented API + `Scene` + dev auth stub.
- *New (this feature)*: an OIDC client library (JWT/JWKS validation against the dedicated auth
  provider) and `opentelemetry-*` (traces/metrics/logs, OTLP export). Both are recorded in
  `docs/CONTRACTS.md` (constitution: no `uv add` without a CONTRACTS update).
- *Deferred to `005`*: the React/Vite SPA and its toolchain (including sign-up/sign-in UI).

**Storage**: PostgreSQL via `PostgresStorage` from `002`; this feature adds the `account`,
`campaign.account_id`, and `session_lease` migration and hardens the atomic-write boundary for
concurrency. The `StorageBackend` interface is unchanged.

**Testing**: `pytest` (backend integration: auth/account scoping, session lease, resume-across-devices,
concurrency isolation, atomic-writes-under-concurrency, graceful degradation, ended-run guarding,
observability); the plugability audit is confirmed to cover the new `auth/` and `observability/`
modules and remains a merge gate. The `FakeNarrator` from `003` keeps the loop testable without an
LLM.

**Target Platform**: Linux server (backend service); dev `docker-compose` now includes Postgres + the
OIDC provider + the OTLP collector.

**Project Type**: web service (backend only).

**Performance Goals**: the system sustains at least 1,000 concurrent active campaigns without data
loss or cross-account leakage (epic SC-005); 95% of turns reflected within 2 s under normal load
(epic SC-006, now at scale).

**Constraints**: numbers-never-in-prose is unaffected (no narrator change here); atomic,
non-corrupting writes unconditionally under concurrency (Principle V); per-account isolation with no
cross-account leakage (FR-009); the web layer depends only on the MCP + HTTP API contracts and the
auth seam (Principle II); `docs/CONTRACTS.md` is the single source of truth for the new
account/session/privacy/observability contracts (Principle III).

**Scale/Scope**: many concurrent accounts/campaigns (vs. `003`'s single dev account); one playable
adventure module; operator-chosen telemetry backend.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0:

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| **I. Numbers Never in Prose** | PASS | This feature adds no narrator logic; the `Scene` + `output_validator` gate from `003` is unchanged, so numbers stay engine-authoritative. Auth, accounts, sessions, and observability never touch the roll/luck/combat/state path. |
| **II. Dependency on Interfaces Only** | PASS | `src/gamebook_web` continues to depend only on the MCP tool contract and the HTTP API contract; it never imports a concrete storage impl or engine internals. The OIDC integration sits behind the same auth seam `003` stubbed, so swapping the stub for real OIDC does not touch the play loop. Observability is added as a new `src/gamebook_web/observability/` module that instruments without coupling to engine internals. The in-memory backend still works for tests. |
| **III. CONTRACTS.md is the Single Source of Truth** | ACTION | The account, session-lease, privacy (`/me`), and observability contracts MUST be folded into `docs/CONTRACTS.md` as they are implemented. The new dependencies (OIDC client lib, `opentelemetry-*`) MUST be recorded in `docs/CONTRACTS.md`. No MCP tool-contract change is permitted. |
| **IV. Determinism and Isolated Testing** | PASS | `rules`/`combat` stay pure and seed-deterministic; the `FakeNarrator` from `003` keeps the play loop testable without an LLM; the plugability audit is extended to the new `auth/` and `observability/` modules and remains a merge gate. |
| **V. Domain Invariants and Atomic Persistence** | PASS | Invariants stay in `domain`; the atomic-write boundary in `PostgresStorage` is hardened to all-or-nothing per state change under the concurrency/multi-account setting (extending `002`'s single-write case); the session lease composes with transactional commits so concurrent edits cannot corrupt state. |

**Verdict**: No violations requiring Complexity Tracking justification. The only obligation is the
Principle III action item — fold the account, session-lease, privacy, and observability contracts
(and the new dependencies) into `docs/CONTRACTS.md`.

## Project Structure

### Documentation (this feature)

```text
specs/004-accounts-hardening-obs/
├── spec.md
├── plan.md              # This file
├── tasks.md
└── checklists/
    └── requirements.md
```

Shared design artifacts live in the epic and are referenced (not duplicated):

- Authentication decision: [../001-web-platform-migration/research.md](../001-web-platform-migration/research.md) §3
- Session-lease decision: research.md §6
- Observability decision: research.md §7
- Privacy/compliance decision: research.md §8
- Data model (account/campaign/session lease, ownership & isolation): [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §B.1/§C.1/§C.2/§C.3/§E
- HTTP API contract (identity & account, session lease, save/resume, errors): [../001-web-platform-migration/contracts/http-api.md](../001-web-platform-migration/contracts/http-api.md)
- Validation guide: [../001-web-platform-migration/quickstart.md](../001-web-platform-migration/quickstart.md) (accounts/hardening/observability sections)

### Source Code (repository root)

```text
src/gamebook/                 # EXISTING engine — behavior unchanged
└── storage/
    └── postgres.py           # PostgresStorage — atomic write boundary HARDENED for concurrency (Principle V)

src/gamebook_web/             # backend service layer from 003 — extended
├── api/
│   ├── app.py                # FastAPI app — unchanged skeleton; lease/auth wiring added
│   ├── play.py               # play endpoints + POST /campaigns/{id}/save checkpoint + resume
│   ├── combat.py             # combat endpoints — now gated on session lease
│   └── account.py            # NEW: GET /me, GET /me/export, DELETE /me (cascade erasure)
├── harness/                  # narrator from 003 — unchanged (Scene + output_validator)
├── auth/                     # REAL OIDC (replaces 003 dev stub): JWT/JWKS validation, sub→account, per-account scoping dependency, graceful degradation
├── sessions/                 # NEW: session-lease enforcement + acquire/takeover/release endpoints
├── observability/            # NEW: OpenTelemetry setup (traces/metrics/logs via OTLP) + per-request traces + play metrics
└── mcp_host.py               # MCPToolset over the engine FastMCP server — unchanged

alembic/versions/             # NEW migration: account, campaign.account_id, session_lease (data-model §B.1/§C.3)

docker-compose.yml            # EXTENDED: add OIDC provider + OTLP collector (Postgres from 003)

tests/
├── server/                   # auth scoping, session lease, resume-across-devices, concurrency isolation, atomic-writes-under-concurrency, degradation, ended-run, observability
└── qa/                       # plugability audit — confirmed green with new auth/ + observability/
```

**Structure Decision**: Keep `src/gamebook/` as the untouched engine (only `storage/postgres.py`'s
atomic boundary is hardened, behind the same interface). Extend `src/gamebook_web/` with real OIDC
in `auth/` (behind the same seam `003` stubbed), session-lease enforcement in `sessions/`,
privacy endpoints in `api/account.py`, and a new `observability/` module — all depending only on the
MCP + HTTP API contracts (Principle II). Add the `account`/`session_lease` migration and the
docker-compose OIDC/OTLP services. No `frontend/` — that is `005-professional-spa`; sign-up/sign-in
UI is `005`'s concern.

## Complexity Tracking

> No Constitution Check violations — this section is intentionally empty.

The single tracked obligation is documentation, not complexity: fold the account, session-lease,
privacy, and observability contracts (and the new dependencies) into `docs/CONTRACTS.md` (Principle
III).
