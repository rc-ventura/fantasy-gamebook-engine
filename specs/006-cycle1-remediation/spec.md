# Feature Specification: Cycle-1 Remediation

**Feature Branch**: `006-cycle1-remediation`

**Created**: 2026-06-28

**Status**: Draft

**Epic**: `001-web-platform-migration` — remediation slice addressing the SDD final
review cycle-1 findings. Depends on `003-web-backend-mvp` and `005-professional-spa`
(both merged to `dev` with the findings documented in
`reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`).

**Input**: The SDD final review (cycle-1, 20260628-0752) returned **BLOCKED** with 2
CRITICAL, 5 HIGH, 5 MEDIUM, and 3 LOW/GOVERNANCE findings. The architectural decisions
are recorded as ADRs 017–020 (created in the same change as this spec). This spec
covers the **implementation work** that follows from those decisions plus the
non-architectural fixes. Session-lease enforcement (FR-025) is **deferred to slice
004** per the cycle-1 dispatch.

## Overview

Close the cycle-1 findings so the web backend + SPA are **live-mode functional and
safe to deploy behind a single-campaign dev constraint**. The two CRITICAL findings
(engine shared across campaigns; no production guard on dev auth) and the contract
drift between backend and frontend (HIGH) are the blockers — without them the SPA is
mock-only and any deployment leaks cross-account data. The MEDIUM findings
(hardcoded victory flag, dropped `name`, missing endpoints, security logging, vite
pin) are included to leave the slice in a clean state. LOW and GOVERNANCE findings
(dev-token mismatch, CORS narrowing, allowlist for fabricated-number detection, ADR
renumbering) are folded in where the touch is small; the allowlist and ADR
renumbering are already designed in ADR-019 and ADR-020.

The scope is deliberately bounded: **no new features**, only fixes and the
multi-tenant engine refactor (ADR-018). Real OIDC, session leases, observability, and
accounts remain in `004-accounts-hardening-obs`.

## SDD Cycle-1 Findings Summary

The review report (`reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`)
returned **BLOCKED** with two **CRITICAL**, five **HIGH**, five **MEDIUM**, and three
LOW/GOVERNANCE findings. The headline verdict: *the architecture is fundamentally sound
in principle but critically broken in execution*. The engine-layer swap boundaries and
the "numbers never in prose" principle are intact; the web backend, however, was built
as a single-campaign facade and the frontend was developed against mock fixtures only.

### QA findings (selected)

- **Contract drift**: `TurnResponse`, `CombatRoundResponse`, `FleeCombatResponse`, and
the campaign identifier (`campaign_id` vs `id`) diverged between the FastAPI backend and
the SPA. The SPA is mock-only in live mode; `res.campaign` is `undefined`.
- **No live integration tests**: all frontend tests (including Playwright) run with
`VITE_USE_MOCK=true`; zero tests exercise the SPA against the real backend.
- **Multi-campaign isolation missing**: the MCP toolset is booted once with a single
`GAMEBOOK_CAMPAIGN_ID`, so every campaign shares the same character/world/events.
- **Coverage caveats**: the QA subagent could not execute `uv run pytest` or `npm test`
because the `exec` tool was denied in subagent context; coverage estimates are based on
static analysis of test files vs. source files.

### Security findings (selected)

- **CRITICAL A01**: single shared engine toolset = total cross-account data leakage.
The `campaign_id` path parameter is checked only against the in-memory
`CampaignRegistry`; the engine state itself is unpartitioned.
- **CRITICAL A07**: dev auth stub uses a hardcoded static token (`dev-token`) with no
expiration, no rotation, and no per-account identity. There is no guard preventing
production deployment with `GAMEBOOK_DEV_MODE=1`.
- **HIGH**: `/docs`, `/redoc`, `/openapi.json` are unconditionally enabled; no
production guard.
- **HIGH**: FR-025 (single active session per campaign) is not enforced in the
backend, even though the frontend calls session lease endpoints that do not exist.
- **MEDIUM**: in-memory `CampaignRegistry` loses all campaign state on restart; no
production guard.
- **LOW**: `_RESULT_KEYS` denylist for fabricated-number detection is bypassable; vite
version is not pinned to the CVE-2025-30208 patch.

### Governance findings

