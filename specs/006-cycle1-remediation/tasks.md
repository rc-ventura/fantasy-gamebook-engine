---
description: "Task list for Cycle-1 Remediation (001 + 002 + 003 + 004 + 005) — closes SDD cycle-1 findings from all five reviews (CRITICAL+HIGH+MEDIUM+LOW+GOVERNANCE)"
---

# Tasks: Cycle-1 Remediation (spec 006)

**Input**: Design documents from `specs/006-cycle1-remediation/` (spec.md, plan.md,
data-model.md, contracts/http-api.md, research.md). Driven by five SDD final reviews:
- `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
- `reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md`
- `reports/sdd-final-review/003-web-backend-mvp/cycle-1-20260628-1010.md`
- `reports/sdd-final-review/004-accounts-hardening-obs/cycle-1-20260628-1043.md`
- `reports/sdd-final-review/005-professional-spa/cycle-1-20260628-1223.md`

**Prerequisites**: spec.md, plan.md; ADRs 017–028; `002-persistence-foundation`,
`003-web-backend-mvp`, `005-professional-spa` merged to `dev`; `feat/004-auth-obs`
implementation absorbed; 002 and 003 remediated in-place on the 006 branch.

**Tests**: Included — test tasks are enumerated per user story and cross-referenced
to success criteria (SC-NNN).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in same phase)
- **[USn]**: User story this task belongs to (US1–US11, mapping to spec.md user stories)

## Path Conventions

Engine: `src/gamebook/`. Web backend: `src/gamebook_web/`. Frontend: `frontend/src/`.
Tests: `tests/{server,qa}/` (backend), `frontend/tests/` (frontend).

---

## Phase 1: Foundational — US2: Multi-tenant engine (CRITICAL, blocks all user stories)

**Goal**: One MCP subprocess serves all campaigns; every MCP tool gains `campaign_id: str`
as first parameter; the web layer passes `campaign_id` on every engine call. Implements
ADR-018 Option A (confirmed 2026-07-01): one subprocess + `storage_factory` + `ScopedMCPToolset`
wrapper. Fixes CRITICAL A01 (cross-account data leakage). **No user story phase may begin
until this phase is green.**

**Independent Test**: `uv run pytest tests/server/test_multi_campaign_isolation.py -v` — two
accounts, two campaigns, assert no cross-talk. `uv run pytest tests/qa/test_dependencies.py
tests/qa/test_isolation.py -q` — plugability audit green.

- [X] T001 [US2] Add `storage_factory: Callable[[str], StorageBackend]` parameter to `build_server` in `src/gamebook/mcp/server.py`; replace the module-level `storage` reference with `storage = storage_factory(campaign_id)` inside each tool body. `CombatService` is also constructed per-campaign via the factory. (ADR-018)
- [X] T002 [US2] Add `campaign_id: str` as the first parameter of all 18 MCP tools in `src/gamebook/mcp/server.py`. Each tool body resolves `storage = storage_factory(campaign_id)` before operating. (ADR-018, FR-001)
- [X] T003 [US2] Update `main()` composition root in `src/gamebook/mcp/server.py`: Phase-2 factory returns `PostgresStorage(database_url, campaign_id)` (cached per `campaign_id`); Phase-1 factory returns `JSONStorage(f"estado/{campaign_id}")`. Remove single-`storage` construction. `GAMEBOOK_CAMPAIGN_ID` env var is only used by the Phase-1 terminal harness `main()`, not the web path. **Cache note**: implement as `dict[str, StorageBackend]` for MVP. Add a code comment: `# TODO(LRU): replace with LRU(max_size=500) before production at scale — unbounded dict is a memory leak with many campaigns`. (ADR-018)
- [X] T004 [P] [US2] Update `tests/server/conftest.py`: inject an in-process `storage_factory` that returns a fresh `InMemoryStorage` per `campaign_id` (not a shared instance). Existing tests pass `campaign_id="dev-campaign"` or a fixture-provided id. (ADR-018, Principle IV)
- [X] T005 [US2] Update every `call_engine(toolset, tool_name, ...)` call site in `src/gamebook_web/api/play.py` to pass `campaign_id=campaign_id`. (`combat.py` was deleted in spec 007 — only `play.py` call sites remain.) (ADR-018, FR-002)
- [X] T006 [US2] Remove `GAMEBOOK_CAMPAIGN_ID` reading from `src/gamebook_web/api/app.py` lifespan and `src/gamebook_web/mcp_host.py` — the web backend uses ONE toolset at startup (no env-var scoping). `engine_toolset_lifespan()` in `app.py` remains; it starts a single subprocess that serves all campaigns via the `campaign_id` parameter in each tool call. (ADR-018, FR-002)
- [X] T006b [US2] Implement `campaign_id` enforcement in `src/gamebook_web/harness/agent.py` using a **scoped toolset wrapper** (prevention) plus a **post-audit** (detection belt-and-suspenders):
  1. **Prevention**: Wrap the `MCPToolset` in `ScopedMCPToolset`; override `arguments["campaign_id"] = current_campaign_id` before every `call_tool(name, arguments)` reaches the MCP server. The LLM cannot pass the wrong `campaign_id`.
  2. **Detection**: `_assert_narrator_campaign(result, campaign_id)` scans `result.all_messages()` after `agent.run()` and raises if any recorded tool call has a different `campaign_id`. This catches any gap in the wrapper. The audit is detection post-facto — if the wrapper fails, tools may have already written to the wrong campaign. The wrapper prevents; the audit is the fallback.
  3. Include `campaign_id` in `_build_prompt` system prompt context as documentation for the LLM. (ADR-018)
