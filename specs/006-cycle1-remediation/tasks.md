---
description: "Task list for Cycle-1 Remediation (001 + 002 + 003 + 004 + 005) — closes SDD cycle-1 findings from all five reviews (CRITICAL+HIGH+MEDIUM+LOW+GOVERNANCE)"
---

# Tasks: Cycle-1 Remediation (001 + 002 + 003 + 004 + 005)

**Input**: Design documents from `specs/006-cycle1-remediation/` (spec.md, plan.md)
and ADRs 017–028. Driven by five SDD final reviews:
- `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
- `reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md`
- `reports/sdd-final-review/003-web-backend-mvp/cycle-1-20260628-1010.md`
- `reports/sdd-final-review/004-accounts-hardening-obs/cycle-1-20260628-1043.md`
- `reports/sdd-final-review/005-professional-spa/cycle-1-20260628-1223.md`

**Prerequisites**: spec.md, plan.md; ADRs 017–028; `002-persistence-foundation`,
`003-web-backend-mvp`, `005-professional-spa` merged to `dev`; `feat/004-auth-obs`
implementation absorbed; 002 and 003 remediated in-place on the 006 branch.

**Tests**: Included — multi-campaign isolation (SC-002), production guards
(SC-003/SC-004/SC-016), live-backend integration (SC-001), plugability audit (SC-005),
full suite (SC-006/SC-007), OIDC fail-closed (SC-009), DB-backed ownership
(SC-010), lease semantics (SC-011), OTel instrumentation (SC-012), account endpoints
(SC-013/SC-014), security audit logging (SC-015), Postgres integration (SC-017),
Postgres TLS (SC-018), concurrency-safe append (SC-019), storage lifecycle (SC-020),
consistent snapshot (SC-021), identifier validation (SC-022), swap-boundary with
Postgres (SC-023), atomic-write mid-statement failure (SC-024), combat victory path
(SC-025), narrator integration (SC-026), combat subagent (SC-027), rate limiter
keying (SC-028), `list_campaigns` fields (SC-029), dependency upper bounds (SC-030),
source maps disabled (SC-031), CSP headers (SC-032), ErrorBoundary (SC-033),
CombatPanel validation (SC-034), 401/403 redirect (SC-035), token expiration (SC-036).

**Organization**: Tasks are grouped by phase (dependency-ordered). Phase 1 blocks all
other phases (the multi-tenant refactor touches every call site). Phases 7–9 (004
remediation) can run in parallel after Phase 1, but Phase 8 depends on Phase 7 for the
auth seam. Phase 6 (002 remediation), Phase 10 (003 remediation), and Phase 11 (005
SPA hardening) can run in parallel with Phases 2–5 after Phase 1.

## Format: `[ID] [Phase] [P?] Description`
- **[P]**: parallelizable (different files, no incomplete dependency)

## Path Conventions
Engine: `src/gamebook/`. Web backend: `src/gamebook_web/`. Frontend: `frontend/src/`.
Tests: `tests/{server,qa}/` (backend), `frontend/tests/` (frontend).

---

## Phase 1: ADR-018 — Multi-tenant engine (CRITICAL, blocks all other phases)

**Purpose**: Every MCP tool gains `campaign_id`; `build_server` takes a
`storage_factory`; the web layer passes `campaign_id` on every call. Fixes CRITICAL
A01 (cross-account leakage) and Bug #5 (engine state not scoped per campaign).

**⚠️ CRITICAL**: No other phase begins until this phase is complete and the engine
tests are green.

- [ ] T001 [P1] Add `storage_factory: Callable[[str], StorageBackend]` parameter to `build_server` in `src/gamebook/mcp/server.py`; replace the module-level `storage` reference with per-call `storage = storage_factory(campaign_id)` inside each tool. Add `combat_factory` (or a combined factory) so `CombatService` is constructed per-campaign. (ADR-018)
- [ ] T002 [P1] Add `campaign_id: str` as the first parameter of every MCP tool in `src/gamebook/mcp/server.py` (18 tools). Each tool body looks up `storage = storage_factory(campaign_id)` before operating. (ADR-018, FR-001)
- [ ] T003 [P1] Update `main()` composition root in `src/gamebook/mcp/server.py` to build a `storage_factory` closure: Phase-2 returns `PostgresStorage(database_url, campaign_id)` (cached per campaign_id); Phase-1 returns `JSONStorage(f"estado/{campaign_id}")`. Remove the single-`storage` construction. (ADR-018)
- [ ] T004 [P1] Update `tests/server/conftest.py` to inject an in-process `storage_factory` that returns per-campaign `InMemoryStorage` instances (cached by campaign_id). Existing tests pass `campaign_id="dev-campaign"` or a fixture-provided id. (ADR-018, Principle IV)
- [ ] T005 [P1] Update every `call_engine(toolset, tool_name, ...)` call site in `src/gamebook_web/api/play.py` (~15 sites) and `src/gamebook_web/api/combat.py` (~5 sites) to pass `campaign_id=campaign_id`. (ADR-018, FR-002)
- [ ] T006 [P1] Remove `GAMEBOOK_CAMPAIGN_ID` reading from `src/gamebook_web/api/app.py` lifespan and `src/gamebook_web/mcp_host.py` — the web backend no longer boots scoped to one campaign. The Phase-1 terminal harness path in `main()` may still use it as a default. (ADR-018, FR-002)
- [ ] T007 [P1] Update `docs/CONTRACTS.md` §6 (MCP tool contract) to show `campaign_id: str` as the first parameter of every tool. Update the HTTP API contract draft to match. (FR-017, Principle III)
- [ ] T008 [P1] Add `tests/server/test_multi_campaign_isolation.py`: create two campaigns, create a character in A, assert B has no character; take a turn in A, assert B's world is unchanged; start combat in A, assert B has no active combat. (SC-002, FR-001)
- [ ] T009 [P1] Run the plugability audit (`uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q`) and fix any new violations introduced by the `storage_factory` seam. (SC-005, Principle II)

**Checkpoint**: Engine is multi-tenant; one process serves N campaigns with isolated
state; CONTRACTS.md §6 updated; plugability audit green.

---

## Phase 2: ADR-017 — Contract alignment (HIGH)

**Purpose**: Frontend TS types conform to backend Pydantic response models; the SPA
assembles `CampaignState` from granular fields; a live-backend integration test
catches future drift. Fixes HIGH Bugs #1–4, #6.

- [ ] T010 [P2] Update `frontend/src/types/index.ts`: `TurnResponse` → `{ scene, character?, world?, effects_applied }`; `CombatRoundResponse` → `{ outcome, final_result?, character?, campaign_ended }`; `FleeCombatResponse` → `{ result, character?, campaign_ended }`; `CampaignSummary` → `{ campaign_id, status, name?, created_at?, updated_at? }`; `CampaignState` → `{ campaign_id, status, character?, world?, current_scene?, combat? }`. (ADR-017, FR-003, FR-004)
- [ ] T011 [P2] Update `frontend/src/hooks/useGame.ts`: `applyTurnResponse` assembles `CampaignState` from `{ campaign_id (prior), status (prior), character: res.character, world: res.world, current_scene: res.scene, combat (prior) }`; `applyCombatResponse` updates `character` and `combat` from response fields. Remove `setCampaign(res.campaign)`. (ADR-017, FR-003)
- [ ] T012 [P2] Update `frontend/src/api/client.ts` and all components to use `campaign_id` (not `id`) everywhere. Update `createCampaign`/`listCampaigns`/`getCampaign` return-type usage. (ADR-017, FR-004)
- [ ] T013 [P2] Update `frontend/src/api/mock.ts` to return the new response shapes (mock stays in sync with the canonical contract per ADR-016/ADR-017). (ADR-017)
- [ ] T014 [P2] Add `frontend/tests/e2e/live-play-loop.spec.ts`: a Playwright suite that runs against the live FastAPI backend (started in global setup) with `VITE_USE_MOCK=false`. Drives: create campaign → create character → take 2 turns → combat round → end. Asserts no `undefined` fields. (SC-001, FR-015)
- [ ] T015 [P2] Run `npm test` and fix any type errors / test failures from the type changes. (SC-007)

**Checkpoint**: SPA types match backend; live-backend Playwright test passes; mock
mode still works.

---

## Phase 3: Production guards (CRITICAL/HIGH)

**Purpose**: Fail-fast on insecure deployment; disable docs in production; log auth
failures. Fixes CRITICAL (dev-auth production guard) and HIGH (docs enabled +
security logging).

- [ ] T016 [P3] Add a startup guard in `src/gamebook_web/api/app.py` lifespan: if `ENV=production` and `GAMEBOOK_DEV_MODE=1`, raise `RuntimeError` with a clear message. (FR-008)
- [ ] T017 [P3] Disable `/docs`, `/redoc`, `/openapi.json` when `ENV=production`: construct FastAPI with `docs_url=None if os.getenv("ENV")=="production" else "/docs"` (same for redoc, openapi). (FR-009)
- [ ] T018 [P3] Add security event logging in `src/gamebook_web/auth/dev_auth.py`: `_unauthenticated` logs `logger.warning("auth failed: reason=%s", message)` before raising. (FR-010)
- [ ] T019 [P3] Add `tests/server/test_production_guards.py`: assert the server raises at boot when `ENV=production` + `GAMEBOOK_DEV_MODE=1`; assert `/docs` returns 404 when `ENV=production`; assert auth failures are logged; assert CORS `*` is rejected at startup when `allow_credentials=True`; assert OTLP defaults to TLS. (SC-003, SC-004, SC-016)

**Checkpoint**: Server refuses insecure production config; docs hidden in production;
auth failures logged.

---

## Phase 4: MEDIUM fixes

**Purpose**: Victory flag moved to adventure-module config; `create_campaign` keeps
the `name`; session-lease calls gated; `GET /me` added; vite pinned. Fixes MEDIUM
findings.

- [ ] T020 [P4] [P] Move the `malachar_defeated` victory check out of `src/gamebook_web/api/play.py:405` into an adventure-module config (e.g. a `victory_flag` field read from the Ignarok SKILL metadata or a small `adventure_module.py` config). The API reads the flag name from config. (FR-005, swap boundary #2)
- [ ] T021 [P4] [P] Add `name: str | None` to `CampaignState` in `src/gamebook_web/sessions/campaign.py`; `registry.create(account_id, name=None)` stores it; `CampaignResponse` and `list_campaigns` include `name`. Update `play.py:create_campaign` to pass `body.name`. (FR-006)
- [ ] T022 [P4] [P] Gate `useGame.acquireSession`/`takeoverSession`/`releaseSession` behind `import.meta.env.VITE_SESSION_LEASE === 'true'` (default off) in `frontend/src/hooks/useGame.ts`. Document the flag in `frontend/.env.local.example`. (FR-007)
- [ ] T023 [P4] [P] Add `GET /me` endpoint in `src/gamebook_web/api/play.py` returning `{ id: account.account_id }` (dev stub; real identity in `004`). (FR-007)
- [ ] T024 [P4] [P] Pin `vite` to `>=5.4.12` in `frontend/package.json` (CVE-2025-30208). Run `npm install` to update the lockfile. (FR-011)

**Checkpoint**: Victory flag swappable; campaign name persisted; no 404s on gated
endpoints; vite patched.

---

## Phase 5: LOW + GOVERNANCE

**Purpose**: Dev-token alignment, CORS narrowing, allowlist for fabricated numbers,
ADR renumbering. Fixes LOW + GOVERNANCE findings.

- [ ] T025 [P5] [P] Align the dev token: `.env.local.example` → `VITE_DEV_TOKEN=dev-token`; `frontend/src/pages/AuthPage.tsx` fallback → `dev-token`; backend `DEV_TOKEN` is already `dev-token`. (FR-012)
- [ ] T026 [P5] [P] Narrow CORS in `src/gamebook_web/api/app.py`: `allow_methods=["GET","POST","DELETE","OPTIONS"]`, `allow_headers=["Content-Type","Authorization"]`. (FR-013)
- [ ] T027 [P5] Replace `_RESULT_KEYS` denylist with `_ALLOWED_EFFECT_PARAMS` allowlist in `src/gamebook_web/harness/agent.py`, keyed by `EffectType`. Unknown param keys → `ModelRetry`. Extend the prose regex to catch "lost N points", "took N damage", "N hp". Update `tests/server/test_scene_numbers.py` to cover the allowlist behavior. (ADR-019, FR-014)
- [ ] T028 [P5] [P] Rename `docs/adrs/ADR-014-pydantic-ai-v2-mcp-toolset-direct-call.md` → `docs/adrs/ADR-021-pydantic-ai-v2-mcp-toolset-direct-call.md`; update the ADR header number. Delete `docs/adrs/ADR-014-vite-env-import-meta-types.md` and `docs/adrs/ADR-015-mock-mode-client-side-fixture-layer.md` (the "moved" stubs). (ADR-020, FR-016)
- [ ] T029 [P5] [P] Update `docs/learning-lessons/pydantic_ai_v2_mcp_toolset_direct_call_pattern.md` cross-link from ADR-014 to ADR-021. (ADR-020, FR-016)

**Checkpoint**: LOW findings closed; ADR numbering clean (001 ADRs).

---

## Phase 6: ADR-026/027 — Persistence foundation hardening (HIGH/MEDIUM, from 002 review)

**Purpose**: Enforce TLS for Postgres; make `append_event` concurrency-safe; add
`PostgresStorage.close()` lifecycle; wrap `_build_snapshot` in a transaction;
validate identifiers; extend swap-boundary and atomic-write tests. Fixes 002 HIGH
A02/A05 and MEDIUM A04/QA findings.

**⚠️ Can run in parallel with Phases 2–5** after Phase 1 is complete (different files,
no dependency on frontend/contract work).

- [ ] T072 [P6] Enforce TLS in `src/gamebook/storage/postgres.py`: create the async engine with `sslmode=require` (or `ssl=True`) by default; add a non-production override env var (e.g., `POSTGRES_SSL_MODE=disable`) for local development; refuse plaintext URLs in production. (ADR-026, FR-037, SC-018)
- [ ] T073 [P6] Make `src/gamebook/storage/postgres.py` `append_event` concurrency-safe: lock the sequence range or use a generated sequence; remove/correct the misleading inline comment at `src/gamebook/storage/postgres.py:230-232`. Add a concurrent-append test. (ADR-027, FR-038, SC-019)
- [ ] T074 [P6] Add `close()` to `src/gamebook/storage/postgres.py`: dispose the async engine and stop the daemon event loop; call it in live-Postgres test teardown and on MCP server graceful shutdown. (ADR-027, FR-039, SC-020)
- [ ] T075 [P6] Wrap `src/gamebook/storage/postgres.py` `_build_snapshot` in an explicit read-only transaction (`async with session.begin()`) so `save_slot` captures a consistent snapshot. (ADR-027, FR-040, SC-021)
- [ ] T076 [P6] Add identifier validation to `src/gamebook/storage/postgres.py` `save_slot`, `load_slot`, `load_combat`, and `remove_combat`, rejecting empty/`None`/`/`/`\`/`..` to match `JSONStorage` parity. (ADR-027, FR-041, SC-022)
- [ ] T077 [P6] [P] Extend `tests/qa/test_storage_swap.py` to include `PostgresStorage` when `DATABASE_URL` is present; prove the consumer-level swap boundary for every backend. (ADR-009, FR-042, SC-023)
- [ ] T078 [P6] [P] Rewrite `tests/server/test_atomic_writes.py` to simulate a failure after at least one `session.execute()` has run, proving no partial data is committed. (FR-043, SC-024)
- [ ] T079 [P6] [P] Update `docs/CONTRACTS.md` §11 (storage contract) to document TLS-by-default, concurrency-safe sequence allocation, and deterministic storage lifecycle. (ADR-026, ADR-027, Principle III)

**Checkpoint**: Postgres is TLS-hardened by default; `append_event` is concurrency-safe;
`PostgresStorage` has deterministic cleanup; snapshots are consistent; identifier
validation matches `JSONStorage`; swap-boundary and atomic-write tests cover Postgres.

---

## Phase 7: ADR-022 — Fail-closed OIDC auth (CRITICAL/HIGH, from 004 review)

**Purpose**: Remove the dev stub from the production path; require `OIDC_ISSUER` +
`exp`; strict JWKS key binding; cache key alignment. Fixes 004 CRITICAL A07 and
HIGH A07.

**⚠️ Depends on**: Phase 1 (multi-tenant engine must be in place so the auth seam
operates on the correct campaign context). Phase 8 depends on this phase for the
auth seam.

- [ ] T030 [P7] Remove the dev stub fallback from `src/gamebook_web/api/app.py` lifespan: when `OIDC_JWKS_URI` is unset and `GAMEBOOK_DEV_MODE` is not explicitly enabled, raise `RuntimeError` (or install a dependency override returning `401` for every request). (ADR-022, FR-018)
- [ ] T031 [P7] Move `DEV_TOKEN = "dev-token"` out of `src/gamebook_web/auth/dev_auth.py` production code — into a test-fixture-only location (e.g. `tests/server/conftest.py` or `tests/server/test_constants.py`). The `dev_auth` module only defines it when `GAMEBOOK_DEV_MODE=1` is explicitly set in a non-production environment. (ADR-022, FR-018)
- [ ] T032 [P7] Make `OIDC_ISSUER` mandatory in `src/gamebook_web/auth/oidc_auth.py`: no empty-string default; if unset when OIDC is active, raise at startup. Set `verify_iss=True` always. (ADR-022, FR-019)
- [ ] T033 [P7] Require `exp` claim in JWT decode in `src/gamebook_web/auth/oidc_auth.py`: tokens without `exp` → `401`. (ADR-022, FR-019)
- [ ] T034 [P7] Reject tokens with missing `kid` in `src/gamebook_web/auth/oidc_auth.py`: no fallback to the first JWKS key. (ADR-022, FR-020)
- [ ] T035 [P7] Change validated-token cache key in `src/gamebook_web/auth/oidc_auth.py` from full SHA-256 to `sha256(token)[:16] + str(exp)`. (ADR-022, FR-021)
- [ ] T036 [P7] Add `tests/server/test_oidc_fail_closed.py`: boot without `OIDC_JWKS_URI` (assert refusal); JWT without `exp` (assert `401`); JWT without `kid` (assert `401`); JWT with wrong `iss` (assert `401`); inspect cache key format. (SC-009)

**Checkpoint**: OIDC auth is fail-closed; dev stub is test-only; `OIDC_ISSUER`+`exp`
mandatory; strict `kid` binding; cache key aligned.

---

## Phase 8: ADR-023/025 — DB-backed campaign ownership + lease fixes (HIGH/MEDIUM, from 004 review)

**Purpose**: Replace `CampaignRegistry` with `AccountRepository` in play routes; fix
`create_campaign`/`_ensure_campaign`; `DELETE /me` confirmation; `save_slot` in
export; `takeover` validates `current_token`; lease expiry `<=`. Fixes 004 HIGH
(campaign ownership) and MEDIUM (lease/account) findings.

**⚠️ Depends on**: Phase 7 (auth seam must be fail-closed so account resolution is
real).

- [ ] T037 [P8] Replace `CampaignRegistry` usage in `src/gamebook_web/api/play.py` `create/list/get/delete` campaign routes with `AccountRepository` methods. Remove or reduce the in-memory registry to a transient-state cache only. (ADR-025, FR-022)
- [ ] T038 [P8] Fix `src/gamebook_web/accounts.py` `create_campaign`: raise `409` on duplicate `campaign_id`; always set `account_id` on the campaign row. (ADR-025, FR-023)
- [ ] T039 [P8] Fix `src/gamebook/storage/postgres.py` `_ensure_campaign`: insert campaign rows with the correct `account_id` (passed from the caller, not `NULL`). (ADR-025, FR-024)
- [ ] T040 [P8] Fix `src/gamebook_web/api/account.py` `DELETE /me`: return `404` if the account does not exist (not `204`); require a `confirmation` field in the request body. Without it → `400`. (ADR-025, FR-025)
- [ ] T041 [P8] Add `save_slot` snapshots to `src/gamebook_web/accounts.py` `export_account` payload. (ADR-025, FR-026)
- [ ] T042 [P8] Fix `src/gamebook_web/sessions/lease.py` `takeover`: validate `current_token` against the current holder before force-acquiring. Wrong/missing → `409`. (ADR-023, FR-027)
- [ ] T043 [P8] Fix `src/gamebook_web/sessions/lease.py` `acquire` and `validate`: change `<` to `<=` for expiry check (`expires_at <= now()` is expired). (ADR-023, FR-028)
- [ ] T044 [P8] Add `tests/server/test_account_endpoints.py`: `DELETE /me` `404` for non-existent, `400` without confirmation, `204` with confirmation; `GET /me/export` includes `save_slot`. (SC-013, SC-014)

**Checkpoint**: Campaign ownership is DB-backed; `create_campaign` rejects duplicates;
`_ensure_campaign` sets `account_id`; `DELETE /me` requires confirmation; GDPR export
includes `save_slot`; `takeover` validates `current_token`; lease expiry is `<=`.

---

## Phase 9: ADR-024 — Observability + PII discipline (HIGH/MEDIUM, from 004 review)

**Purpose**: Fix OTel instrumentation; wire span helpers; emit metrics; redact
exceptions; secure OTLP; security audit logging; CORS `*` rejection. Fixes 004 HIGH
(OTel ineffective) and MEDIUM (PII/traceback leak, no audit logs, OTLP insecure).

**⚠️ Can run in parallel with Phase 8** (different files, no dependency).

- [ ] T045 [P9] Fix `src/gamebook_web/observability/setup.py`: change `FastAPIInstrumentor().instrument()` to `FastAPIInstrumentor.instrument_app(app)`. (ADR-024, FR-029)
- [ ] T046 [P9] Wire `turn_span` in `src/gamebook_web/api/play.py` `/turn` route: wrap the handler in `turn_span(campaign_id, account_id, turn_number)`. (ADR-024, FR-030)
- [ ] T047 [P9] Wire `narrator_span` in `src/gamebook_web/harness/agent.py` narrator call: wrap the LLM call in `narrator_span()`. (ADR-024, FR-030)
- [ ] T048 [P9] Emit metrics at the appropriate call sites: `http_requests_total` (every HTTP request), `turn_duration_seconds` (after `/turn`), `active_campaigns` (on create/delete), `combat_rounds_total` (on combat round). (ADR-024, FR-030)
- [ ] T049 [P9] Fix `src/gamebook_web/observability/tracing.py` `span_set_error`: record only `type(exc).__name__` — no message, no traceback. Replace `record_exception(exc)` with a manual event or attribute override. (ADR-024, FR-031)
- [ ] T050 [P9] Fix `src/gamebook_web/api/app.py` generic exception handler: change `logger.exception(...)` to `logger.error("unhandled %s", type(exc).__name__)`. (ADR-024, FR-031)
- [ ] T051 [P9] Remove `insecure=True` from `src/gamebook_web/observability/setup.py` OTLP exporters; use TLS by default. Only set `insecure=True` when `OTLP_INSECURE=true` is explicitly set. (ADR-024, FR-032)
- [ ] T052 [P9] Add security audit logging in `src/gamebook_web/api/account.py` (sign-in/sign-out/failed auth/account deletion), `src/gamebook_web/api/sessions.py` (lease acquire/takeover/release), `src/gamebook_web/middleware/lease_guard.py` (lease validation failures), `src/gamebook_web/auth/oidc_auth.py` (JWKS fetch failures, token validation failures). Log at `INFO`/`WARNING` with opaque IDs. (FR-033)
- [ ] T053 [P9] Reject `GAMEBOOK_CORS_ORIGINS=*` at startup in `src/gamebook_web/api/app.py` when `allow_credentials=True`. (FR-034)
- [ ] T054 [P9] Add `tests/server/test_otel_instrumentation.py`: assert `turn_span`/`narrator_span` exist with correct attributes (no PII); assert `http_requests_total` incremented; assert `span_set_error` has no message/traceback; assert `instrument_app` was called. (SC-012)
- [ ] T055 [P9] Add `tests/server/test_security_audit_logging.py`: assert log lines for sign-in/out, failed auth, lease acquire/takeover/release, account deletion. (SC-015)

**Checkpoint**: OTel correctly instrumented; span helpers wired; metrics emitted;
exceptions redacted in spans and logs; OTLP defaults to TLS; security audit logging
covers all event types; CORS `*` rejected with credentials.

---

## Phase 10: ADR-028 — Combat victory path + narrator test coverage (MEDIUM/LOW, from 003 review)

**Purpose**: Unify terminal-state checking into a shared helper; fix
`request: Request = None`; key rate limiter on `account_id`; exercise
`PydanticNarrator` and `combat_subagent` with tests; `list_campaigns` includes
`name`/timestamps; dependency upper bounds; learning lessons. Fixes 003 new findings
(not already covered by 001 remediation).

**⚠️ Can run in parallel with Phases 2–9** (different files, no dependency on Phase 1
beyond the multi-tenant engine being in place).

- [ ] T085 [P10] [P] Unify terminal-state checking: extract `_check_terminal_state` (or a shared helper) from `src/gamebook_web/api/play.py` and call it from both `take_turn` and `combat_round` in `src/gamebook_web/api/combat.py` when `outcome.ended` is True. Handle both victory (adventure module's `victory_flag`) and death. (ADR-028, FR-044)
- [ ] T086 [P10] [P] Remove `= None` default from `request: Request` parameter on all rate-limited routes in `src/gamebook_web/api/play.py` and `src/gamebook_web/api/combat.py`. (FR-045)
- [ ] T087 [P10] [P] Key the rate limiter on `account_id` when authenticated in `src/gamebook_web/limiter.py`; fall back to IP only when unauthenticated. Configure trusted proxy headers (`X-Forwarded-For`). (FR-046)
- [ ] T088 [P10] [P] Update `list_campaigns` in `src/gamebook_web/api/play.py` to include `name`, `created_at`, and `updated_at` in the response for each campaign. (FR-048)
- [ ] T089 [P10] [P] Add upper bounds to floating `>=` ranges in `pyproject.toml` (e.g. `fastapi>=0.115.0,<1.0`). (FR-049)
- [ ] T090 [P10] [P] Create `docs/learning-lessons/contract_drift_requires_live_integration_test.md` — API/frontend contract drift requires a live integration test, not eyeballing field names. (FR-050)
- [ ] T091 [P10] [P] Create `docs/learning-lessons/single_shared_engine_subprocess_antipattern.md` — booting a single shared engine subprocess scoped to an env var is a multi-tenancy anti-pattern. (FR-050)
- [ ] T092 [P10] Add `tests/server/test_combat_victory.py`: win via `POST /combat/round` → campaign ended + archived; assert `_check_terminal_state` was called; assert further turns → `409`. (SC-025, FR-044)
- [ ] T093 [P10] Add `tests/server/test_narrator_integration.py`: mocked LLM producing a valid `Scene` → validation → effects → response; mocked LLM producing fabricated numbers → `ModelRetry`. (SC-026, FR-047)
- [ ] T094 [P10] Add `tests/server/test_combat_subagent.py`: delegate a combat to `combat_subagent.resolve_combat()`; verify the `CombatResult` structure and combat state update. (SC-027, FR-047)
- [ ] T095 [P10] Add `tests/server/test_rate_limiter.py`: assert rate limiter keys on `account_id` when authenticated; falls back to IP when unauthenticated. (SC-028, FR-046)

**Checkpoint**: Combat victory works via explicit route; narrator and combat subagent
tested; rate limiter keyed on account_id; `list_campaigns` complete; dependency upper
bounds; learning lessons recorded.

---

## Phase 11: SPA production hardening (HIGH/MEDIUM/LOW, from 005 review)

**Purpose**: Disable source maps in production; add CSP headers; add ErrorBoundary;
validate CombatPanel participants; 401/403 redirect to `/auth`; token expiration
checking; fix useEffect stale closure; free-text input validation; error message
sanitization; security headers; vitest upgrade. Fixes 005 blocking findings.

**⚠️ Can run in parallel with Phases 2–10** (frontend files, no dependency on backend
phases beyond the contract alignment in Phase 2).

- [ ] T097 [P11] [P] Disable source maps in production: change `sourcemap: true` to `sourcemap: false` (or `sourcemap: import.meta.env.DEV`) in `frontend/vite.config.ts`. (FR-051, SC-031)
- [ ] T098 [P11] [P] Add Content-Security-Policy meta tag to `frontend/index.html`: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'`. (FR-052, SC-032)
- [ ] T099 [P11] [P] Create `frontend/src/components/ErrorBoundary.tsx` (class component catching render errors, fallback UI with "reload" button); wrap App root in `App.tsx`. (FR-053, SC-033)
- [ ] T100 [P11] [P] Add `participants.length >= 2` validation in `frontend/src/components/CombatPanel.tsx` before accessing indices 0 and 1; render fallback if short. (FR-054, SC-034)
- [ ] T101 [P11] [P] Add 401/403 handling in `frontend/src/hooks/useGame.ts`: intercept `err.code === 'unauthenticated'` or `err.code === 'forbidden'` and redirect to `/auth`. (FR-055, SC-035)
- [ ] T102 [P11] [P] Add token expiration checking in `frontend/src/hooks/useGame.ts` (or `useAuth.ts`): parse `expires_at` from session lease and redirect to `/auth` if expired. (FR-056, SC-036)
- [ ] T103 [P11] [P] Fix useEffect stale closure in `frontend/src/hooks/useGame.ts` and `frontend/src/hooks/useCampaign.ts`: remove `load` from dependency array or wrap in `useCallback`. (FR-057)
- [ ] T104 [P11] [P] Add free-text input validation in `frontend/src/components/ChoicesPanel.tsx`: reject empty submissions (after trim), enforce max length (1000 chars), disable submit button when empty. (FR-058)
- [ ] T105 [P11] [P] Sanitize error messages in `frontend/src/hooks/useGame.ts`: show generic "Something went wrong" to users; log details to console only in dev mode. (FR-059)
- [ ] T106 [P11] [P] Add security headers to the backend response or reverse proxy: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`. (FR-060)
- [ ] T107 [P11] [P] Pin `vitest >= 3.2.6` in `frontend/package.json` to address GHSA-5xrq-8626-4rwp; run `npm install` to refresh lockfile. (FR-061)
- [ ] T108 [P11] Add `frontend/src/components/__tests__/test_error_boundary.test.tsx`: throw in child component → assert fallback UI renders. (SC-033)
- [ ] T109 [P11] Add `frontend/src/components/__tests__/test_combat_panel_validation.test.tsx`: render CombatPanel with empty/short participants → assert fallback. (SC-034)
- [ ] T110 [P11] Add `frontend/src/hooks/__tests__/test_auth_redirect.test.tsx`: mock 401 response → assert redirect to `/auth`; mock expired `expires_at` → assert redirect. (SC-035, SC-036)
- [ ] T111 [P11] Add `frontend/src/components/__tests__/test_choices_validation.test.tsx`: empty input → submit button disabled; max length enforced. (FR-058)

**Checkpoint**: SPA is production-hardened — source maps disabled, CSP present,
ErrorBoundary wraps App, CombatPanel validates, 401/403 redirects, token expiration
checked, useEffect fixed, free-text validated, errors sanitized, security headers set,
vitest upgraded.

---

## Phase 12: Postgres integration tests (CRITICAL/HIGH, from 004 + 002 reviews)

**Purpose**: Add integration tests that run against a live Postgres with
`DATABASE_URL` covering account, lease, ownership, GDPR, campaign scoping, and the
002 hardening paths (TLS, concurrency, lifecycle, snapshot, identifier validation).
Fixes the 004/002 finding that these paths lack live-DB coverage.

**⚠️ Depends on**: Phases 7–9 (the code under test must be fixed first) and Phase 6
(002 storage hardening).

- [ ] T056 [P12] Add `tests/server/test_postgres_accounts.py`: account upsert (`get_or_create`), account resolution from OIDC `sub`, account deletion with cascade. (SC-017, FR-035)
- [ ] T057 [P12] Add `tests/server/test_postgres_campaign_ownership.py`: create campaign (assert `account_id` not `NULL`); duplicate ID → `409`; list campaigns (assert from Postgres, not in-memory); delete campaign (assert row removed). (SC-010, SC-017, FR-035)
- [ ] T058 [P12] Add `tests/server/test_postgres_leases.py`: acquire/validate/takeover/release; wrong `current_token` → `409`; expiry `<=` boundary; `SELECT FOR UPDATE` concurrency. (SC-011, SC-017, FR-035)
- [ ] T059 [P12] Add `tests/server/test_postgres_gdpr.py`: export includes account + campaigns + `save_slot` snapshots; erasure removes all rows. (SC-014, SC-017, FR-035)
- [ ] T060 [P12] Add `tests/server/test_postgres_campaign_scoping.py`: two campaigns with different `campaign_id` values do not see each other's state (extends `test_multi_campaign_isolation.py` to run against live DB). (SC-002, SC-017, FR-035)
- [ ] T080 [P12] Add `tests/server/test_postgres_storage.py` (or extend existing): TLS enforcement, concurrent `append_event`, `close()` lifecycle, consistent snapshot, identifier validation. (SC-018, SC-019, SC-020, SC-021, SC-022, FR-037–FR-041)
- [ ] T081 [P12] Run the storage swap-boundary test with Postgres: `DATABASE_URL=... uv run pytest tests/qa/test_storage_swap.py -v`. (SC-023, FR-042)
- [ ] T082 [P12] Run the atomic-write test with Postgres: `DATABASE_URL=... uv run pytest tests/server/test_atomic_writes.py -v`. (SC-024, FR-043)

**Checkpoint**: All DB-backed paths covered by live Postgres integration tests,
including the 002 hardening paths.

---

## Phase 13: ADR renumbering + Verification

**Purpose**: Renumber 004 ADRs 017–019 → 022–024; create ADR-025, ADR-026, ADR-027,
ADR-028; verify all success criteria before merge.

- [ ] T061 [P13] Rename `docs/adrs/ADR-017-oidc-jwt-jwks-validation-pattern.md` → `ADR-022-oidc-jwt-jwks-validation-pattern.md`; update the ADR header number. (FR-036, ADR-020)
- [ ] T062 [P13] Rename `docs/adrs/ADR-018-session-lease-acquire-takeover-semantics.md` → `ADR-023-session-lease-acquire-takeover-semantics.md`; update the ADR header number. (FR-036, ADR-020)
- [ ] T063 [P13] Rename `docs/adrs/ADR-019-opentelemetry-auto-instrumentation.md` → `ADR-024-opentelemetry-auto-instrumentation.md`; update the ADR header number. (FR-036, ADR-020)
- [ ] T064 [P13] Create `docs/adrs/ADR-025-db-backed-campaign-registry.md` documenting the replacement of `CampaignRegistry` with `AccountRepository`. (FR-036, ADR-025)
- [ ] T083 [P13] Create `docs/adrs/ADR-026-postgres-tls-policy.md` documenting the TLS-by-default policy for PostgreSQL connections. (FR-037, ADR-026)
- [ ] T084 [P13] Create `docs/adrs/ADR-027-postgres-concurrency-and-lifecycle.md` documenting concurrency-safe event sequence allocation and deterministic `PostgresStorage` lifecycle. (FR-038, FR-039, ADR-027)
- [ ] T096 [P13] Create `docs/adrs/ADR-028-combat-terminal-state-unification.md` documenting the unification of terminal-state checking into a shared helper. (ADR-028, FR-044)
- [ ] T065 [P13] Update `CLAUDE.md` ADR table to list ADRs 014–028 exactly once each with correct numbers and titles. (SC-008, FR-016, FR-036)
- [ ] T066 [P13] Run `uv run pytest -q` (full backend suite) — must be green. (SC-006)
- [ ] T067 [P13] Run `uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q` (plugability audit) — must be green. (SC-005)
- [ ] T068 [P13] Run `cd frontend && npm test` (vitest unit suite, including new 005 tests) — must be green. (SC-007)
- [ ] T069 [P13] Run `cd frontend && npx playwright test` (e2e, including the new live-backend suite) — must be green. (SC-001)
- [ ] T070 [P13] Run `DATABASE_URL=... uv run pytest tests/server/test_postgres_*.py tests/qa/test_storage_swap.py tests/server/test_atomic_writes.py -v` (live Postgres integration tests) — must be green. (SC-017, SC-023, SC-024)
- [ ] T071 [P13] Run `/sdd-final-review` to dispatch cycle-2 (QA + Security + Tech Leader) and confirm the cycle-1 findings from all five reviews are closed.

**Checkpoint**: All success criteria met; ADR numbering clean; ready for SDD cycle-2
review.