- Duplicate ADR numbers: `ADR-014` is shared by the Postgres sync/async bridge and the
pydantic-ai MCPToolset pattern; two "moved" stubs remain in `docs/adrs/`. The
`CLAUDE.md` table perpetuates the ambiguity. This is addressed by ADR-020.

## Architectural Decisions (ADRs created in this cycle)

| ADR | Decision | Finding addressed |
|---|---|---|
| [ADR-017](../../docs/adrs/ADR-017-api-frontend-contract-canonical-shape.md) | Backend Pydantic models are canonical; frontend TS types conform | HIGH Bugs #1–4, #6 |
| [ADR-018](../../docs/adrs/ADR-018-multi-tenant-engine-per-call-campaign-id.md) | Every MCP tool gains `campaign_id`; `build_server` takes a `storage_factory` | CRITICAL A01, Bug #5, SC-005 |
| [ADR-019](../../docs/adrs/ADR-019-allowlist-for-fabricated-number-detection.md) | Allowlist of legal param keys per effect type replaces the denylist | LOW `_RESULT_KEYS` |
| [ADR-020](../../docs/adrs/ADR-020-resolve-duplicate-adr-numbering.md) | Renumber colliding ADR-014 (pydantic-ai) → ADR-021; delete "moved" stubs | GOVERNANCE |

The cycle-1 findings require four architectural decisions, recorded as ADRs 017–020.
They are the blueprint for the implementation work in this spec.

### ADR-017 — Backend-canonical API/frontend contract shape

The backend Pydantic models are the single source of truth. The frontend TypeScript
types are adjusted to match them, and the SPA assembles `CampaignState` from the
granular fields (`scene`, `character`, `world`, `effects_applied`, `outcome`,
`final_result`, `campaign_ended`, etc.) rather than expecting an aggregated `campaign`
object. The OpenAPI schema at `/openapi.json` becomes the frozen contract. This was
chosen because it avoids forcing the backend to re-read full campaign state after
every turn/combat call, keeps the externally-usable API surface clean, and minimizes
backend churn.

| Response type | Backend shape (canonical) |
|---|---|
| `TurnResponse` | `{ scene, character?, world?, effects_applied }` |
| `CombatRoundResponse` | `{ outcome, final_result?, character?, campaign_ended }` |
| `FleeCombatResponse` | `{ result, character?, campaign_ended }` |
| Campaign identifier | `campaign_id` everywhere |
| `CampaignSummary` | `{ campaign_id, status, name?, created_at?, updated_at? }` |

### ADR-018 — Multi-tenant engine via per-call `campaign_id`

Multi-tenancy is implemented at the **MCP server layer**, not by rewriting the
`StorageBackend` Protocol. Every MCP tool gains `campaign_id: str` as its first
parameter; `build_server` receives a `storage_factory: Callable[[str], StorageBackend]`
that returns a cached-or-new backend scoped to the campaign. The web layer passes
`campaign_id` on every `call_engine(...)` invocation. This preserves Principle II
(interface stability) and swap boundary #1, keeps one engine subprocess for all
campaigns, and makes the campaign dimension explicit in the contract.

Rejected alternatives:
- **Subprocess per campaign**: too heavy for 1,000 concurrent campaigns (memory,
startup latency) and hides the campaign dimension from the contract.
- **Multi-tenant `StorageBackend`**: would rewrite every storage method and every test,
violating the spirit of swap boundary #1.

### ADR-019 — Allowlist for fabricated-number detection

The `_RESULT_KEYS` denylist in `agent.py` is replaced by an allowlist of legal param
keys per `EffectType`. Unknown keys in `effect.params` are rejected with `ModelRetry`.
The prose regex is extended to catch patterns like "lost 5 points", "took 3 damage",
"N hp". This makes the "numbers never in prose" gate structural instead of heuristic
with minimal code churn. A future hardening slice may replace `params: dict[str, Any]`
with a discriminated union of typed Pydantic models (ADR-019 option 3), which is out of
scope here.

### ADR-020 — Resolve duplicate ADR numbering

`ADR-014-postgres-storage-sync-async-bridge.md` keeps number 014. The pydantic-ai
MCPToolset ADR is renumbered from 014 to **021** and renamed. The two "moved" stubs are
deleted. The `CLAUDE.md` ADR table is corrected to list each ADR exactly once.

## Implementation Notes

The following notes are derived from the SDD review and constrain how the spec is
implemented.