- [X] T007 [P] [US2] Update `docs/CONTRACTS.md` §6 (MCP tool contract) to show `campaign_id: str` as first parameter of every tool. Update the HTTP API contract reference to the backend-scoped routes (`/me/game/...`). (FR-017, Principle III)
- [X] T008 [US2] Add `tests/server/test_multi_campaign_isolation.py`: using the API with two different accounts, create a campaign per account, create a character in campaign A, assert campaign B has no character; take a turn in A, assert B's world unchanged. (SC-002, FR-001)
- [X] T009 [P] [US2] Run the plugability audit (`uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q`) and fix any new violations introduced by the `storage_factory` seam. (SC-005, Principle II)

**Checkpoint**: Engine is multi-tenant; one process serves N campaigns with isolated
state; CONTRACTS.md §6 updated; `ScopedMCPToolset` wrapper enforces `campaign_id`;
plugability audit green.

---

## Phase 2: US1 — The SPA plays against the live backend (Priority: P1) 🎯 MVP

**Goal**: Redesign the HTTP API from resource-scoped (`/campaigns/{id}/...`) to
backend-scoped (`/me/game/...`) per D1 (2026-07-01). One active campaign per account;
backend resolves `campaign_id` from `JWT → account → active campaign` — the frontend
never manages `campaign_id`. Frontend types conform to backend Pydantic models; a
live-backend Playwright integration test catches future drift.

**Dependency**: Requires Phase 1 complete (backend routes depend on `campaign_id` being
resolved internally via the multi-tenant engine).

**Independent Test**: Start FastAPI backend + Vite dev server with `VITE_USE_MOCK=false`.
Run `npx playwright test tests/e2e/live-play-loop.spec.ts` — full play loop against the
live backend with no `undefined` fields.

**Backend route mapping (D1):**

| Old route | New route |
|-----------|-----------|
| `POST /campaigns` | `POST /me/game` |
| `GET /campaigns` | _removed → see `GET /me/graveyard`_ |
| `GET /campaigns/{id}` | `GET /me/game` |
| `DELETE /campaigns/{id}` | `DELETE /me/game` |
| `POST /campaigns/{id}/character` | `POST /me/game/character` |
| `GET /campaigns/{id}/character` | `GET /me/game/character` |
| `POST /campaigns/{id}/turn` | `POST /me/game/turn` |
| `GET /campaigns/{id}/scene` | `GET /me/game/scene` |
| `POST /campaigns/{id}/save` | `POST /me/game/save` |
| `POST /campaigns/{id}/session` | `POST /me/game/session` |
| `POST /campaigns/{id}/session/takeover` | `POST /me/game/session/takeover` |
| `DELETE /campaigns/{id}/session` | `DELETE /me/game/session` |
| _(new)_ | `GET /me/graveyard` — ended campaigns |

### Phase 2a: Backend route redesign

- [X] T112 [US1] Rename all route handlers in `src/gamebook_web/api/play.py`: replace `/campaigns` prefix with `/me/game`; remove `campaign_id` from all path parameters. Replace `_campaign_or_404(registry, campaign_id, account)` with `_get_active_campaign(account)` helper (see T113). (ADR-017, D1)
- [X] T113 [US1] Add `_get_active_campaign(account: Account, registry: CampaignRegistry) -> CampaignState` helper in `src/gamebook_web/api/play.py`: looks up the one active campaign for `account.account_id`. When no active campaign exists: raise `404` with `{ "error": { "code": "no_active_campaign", "message": "...", "hint": "POST /me/game to start a new game" } }` — never a generic 404. The SPA intercepts this specific code to route the player to the start screen. The `campaign_id` extracted here is passed to all `call_engine(...)` calls inside each handler. (ADR-017, D1, FR-002)
- [X] T114 [P] [US1] Add `GET /me/graveyard` endpoint in `src/gamebook_web/api/play.py` returning the list of `ended` campaigns for the caller's account. Response: `[{ campaign_id, status, name?, created_at?, ended_at?, ended_reason? }]`. (ADR-017, D1, FR-003)
- [X] T115 [P] [US1] Update `specs/001-web-platform-migration/contracts/http-api.md` to reflect the backend-scoped route table above. Remove old `GET /campaigns`, `GET /campaigns/{id}` etc. Add new `/me/game/...` routes and graveyard endpoint. (ADR-017, Principle III)
- [ ] T116 [US1] Update session-lease routes in `src/gamebook_web/api/sessions.py`: rename `POST /campaigns/{id}/session` → `POST /me/game/session`, `POST /campaigns/{id}/session/takeover` → `POST /me/game/session/takeover`, `DELETE /campaigns/{id}/session` → `DELETE /me/game/session`. (ADR-017, ADR-023, D1)

### Phase 2b: Frontend contract alignment

- [X] T010 [US1] Update `frontend/src/types/index.ts`: `TurnResponse` → `{ scene, character?, world? }` (no `effects_applied` — removed in spec 007); remove `CombatRoundResponse` and `FleeCombatResponse` (combat endpoints deleted in spec 007); remove `CampaignSummary` from primary play-path types (moves to graveyard type); add `GraveyardEntry` interface `{ campaign_id: string, status: 'ended', name?: string, created_at?: string, ended_at?: string, ended_reason?: 'death' | 'victory' }`. (ADR-017, FR-003, FR-004)
- [X] T011 [US1] Refactor `frontend/src/hooks/useGame.ts` to `useGame()` — remove `campaignId` parameter. Remove all references to `campaignId` in the hook body; calls become `getActiveGame()`, `takeTurn(choice)`, `acquireSession()` etc. (no `campaign_id` in any call). `applyTurnResponse` assembles `GameState` from `{ character: res.character, world: res.world, current_scene: res.scene }`. Remove `applyCombatResponse`. (ADR-017, D1, FR-003)
- [X] T012 [US1] Rewrite `frontend/src/api/client.ts`: replace all `/campaigns/${id}/...` endpoints with `/me/game/...` (no `id` parameter). Methods: `createGame()`, `getGame()`, `deleteGame()`, `createCharacter()`, `readCharacter()`, `takeTurn(choice)`, `getScene()`, `saveGame()`, `getGraveyard()`. (ADR-017, D1, FR-004)
- [X] T013 [P] [US1] Update `frontend/src/api/mock.ts` to return the new response shapes under the new route keys. No `effects_applied` in `TurnResponse`; no combat round/flee mock handlers; new `/me/game/...` key names. Mock stays in sync with the canonical contract per ADR-016/ADR-017. (ADR-017)
- [ ] T014 [US1] Add `frontend/tests/e2e/live-play-loop.spec.ts`: Playwright suite against the live FastAPI backend (started in global setup) with `VITE_USE_MOCK=false`. Flow: `POST /me/game` → `POST /me/game/character` → `POST /me/game/turn` × 2 → turn that auto-resolves combat → `GET /me/game/scene` (resume). Asserts no `undefined` fields in any response. (SC-001, FR-015)
- [X] T015 [US1] Run `npm test` and fix any type errors / test failures from the type and route changes. (SC-007)