1. **Web backend must not read `GAMEBOOK_CAMPAIGN_ID` at startup.** The web path boots
   one engine subprocess that serves any campaign via `campaign_id` per call. The
   Phase-1 terminal harness may still use `GAMEBOOK_CAMPAIGN_ID` to pick a default
   campaign for the `main()` composition root.
2. **Test fixtures must provide a per-campaign storage factory.** In-memory tests use a
   factory that returns a fresh `InMemoryStorage` per `campaign_id`. Existing tests
   pass `campaign_id="dev-campaign"` or a fixture-provided id.
3. **Frontend state assembly belongs to `useGame`.** The backend returns granular
   fields; the SPA composes `CampaignState`. `setCampaign(res.campaign)` is removed.
4. **Session lease endpoints are gated, not implemented.** `useGame.acquireSession`,
   `takeoverSession`, and `releaseSession` are wrapped in
   `import.meta.env.VITE_SESSION_LEASE === 'true'`. Real lease enforcement is deferred to
   slice 004, so the default live-mode build does not 404 on missing endpoints.
5. **Production guards are fail-fast.** If `ENV=production` and `GAMEBOOK_DEV_MODE=1`,
   the lifespan raises `RuntimeError`. If `ENV=production`, the FastAPI app is built
   with `docs_url=None, redoc_url=None, openapi_url=None`.
6. **Dev-token alignment.** `.env.local.example` and `AuthPage.tsx` fallback must both
   be `dev-token` to match the backend `DEV_TOKEN` constant.
7. **Security event logging.** Auth failures in `dev_auth.py` log the path and reason at
   `WARNING` before raising the HTTP exception.
8. **Vite pin.** `frontend/package.json` must require `vite >= 5.4.12` to ensure the
   CVE-2025-30208 patch is present; `npm install` refreshes the lockfile.
9. **Supply-chain risk surface.** `pydantic-ai` is pinned to `>=0.0.15` in
   `pyproject.toml`; the review notes that 0.0.x pre-1.0 packages carry rapid API churn
   and limited audit history. This is a known risk to monitor; a future hardening slice
   should move to a stable 1.x release once available.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The SPA plays against the live backend (Priority: P1)

A player opens the SPA in live mode (not mock), signs in with the dev token, starts a
campaign, creates a character, takes a turn, resolves a combat round, and reaches an
end-state — and every response field the SPA reads is populated and matches the
backend's OpenAPI schema. No `undefined` campaign, no 404 on session endpoints (gated
out), no field-name mismatch.

**Why this priority**: This is the entire point of the remediation — the SPA is
currently mock-only because of contract drift. Without this, slices 003 and 005
cannot be used together, which is the product.

**Independent Test**: Start the FastAPI backend and the Vite dev server with
`VITE_USE_MOCK=false`. Drive the full play loop through the browser (or a Playwright
test against the live backend): create campaign → create character → take 2 turns →
start combat → resolve a round → flee → end. Confirm every response renders without
`undefined` and the character sheet reflects engine-rolled values.

**Acceptance Scenarios**:

1. **Given** the backend running and the SPA in live mode, **When** the player creates
   a campaign, **Then** `createCampaign` returns `{ campaign_id, status, name }` and
   the SPA stores it under `campaign_id` (not `id`).
2. **Given** a campaign exists, **When** the player takes a turn, **Then** the
   `TurnResponse` carries `{ scene, character, world, effects_applied }` and the SPA
   assembles `CampaignState` from those fields without reading `res.campaign`.
3. **Given** an active combat, **When** the player resolves a round, **Then** the
   `CombatRoundResponse` carries `{ outcome, final_result, character, campaign_ended }`
   and the SPA renders the round from `outcome` (not `res.round`).
4. **Given** two campaigns A and B owned by the same account, **When** the player
   creates a character in A then reads B's character, **Then** B has no character
   (engine state is isolated per campaign — ADR-018).
5. **Given** the backend boots with `ENV=production` and `GAMEBOOK_DEV_MODE=1`,
   **Then** the server refuses to start with a clear error.

### User Story 2 - The engine serves multiple campaigns in one process (Priority: P1)

A single FastAPI process serves multiple campaigns simultaneously. Each campaign has
its own character, world, events, and combat state. A tool call for campaign B cannot
touch campaign A's state.

**Why this priority**: This is the CRITICAL security finding (A01). Without
per-campaign isolation, the backend is a cross-account data leak.

**Independent Test**: Using the documented API with the `FakeNarrator`, create two
campaigns, create a character in each, take a turn in each, and assert each
campaign's `GET /campaigns/{id}` returns only its own state. Run the existing
`test_api_play_loop.py` against a two-campaign fixture and confirm no cross-talk.

**Acceptance Scenarios**:

1. **Given** two campaigns in one process, **When** a character is created in
   campaign A, **Then** `GET /campaigns/B/character` returns 404 (no character) and
   `GET /campaigns/A/character` returns A's character.
2. **Given** the engine subprocess is started once, **When** 100 campaigns are
   created, **Then** the process does not spawn 100 subprocesses (one process, one
   `storage_factory`, per-campaign backends cached).
3. **Given** the `storage_factory` cache, **When** a campaign is idle, **Then** its
   backend can be evicted and re-created on next access without data loss (state is
   durable in Postgres/JSON, not in the cache).

### User Story 3 - Production guards prevent insecure deployment (Priority: P2)

An operator who misconfigures the server (dev auth in production, docs enabled in
production) gets a fail-fast error at boot, not a silently insecure deployment.

**Why this priority**: The dev auth stub is correct for dev but has no guard against
production misconfiguration. This is defense-in-depth, not a new feature.

**Independent Test**: Set `ENV=production` and `GAMEBOOK_DEV_MODE=1` and assert the
server raises at startup. Set `ENV=production` and assert `/docs` returns 404.

**Acceptance Scenarios**:

1. **Given** `ENV=production` and `GAMEBOOK_DEV_MODE=1`, **When** the server boots,
   **Then** it raises `RuntimeError` with a message naming both env vars.
2. **Given** `ENV=production`, **When** a client requests `/docs`, **Then** the
   response is 404 (docs disabled).
3. **Given** a 401 auth failure, **When** the response is logged, **Then** the log
   line includes the path and reason (security event logging).

## Functional Requirements

### FR-001 (ADR-018) Multi-tenant engine via per-call campaign_id
Every MCP tool in `src/gamebook/mcp/server.py` gains a `campaign_id: str` first
parameter. `build_server` takes a `storage_factory: Callable[[str], StorageBackend]`
instead of a single `storage` instance. The factory caches per-campaign backends.

### FR-002 (ADR-018) Web layer passes campaign_id on every engine call
Every `call_engine(toolset, tool_name, ...)` call site in `play.py` and `combat.py`
passes `campaign_id=campaign_id`. `GAMEBOOK_CAMPAIGN_ID` is no longer read by the web
backend lifespan.

### FR-003 (ADR-017) Frontend types conform to backend response shapes
`frontend/src/types/index.ts` is updated: `TurnResponse`, `CombatRoundResponse`,
`FleeCombatResponse`, `CampaignSummary`, `CampaignState` match the backend Pydantic
models. `useGame.applyTurnResponse` / `applyCombatResponse` assemble `CampaignState`
from the granular fields.

### FR-004 (ADR-017) Campaign identifier is `campaign_id` everywhere
The frontend uses `campaign_id` (not `id`) in all types, API calls, and component
props. The backend `CampaignResponse` already uses `campaign_id`.

### FR-005 (MEDIUM) Victory condition moved out of the API layer
The hardcoded `malachar_defeated` check (`play.py:405`) is replaced by an
adventure-module victory-flag configuration consumed by the API layer. Swap boundary
#2 is preserved.

### FR-006 (MEDIUM) `create_campaign` persists the `name`
`CampaignState` gains a `name` field; `registry.create(account_id, name)` stores it;
`CampaignResponse` and `list_campaigns` include it.

### FR-007 (MEDIUM) Missing endpoints gated or removed
The frontend `useGame.acquireSession` call (and `takeoverSession`/`releaseSession`) is
gated behind `VITE_SESSION_LEASE=true` (default off). `GET /me` is either implemented
as a trivial dev stub returning `{ id: DEV_ACCOUNT_ID }` or the frontend call is
removed. Session-lease endpoints are deferred to slice 004.

### FR-008 (CRITICAL) Production guard on dev auth
The app lifespan asserts: if `ENV=production` and `GAMEBOOK_DEV_MODE=1`, raise
`RuntimeError` at boot. If `ENV=production` and dev auth is the active auth impl,
raise.

### FR-009 (HIGH) `/docs`, `/redoc`, `/openapi.json` disabled in production
The FastAPI app is constructed with `docs_url=None, redoc_url=None,
openapi_url=None` when `ENV=production`.