**Checkpoint**: Backend routes are `/me/game/...`; graveyard endpoint exists;
`_get_active_campaign` returns structured `no_active_campaign` 404; frontend `useGame()`
has no `campaignId` parameter; SPA API client uses new routes; live-backend Playwright
test passes; mock mode still works.

---

## Phase 3: US3 — Production guards prevent insecure deployment (Priority: P2)

**Goal**: Fail-fast on insecure production config; disable API docs in production;
log auth failures with path + reason. Fixes CRITICAL dev-auth production guard and
HIGH docs/logging findings.

**Dependency**: Can run in parallel with other phases after Phase 1 is complete
(different files: `app.py`, `dev_auth.py`).

**Independent Test**: `ENV=production GAMEBOOK_DEV_MODE=1 uvicorn ...` — assert
`RuntimeError` at boot. `ENV=production` + `GET /docs` — assert `404`.

- [X] T016 [US3] Add startup guard in `src/gamebook_web/api/app.py` lifespan: if `ENV=production` and `GAMEBOOK_DEV_MODE=1`, raise `RuntimeError` with a clear message naming both env vars. (FR-008)
- [X] T017 [P] [US3] Disable `/docs`, `/redoc`, `/openapi.json` when `ENV=production`: construct FastAPI with `docs_url=None if os.getenv("ENV")=="production" else "/docs"` (same for redoc, openapi). (FR-009)
- [X] T018 [P] [US3] Add security event logging in `src/gamebook_web/auth/dev_auth.py`: `_unauthenticated` logs `logger.warning("auth failed: reason=%s path=%s", message, path)` before raising. (FR-010)
- [X] T019 [US3] Add `tests/server/test_production_guards.py`: assert server raises at boot when `ENV=production` + `GAMEBOOK_DEV_MODE=1`; assert `/docs` returns `404` when `ENV=production`; assert auth failures are logged; assert CORS `*` is rejected at startup when `allow_credentials=True`; assert OTLP defaults to TLS. (SC-003, SC-004, SC-016)

**Checkpoint**: Server refuses insecure production config; docs hidden; auth failures
logged with path and reason.

---

## Phase 4: US4 — OIDC auth is fail-closed (Priority: P1)

**Goal**: Remove the dev stub from the production path; require `OIDC_ISSUER` + `exp`
claim; strict JWKS key binding (`kid` required); correct cache key. Fixes CRITICAL A07
and HIGH A07 from 004 review.

**Dependency**: Requires Phase 1 complete. Phase 5 (US5) depends on this phase —
the auth seam must be fail-closed before campaign ownership can rely on real account IDs.

**Independent Test**: `uv run pytest tests/server/test_oidc_fail_closed.py -v` — boot
without `OIDC_JWKS_URI` (assert refusal); JWT without `exp` (assert `401`); JWT
without `kid` (assert `401`); JWT with wrong `iss` (assert `401`).

- [ ] T030 [US4] Remove the dev-stub fallback from `src/gamebook_web/api/app.py` lifespan: when `OIDC_JWKS_URI` is unset and `GAMEBOOK_DEV_MODE` is not explicitly enabled, raise `RuntimeError` (or install a dependency override returning `401` for every request). (ADR-022, FR-018)
- [ ] T031 [P] [US4] Move `DEV_TOKEN = "dev-token"` out of `src/gamebook_web/auth/dev_auth.py` production code into a test-fixture-only location (`tests/server/conftest.py` or `tests/server/test_constants.py`). The `dev_auth` module only defines it when `GAMEBOOK_DEV_MODE=1` is explicitly set in a non-production environment. (ADR-022, FR-018)
- [ ] T032 [US4] Make `OIDC_ISSUER` mandatory in `src/gamebook_web/auth/oidc_auth.py`: no empty-string default; if unset when OIDC is active, raise at startup. Set `verify_iss=True` always. (ADR-022, FR-019)
- [ ] T033 [P] [US4] Require `exp` claim in JWT decode in `src/gamebook_web/auth/oidc_auth.py`: tokens without `exp` → `401`. (ADR-022, FR-019)
- [ ] T034 [P] [US4] Reject tokens with missing `kid` in `src/gamebook_web/auth/oidc_auth.py`: no fallback to first JWKS key. (ADR-022, FR-020)
- [ ] T035 [US4] Change validated-token cache key in `src/gamebook_web/auth/oidc_auth.py` from full SHA-256 to `sha256(token)[:16] + str(exp)`. (ADR-022, FR-021)
- [ ] T036 [US4] Add `tests/server/test_oidc_fail_closed.py`: boot without `OIDC_JWKS_URI` (assert refusal); JWT without `exp` (assert `401`); JWT without `kid` (assert `401`); JWT with wrong `iss` (assert `401`); inspect cache key format. (SC-009)

**Checkpoint**: OIDC auth is fail-closed; dev stub is test-only; `OIDC_ISSUER` + `exp`
mandatory; strict `kid` binding; cache key aligned.