### FR-010 (MEDIUM) Security event logging for auth failures
`dev_auth._unauthenticated` logs the path and reason at WARNING before raising. The
generic exception handler already logs unhandled errors.

### FR-011 (MEDIUM) Pin `vite` to `>=5.4.12`
`frontend/package.json` updates `vite` from `^5.4.1` to `>=5.4.12` to ensure
CVE-2025-30208 patch.

### FR-012 (LOW) Dev-token mismatch fixed
`.env.local.example` uses `VITE_DEV_TOKEN=dev-token`; `AuthPage.tsx` fallback is
`dev-token`; backend `DEV_TOKEN = "dev-token"`. All three align.

### FR-013 (LOW) CORS methods/headers narrowed
`app.py` CORS config changes `allow_methods=["*"]` → `["GET", "POST", "DELETE",
"OPTIONS"]` and `allow_headers=["*"]` → `["Content-Type", "Authorization"]`.

### FR-014 (ADR-019) Allowlist for fabricated-number detection
`agent.py` replaces `_RESULT_KEYS` denylist with `_ALLOWED_EFFECT_PARAMS` allowlist
keyed by `EffectType`. Unknown param keys → `ModelRetry`. Prose regex extended.

### FR-015 (HIGH) Integration test: frontend against live backend
A Playwright test runs the SPA against the live FastAPI backend (not mock mode) for
the full play loop. Added to `frontend/tests/e2e/`.

### FR-016 (ADR-020) ADR renumbering
`ADR-014-pydantic-ai-v2-mcp-toolset-direct-call.md` is renamed to
`ADR-021-pydantic-ai-v2-mcp-toolset-direct-call.md`. The two "moved" stub files are
deleted. `CLAUDE.md` ADR table is corrected. The learning-lesson cross-link is
updated.

### FR-017 (Principle III) CONTRACTS.md §6 updated for campaign_id
The MCP tool contract in `docs/CONTRACTS.md` §6 is updated to show `campaign_id` as
the first parameter of every tool. The HTTP API contract draft is reconciled with
ADR-017's canonical shapes.

## Success Criteria

- **SC-001** (from cycle-1) The SPA plays a full loop against the live backend
  without `undefined` fields or 404s on gated endpoints. Verified by FR-015.
- **SC-002** (from cycle-1) Two campaigns in one process have isolated engine state.
  Verified by a new `test_multi_campaign_isolation.py`.
- **SC-003** (from cycle-1) The server refuses to boot with dev auth in production.
  Verified by a new `test_production_guards.py`.
- **SC-004** (from cycle-1) `/docs` returns 404 in production. Verified by
  `test_production_guards.py`.
- **SC-005** The plugability audit (`tests/qa/test_dependencies.py`,
  `tests/qa/test_isolation.py`) stays green after the ADR-018 refactor.
- **SC-006** The full test suite (`uv run pytest -q`) stays green.
- **SC-007** The frontend test suite (`npm test`) stays green after the type changes.
- **SC-008** ADRs 017–021 are listed exactly once each in `CLAUDE.md` with correct
  numbers.

## Out of Scope

- Real OIDC, accounts, session-lease enforcement, resume-across-devices → slice `004`.
- OpenTelemetry observability → slice `004`.
- OpenAPI codegen for TS types → future hardening slice (ADR-017 notes this).
- Typed discriminated-union Effect params (ADR-019 option 3) → future slice.
- Per-campaign subprocess isolation (ADR-018 option 1) → rejected, see ADR-018.
- Multi-tenant `StorageBackend` interface (ADR-018 option 3) → rejected, see ADR-018.

## Clarifications

### Session 2026-06-28

- Q: Should session-lease endpoints be implemented in this slice? → A: No, deferred to
  `004`. The frontend's `acquireSession` call is gated behind `VITE_SESSION_LEASE=true`
  (default off) so it does not 404 in live mode.
- Q: Backend or frontend canonical for the API contract? → A: Backend canonical
  (ADR-017); frontend TS types conform.
- Q: How is multi-tenancy achieved? → A: Per-call `campaign_id` through the MCP tool
  contract; `build_server` takes a `storage_factory` (ADR-018).
- Q: Scope of action items? → A: CRITICAL + HIGH + MEDIUM; LOW and GOVERNANCE folded
  in where the touch is small.