---

## Phase 5: US5 + US6 — Campaign ownership is DB-backed + lease semantics (Priority: P1/P2)

**Goal**: Replace in-memory `CampaignRegistry` with `AccountRepository` in play routes;
fix `create_campaign`/`_ensure_campaign`; `DELETE /me` confirmation; `save_slot` in
GDPR export; `takeover` validates `current_token`; lease expiry uses `<=`.
Fixes HIGH (campaign ownership split) and MEDIUM (lease semantics / account fixes) from 004.

**Dependency**: Requires Phase 4 (auth must be fail-closed so account resolution is real).

**Independent Test** (US5): With live Postgres, create campaign, assert `account_id` not
`NULL`; duplicate ID → `409`; list from Postgres not in-memory.
**Independent Test** (US6): Acquire lease, takeover with wrong `current_token` → `409`;
wait until `expires_at == now()` → assert expired.

- [ ] T037 [US5] Replace `CampaignRegistry` usage in `src/gamebook_web/api/play.py` with `AccountRepository` methods. `_get_active_campaign(account)` (from T113) calls `AccountRepository.get_active_campaign(account_id)` not `registry.get(...)`. Reduce the in-memory registry to transient-state cache only (current scene, session-lease token). (ADR-025, FR-022)
- [ ] T038 [P] [US5] Fix `src/gamebook_web/accounts.py` `create_campaign`: raise `409` on duplicate `campaign_id`; always set `account_id` on the campaign row. (ADR-025, FR-023)
- [ ] T039 [P] [US5] Fix `src/gamebook/storage/postgres.py` `_ensure_campaign`: insert campaign rows with the correct `account_id` (passed from the caller, not `NULL`). (ADR-025, FR-024)
- [ ] T040 [P] [US5] Fix `src/gamebook_web/api/account.py` `DELETE /me`: return `404` if account does not exist (not `204`); require a `confirmation` field in the request body — without it → `400`. (ADR-025, FR-025)
- [ ] T041 [P] [US5] Add `save_slot` snapshots to `src/gamebook_web/accounts.py` `export_account` payload. (ADR-025, FR-026)
- [ ] T042 [P] [US6] Fix `src/gamebook_web/sessions/lease.py` `takeover`: validate `current_token` against the current holder before force-acquiring. Wrong or missing → `409`. (ADR-023, FR-027)
- [ ] T043 [P] [US6] Fix `src/gamebook_web/sessions/lease.py` `acquire` and `validate`: change `<` to `<=` for expiry check (`expires_at <= now()` is expired). (ADR-023, FR-028)
- [ ] T044 [US5] Add `tests/server/test_account_endpoints.py`: `DELETE /me` `404` for non-existent, `400` without confirmation, `204` with confirmation; `GET /me/export` includes `save_slot`. (SC-013, SC-014)

**Checkpoint**: Campaign ownership is DB-backed; `create_campaign` rejects duplicates;
`_ensure_campaign` sets `account_id`; `DELETE /me` requires confirmation; GDPR export
includes `save_slot`; `takeover` validates `current_token`; lease expiry uses `<=`.

---

## Phase 6: US7 — Observability is wired and PII-free (Priority: P2)

**Goal**: Fix OTel instrumentation; wire span helpers; emit metrics; redact exceptions;
secure OTLP; security audit logging; CORS `*` rejection. Fixes HIGH (OTel not wired)
and MEDIUM (PII/traceback leak, no audit logs, OTLP insecure) from 004 review.

**Dependency**: Can run in parallel with Phase 5 (different files). Requires Phase 1.

**Independent Test**: `uv run pytest tests/server/test_otel_instrumentation.py
tests/server/test_security_audit_logging.py -v` — span helpers exist with correct
attributes, no PII, `http_requests_total` incremented, audit log lines present.

- [ ] T045 [US7] Fix `src/gamebook_web/observability/setup.py`: change `FastAPIInstrumentor().instrument()` to `FastAPIInstrumentor.instrument_app(app)`. (ADR-024, FR-029)
- [ ] T046 [US7] Wire `turn_span` in `src/gamebook_web/api/play.py` `/turn` route: wrap the handler body in `turn_span(campaign_id, account_id, turn_number)`. (ADR-024, FR-030)
- [ ] T047 [P] [US7] Wire `narrator_span` in `src/gamebook_web/harness/agent.py` narrator call: wrap the LLM call in `narrator_span()`. (ADR-024, FR-030)
- [ ] T048 [P] [US7] Emit metrics at call sites: `http_requests_total` (every HTTP request), `turn_duration_seconds` (after `/turn`), `active_campaigns` (on create/delete), `combat_rounds_total` (on combat round). (ADR-024, FR-030)
- [ ] T049 [P] [US7] Fix `src/gamebook_web/observability/tracing.py` `span_set_error`: record only `type(exc).__name__` — no message, no traceback. Replace `record_exception(exc)` with a manual event or attribute override. (ADR-024, FR-031)
- [ ] T050 [P] [US7] Fix `src/gamebook_web/api/app.py` generic exception handler: change `logger.exception(...)` to `logger.error("unhandled %s", type(exc).__name__)`. (ADR-024, FR-031)
- [ ] T051 [P] [US7] Remove `insecure=True` from `src/gamebook_web/observability/setup.py` OTLP exporters; use TLS by default. Only set `insecure=True` when `OTLP_INSECURE=true` is explicitly set. (ADR-024, FR-032)
- [ ] T052 [P] [US7] Add security audit logging in `src/gamebook_web/api/account.py` (sign-in/sign-out/failed auth/account deletion), `src/gamebook_web/api/sessions.py` (lease acquire/takeover/release), `src/gamebook_web/middleware/lease_guard.py` (lease validation failures), `src/gamebook_web/auth/oidc_auth.py` (JWKS fetch failures, token validation failures). Log at `INFO`/`WARNING` with opaque IDs only. (FR-033)
- [ ] T053 [P] [US7] Reject `GAMEBOOK_CORS_ORIGINS=*` at startup in `src/gamebook_web/api/app.py` when `allow_credentials=True`. (FR-034)
- [ ] T054 [US7] Add `tests/server/test_otel_instrumentation.py`: assert `turn_span`/`narrator_span` exist with correct attributes (no PII); assert `http_requests_total` incremented; assert `span_set_error` has no message/traceback; assert `instrument_app` was called. (SC-012)
- [ ] T055 [US7] Add `tests/server/test_security_audit_logging.py`: assert log lines for sign-in/out, failed auth, lease acquire/takeover/release, account deletion. (SC-015)

**Checkpoint**: OTel correctly instrumented; span helpers wired; metrics emitted;
exceptions redacted in spans and logs; OTLP defaults to TLS; security audit logging
covers all event types; CORS `*` rejected with credentials.

---

## Phase 7: US8 — Persistence foundation is production-hardened (Priority: P2)

**Goal**: Enforce TLS for Postgres connections; make `append_event` concurrency-safe
(no duplicate `seq`); add `PostgresStorage.close()` lifecycle; wrap `_build_snapshot`
in a consistent-read transaction; validate identifiers at save/load boundaries.
Fixes HIGH A02/A05 and MEDIUM A04/QA findings from 002 review.

**Dependency**: Can run in parallel with Phases 3–6 (different files: `postgres.py`
and its tests). Requires Phase 1.

**Independent Test**: `DATABASE_URL=... uv run pytest tests/server/test_postgres_storage.py
tests/server/test_atomic_writes.py tests/qa/test_storage_swap.py -v` — TLS enforced,
concurrent appends produce unique `seq`, `close()` is clean, snapshot is consistent.

- [ ] T072 [US8] Enforce TLS in `src/gamebook/storage/postgres.py`: create the async engine with `sslmode=require` (or `ssl=True`) by default; add non-production override env var `POSTGRES_SSL_MODE=disable` for local development; refuse plaintext URLs in production. (ADR-026, FR-037, SC-018)
- [ ] T073 [US8] Make `src/gamebook/storage/postgres.py` `append_event` concurrency-safe: lock the sequence range or use a DB-generated sequence; remove/correct the misleading inline comment at `src/gamebook/storage/postgres.py:230-232`. (ADR-027, FR-038, SC-019)
- [ ] T074 [P] [US8] Add `close()` to `src/gamebook/storage/postgres.py`: dispose the async engine and stop the daemon event loop; call it in live-Postgres test teardown and on MCP server graceful shutdown. (ADR-027, FR-039, SC-020)
- [ ] T075 [P] [US8] Wrap `src/gamebook/storage/postgres.py` `_build_snapshot` in an explicit read-only transaction (`async with session.begin()`) so `save_slot` captures a consistent snapshot. (ADR-027, FR-040, SC-021)
- [ ] T076 [P] [US8] Add identifier validation to `src/gamebook/storage/postgres.py` `save_slot`, `load_slot`, `load_combat`, and `remove_combat`: reject empty/`None`/`/`/`\`/`..` to match `JSONStorage` parity. (ADR-027, FR-041, SC-022)
- [ ] T077 [P] [US8] Extend `tests/qa/test_storage_swap.py` to include `PostgresStorage` when `DATABASE_URL` is present; prove the consumer-level swap boundary for every backend. (ADR-009, FR-042, SC-023)
- [ ] T078 [P] [US8] Rewrite `tests/server/test_atomic_writes.py` to simulate a failure after at least one `session.execute()` has run, proving no partial data is committed. (FR-043, SC-024)
- [ ] T079 [P] [US8] Update `docs/CONTRACTS.md` §11 (storage contract) to document TLS-by-default, concurrency-safe sequence allocation, and deterministic storage lifecycle. (ADR-026, ADR-027, Principle III)

**Checkpoint**: Postgres is TLS-hardened by default; `append_event` is concurrency-safe;
`PostgresStorage` has deterministic cleanup; snapshots are consistent; identifier
validation matches `JSONStorage`; swap-boundary and atomic-write tests cover Postgres.

---

## Phase 8: US10 — Narrator is tested (Priority: P2)

**Goal**: Exercise the `PydanticNarrator` live path with an integration test; ensure
`_check_terminal_state` handles both victory and death from `take_turn`; key rate
limiter on `account_id`; fix `request: Request = None` default; add dependency upper
bounds; record learning lessons. Fixes LOW (narrator untested) and MEDIUM (rate limiter)
from 003 review. (`combat_subagent.py` was deleted in spec 007 — T094 is OBSOLETE.)

**Dependency**: Can run in parallel with Phases 3–7 after Phase 1. Does not depend
on Phase 4 or 5 (different subsystem).

**Independent Test**: `uv run pytest tests/server/test_combat_victory.py
tests/server/test_narrator_integration.py tests/server/test_rate_limiter.py -v` —
narrator produces valid `Scene` with no `effects_applied`; combat victory archived;
rate limiter keys on `account_id`.

- [ ] T085 [P] [US10] Ensure `_check_terminal_state` in `src/gamebook_web/api/play.py` handles both victory (adventure module's `victory_flag`) and death correctly after `take_turn`. (`combat.py` was deleted in spec 007 — `_check_terminal_state` is only called from `take_turn`. No unification needed.) (ADR-028, FR-044)
- [ ] T086 [P] [US10] Remove `= None` default from `request: Request` parameter on all rate-limited routes in `src/gamebook_web/api/play.py`. (`combat.py` was deleted in spec 007 — only `play.py` routes remain.) (FR-045)
- [ ] T087 [P] [US10] Key the rate limiter on `account_id` when authenticated in `src/gamebook_web/limiter.py`; fall back to IP only when unauthenticated. Configure trusted proxy headers (`X-Forwarded-For`). (FR-046)
- [ ] T088 [P] [US10] Update `GET /me/graveyard` in `src/gamebook_web/api/play.py` (added in T114) to include `name`, `created_at`, `ended_at`, and `ended_reason` (`death` | `victory`) in each `GraveyardEntry`. (FR-048)
- [ ] T089 [P] [US10] Add upper bounds to floating `>=` ranges in `pyproject.toml` (e.g. `fastapi>=0.115.0,<1.0`). (FR-049)
- [ ] T090 [P] [US10] Create `docs/learning-lessons/contract_drift_requires_live_integration_test.md` — API/frontend contract drift requires a live integration test, not eyeballing field names. (FR-050)
- [ ] T091 [P] [US10] Create `docs/learning-lessons/single_shared_engine_subprocess_antipattern.md` — booting a single shared engine subprocess scoped to an env var is a multi-tenancy anti-pattern. (FR-050)
- [ ] T092 [US10] Add `tests/server/test_combat_victory.py`: win via `POST /me/game/turn` that triggers combat (auto-resolved inside the turn) → campaign ended + archived; assert `_check_terminal_state` was called; assert further turns → `409`. (No `POST /combat/round` — combat resolves inside `POST /turn` per spec 007.) (SC-025, FR-044)
- [ ] T093 [P] [US10] Add `tests/server/test_narrator_integration.py`: mocked LLM producing a valid `Scene` (narrator calls MCP tools during generation, narrates real results) → validation → response; assert no `effects` field in `Scene` and no `effects_applied` in `TurnResponse`. (SC-026, FR-047)
- [x] T094 **OBSOLETE — superseded by spec 007.** `combat_subagent.py` was deleted in spec 007 (ADR-029). No subagent to test.
- [ ] T095 [P] [US10] Add `tests/server/test_rate_limiter.py`: assert rate limiter keys on `account_id` when authenticated; falls back to IP when unauthenticated. (SC-028, FR-046)

**Checkpoint**: Combat victory works inside `POST /me/game/turn`; narrator tool-use
tested with no `effects_applied`; rate limiter keyed on `account_id`; graveyard entries
include all required fields; dependency upper bounds added; learning lessons recorded.

---

## Phase 9: US11 — SPA is production-hardened (Priority: P2)

**Goal**: Disable source maps in production; add CSP headers; add `ErrorBoundary`;
validate `CombatPanel` participants (or remove dead-code combat UI); 401/403 redirect
to `/auth`; token expiration checking; fix useEffect stale closure; free-text input
validation; error message sanitization; security headers; vitest upgrade.
Fixes 005 HIGH/MEDIUM/LOW blocking findings.

**Dependency**: Can run in parallel with Phases 3–8 (frontend files). Requires Phase 2
(frontend contract alignment must be complete before hardening the SPA).

**Independent Test**: `npm run build && ls dist/assets/*.map` — assert no source maps.
`npm test -- --run` — all unit tests pass. `npx playwright test` — e2e passes.

- [ ] T097 [P] [US11] Disable source maps in production: change `sourcemap: true` to `sourcemap: false` (or `sourcemap: import.meta.env.DEV`) in `frontend/vite.config.ts`. (FR-051, SC-031)
- [ ] T098 [P] [US11] Add Content-Security-Policy meta tag to `frontend/index.html`: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'`. (FR-052, SC-032)
- [ ] T099 [P] [US11] Create `frontend/src/components/ErrorBoundary.tsx` (class component catching render errors, fallback UI with "reload" button); wrap App root in `frontend/src/App.tsx`. (FR-053, SC-033)
- [ ] T100 [P] [US11] Handle dead-code combat UI in `frontend/src/components/CombatPanel.tsx`: combat is auto-resolved inside the turn — no separate per-round combat UI. If keeping `CombatPanel` as narrative-only display, validate `combat` is non-null before rendering. If removing: delete `CombatPanel.tsx` and the `inCombat` branch in `PlayPage.tsx`. (FR-054, SC-034)
- [ ] T101 [P] [US11] Add 401/403 handling in `frontend/src/hooks/useGame.ts`: intercept `err.code === 'unauthenticated'` or `err.code === 'forbidden'` and redirect to `/auth`. (FR-055, SC-035)
- [ ] T102 [P] [US11] Add token expiration checking in `frontend/src/hooks/useGame.ts` (or `frontend/src/hooks/useAuth.ts`): parse `expires_at` from session lease and redirect to `/auth` if expired. (FR-056, SC-036)
- [ ] T103 [P] [US11] Fix useEffect stale closure in `frontend/src/hooks/useGame.ts` and `frontend/src/hooks/useCampaign.ts`: remove `load` from dependency array or wrap in `useCallback`. (FR-057)
- [ ] T104 [P] [US11] Add free-text input validation in `frontend/src/components/ChoicesPanel.tsx`: reject empty submissions (after trim), enforce max length (1000 chars), disable submit button when empty. (FR-058)
- [ ] T105 [P] [US11] Sanitize error messages in `frontend/src/hooks/useGame.ts`: show generic "Something went wrong" to users; log details to `console.error` only in dev mode. (FR-059)
- [ ] T106 [P] [US11] Add security headers to the backend response or reverse proxy config: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`. (FR-060)
- [ ] T107 [P] [US11] Pin `vitest >= 3.2.6` in `frontend/package.json` (GHSA-5xrq-8626-4rwp); run `npm install` to refresh lockfile. (FR-061)
- [ ] T108 [US11] Add `frontend/src/components/__tests__/test_error_boundary.test.tsx`: throw in child component → assert fallback UI renders (not blank screen). (SC-033)
- [ ] T109 [US11] Add `frontend/src/components/__tests__/test_combat_panel_validation.test.tsx`: if `CombatPanel` is kept, assert it renders gracefully when `combat` is null/undefined. If removed, this test is not needed. (SC-034)
- [ ] T110 [US11] Add `frontend/src/hooks/__tests__/test_auth_redirect.test.tsx`: mock 401 response → assert redirect to `/auth`; mock expired `expires_at` → assert redirect. (SC-035, SC-036)
- [ ] T111 [US11] Add `frontend/src/components/__tests__/test_choices_validation.test.tsx`: empty input → submit button disabled; max length enforced. (FR-058)

**Checkpoint**: SPA is production-hardened — source maps disabled, CSP present,
`ErrorBoundary` wraps App, combat UI validated or removed, 401/403 redirects, token
expiration checked, useEffect fixed, free-text validated, errors sanitized, security
headers set, vitest upgraded.

---

## Phase 10: Postgres integration tests (cross-cutting, requires Phases 5–7)

**Goal**: Add live-Postgres integration tests covering the code fixed in Phases 4–7
(accounts, leases, campaign ownership, GDPR, campaign scoping, storage hardening).
**Requires**: `DATABASE_URL` environment variable set to a running Postgres instance.

**Dependency**: Requires Phases 5, 6, 7 (the code under test must be fixed first).

- [ ] T056 [P] Add `tests/server/test_postgres_accounts.py`: account upsert (`get_or_create`), account resolution from OIDC `sub`, account deletion with cascade. (SC-017, FR-035)
- [ ] T057 [P] Add `tests/server/test_postgres_campaign_ownership.py`: create campaign (assert `account_id` not `NULL`); duplicate ID → `409`; list campaigns (assert from Postgres, not in-memory); delete campaign (assert row removed). (SC-010, SC-017, FR-035)
- [ ] T058 [P] Add `tests/server/test_postgres_leases.py`: acquire/validate/takeover/release; wrong `current_token` → `409`; expiry `<=` boundary; `SELECT FOR UPDATE` concurrency. (SC-011, SC-017, FR-035)
- [ ] T059 [P] Add `tests/server/test_postgres_gdpr.py`: export includes account + campaigns + `save_slot` snapshots; erasure removes all rows. (SC-014, SC-017, FR-035)
- [ ] T060 [P] Add `tests/server/test_postgres_campaign_scoping.py`: two campaigns with different `campaign_id` values do not see each other's state (extends `test_multi_campaign_isolation.py` to run against live DB). (SC-002, SC-017, FR-035)
- [ ] T080 [P] Add `tests/server/test_postgres_storage.py` (or extend existing): TLS enforcement, concurrent `append_event`, `close()` lifecycle, consistent snapshot, identifier validation. (SC-018, SC-019, SC-020, SC-021, SC-022, FR-037–FR-041)
- [ ] T081 [P] Run the storage swap-boundary test with Postgres: `DATABASE_URL=... uv run pytest tests/qa/test_storage_swap.py -v`. (SC-023, FR-042)
- [ ] T082 [P] Run the atomic-write test with Postgres: `DATABASE_URL=... uv run pytest tests/server/test_atomic_writes.py -v`. (SC-024, FR-043)

**Checkpoint**: All DB-backed paths covered by live Postgres integration tests including
storage hardening paths from Phase 7.

---

## Phase 11: Polish & Governance

**Purpose**: MEDIUM/LOW fixes (adventure-module victory flag, campaign name, session lease
gating, `GET /me`, vite CVE), dev-token alignment, CORS narrowing, ADR renumbering,
and final verification sweep.

**Dependency**: MEDIUM/LOW tasks (T020–T029) can run in parallel with Phases 2–10 after
Phase 1. ADR renumbering (T061–T065) and verification (T066–T071) must follow all implementation.

### MEDIUM/LOW fixes (can run in parallel with Phases 2–9)

- [ ] T020 [P] Move the `malachar_defeated` victory check out of `src/gamebook_web/api/play.py` into an adventure-module config (e.g. a `victory_flag` field read from Ignarok SKILL metadata or a small `adventure_module.py` config). The API reads the flag name from config. (FR-005, swap boundary #2)
- [ ] T021 [P] Add `name: str | None` to `CampaignState` in `src/gamebook_web/sessions/campaign.py`; `registry.create(account_id, name=None)` stores it; `CampaignResponse` (from `POST /me/game` and `GET /me/game`) and `GraveyardEntry` include `name`. Update `play.py:create_game` handler to pass `body.name`. (FR-006)
- [ ] T022 [P] Gate `useGame.acquireSession`/`takeoverSession`/`releaseSession` behind `import.meta.env.VITE_SESSION_LEASE === 'true'` (default off) in `frontend/src/hooks/useGame.ts`. Session routes are `/me/game/session`, `/me/game/session/takeover`, `DELETE /me/game/session` (updated in T116). Document the flag in `frontend/.env.local.example`. (FR-007)
- [ ] T023 [P] Add `GET /me` endpoint in `src/gamebook_web/api/account.py` returning `{ id: account.account_id }` (dev stub; real identity + metadata in slice 004). Game state lives at `/me/game` — this is the account-identity endpoint only. (FR-007)
- [ ] T024 [P] Pin `vite` to `>=5.4.12` in `frontend/package.json` (CVE-2025-30208). Run `npm install` to update the lockfile. (FR-011)
- [ ] T025 [P] Align the dev token: `frontend/.env.local.example` → `VITE_DEV_TOKEN=dev-token`; `frontend/src/pages/AuthPage.tsx` fallback → `dev-token`; backend `DEV_TOKEN` is already `dev-token`. (FR-012)
- [ ] T026 [P] Narrow CORS in `src/gamebook_web/api/app.py`: `allow_methods=["GET","POST","DELETE","OPTIONS"]`, `allow_headers=["Content-Type","Authorization"]`. (FR-013)
- [x] T027 **OBSOLETE — superseded by spec 007.** `_RESULT_KEYS`, `EffectType`, `Effect`, and `_scene_contains_fabricated_numbers` were deleted in spec 007 (ADR-029). Principle I is now enforced by design. No replacement needed.
- [ ] T028 [P] Rename `docs/adrs/ADR-014-pydantic-ai-v2-mcp-toolset-direct-call.md` → `docs/adrs/ADR-021-pydantic-ai-v2-mcp-toolset-direct-call.md`; update the ADR header number. Delete `docs/adrs/ADR-014-vite-env-import-meta-types.md` and `docs/adrs/ADR-015-mock-mode-client-side-fixture-layer.md` (the "moved" stubs). (ADR-020, FR-016)
- [ ] T029 [P] Update `docs/learning-lessons/pydantic_ai_v2_mcp_toolset_direct_call_pattern.md` cross-link from ADR-014 to ADR-021. (ADR-020, FR-016)

### ADR renumbering (after implementation complete)

- [ ] T061 [P] Rename `docs/adrs/ADR-017-oidc-jwt-jwks-validation-pattern.md` → `ADR-022-oidc-jwt-jwks-validation-pattern.md`; update the ADR header number. (FR-036, ADR-020)
- [ ] T062 [P] Rename `docs/adrs/ADR-018-session-lease-acquire-takeover-semantics.md` → `ADR-023-session-lease-acquire-takeover-semantics.md`; update the ADR header number. (FR-036, ADR-020)
- [ ] T063 [P] Rename `docs/adrs/ADR-019-opentelemetry-auto-instrumentation.md` → `ADR-024-opentelemetry-auto-instrumentation.md`; update the ADR header number. (FR-036, ADR-020)
- [ ] T064 [P] Create `docs/adrs/ADR-025-db-backed-campaign-registry.md` documenting the replacement of `CampaignRegistry` with `AccountRepository`. (FR-036, ADR-025)
- [ ] T083 [P] Create `docs/adrs/ADR-026-postgres-tls-policy.md` documenting TLS-by-default policy for PostgreSQL connections. (FR-037, ADR-026)
- [ ] T084 [P] Create `docs/adrs/ADR-027-postgres-concurrency-and-lifecycle.md` documenting concurrency-safe event sequence allocation and deterministic `PostgresStorage` lifecycle. (FR-038, FR-039, ADR-027)
- [ ] T096 [P] Create `docs/adrs/ADR-028-combat-terminal-state-unification.md` documenting that `_check_terminal_state` runs after `take_turn` (the only entry point post-spec-007). Original scope of "unifying between take_turn and combat_round" is moot — `combat_round` was deleted in spec 007. (ADR-028, FR-044)
- [ ] T065 Update `CLAUDE.md` ADR table to list ADRs 014–028 exactly once each with correct numbers and titles. (SC-008, FR-016, FR-036)

### Final verification (must be last)

- [ ] T066 Run `uv run pytest -q` (full backend suite) — must be green. (SC-006)
- [ ] T067 Run `uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q` (plugability audit) — must be green. (SC-005)
- [ ] T068 Run `cd frontend && npm test -- --run` (vitest unit suite including new 005 tests) — must be green. (SC-007)
- [ ] T069 Run `cd frontend && npx playwright test` (e2e, including the new live-backend suite) — must be green. (SC-001)
- [ ] T070 Run `DATABASE_URL=... uv run pytest tests/server/test_postgres_*.py tests/qa/test_storage_swap.py tests/server/test_atomic_writes.py -v` (live Postgres integration tests) — must be green. (SC-017, SC-023, SC-024)
- [ ] T071 Run `/sdd-final-review` to dispatch cycle-2 (QA + Security + Tech Leader) and confirm cycle-1 findings from all five reviews are closed.

**Checkpoint**: All success criteria met; ADR numbering clean; ready for SDD cycle-2 review.

---

## Dependencies

```
Phase 1 (US2) → ALL other phases (CRITICAL blocker)
Phase 1 → Phase 2 (US1) → Phase 9 (US11)   [US11 needs US1 contract alignment]
Phase 1 → Phase 4 (US4) → Phase 5 (US5/US6)  [US5 needs fail-closed auth]
Phase 1 → Phase 3 (US3)                       [independent after Phase 1]
Phase 1 → Phase 6 (US7)                       [independent after Phase 1]
Phase 1 → Phase 7 (US8)                       [independent after Phase 1]
Phase 1 → Phase 8 (US10)                      [independent after Phase 1]
Phases 5, 6, 7 → Phase 10 (Postgres tests)    [tests exercise fixed code]
All implementation → Phase 11 ADR renaming/verification
```

**Parallel opportunities after Phase 1**:
- Phases 3, 4, 6, 7, 8 can run simultaneously (different subsystems)
- Polish tasks T020–T029 can run in parallel with any implementation phase
- Phase 9 (US11) can start after Phase 2 (US1) — frontend independent of backend auth

## MVP Scope

**US2 (Phase 1) + US1 (Phase 2)** = minimum viable state where:
- The SPA runs against the live backend without contract mismatches
- The engine is multi-tenant and safe from cross-account leakage

Add **US3 (Phase 3)** before any production exposure.

## Implementation Strategy

1. **Phase 1 first, always**: The multi-tenant engine refactor (`campaign_id` in all 18
   tools + `storage_factory`) touches core engine code and tests. Everything else builds on it.
2. **Then US1 (Phase 2)**: Backend route redesign + frontend alignment unblocks the
   live-backend Playwright test which is the integration health check for the whole system.
3. **Parallel sprint** after Phase 2: Phases 3, 4, 6, 7, 8 (auth, observability, persistence,
   narrator) can proceed concurrently — assign to different agents or engineers by subsystem.
4. **Phase 5 waits for Phase 4**: Campaign ownership must run on real auth.
5. **Postgres tests (Phase 10) last in their cluster**: Write tests after fixing the code.
6. **Polish/Governance (Phase 11)** completes the sweep.
