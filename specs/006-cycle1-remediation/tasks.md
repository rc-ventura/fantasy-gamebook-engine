---
description: "Task list for Cycle-1 Remediation — closes SDD cycle-1 findings (CRITICAL+HIGH+MEDIUM+LOW+GOVERNANCE)"
---

# Tasks: Cycle-1 Remediation

**Input**: Design documents from `specs/006-cycle1-remediation/` (spec.md, plan.md)
and ADRs 017–020. Driven by the SDD final review
`reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`.

**Prerequisites**: spec.md, plan.md; ADRs 017–020; `003-web-backend-mvp` and
`005-professional-spa` merged to `dev`.

**Tests**: Included — multi-campaign isolation (SC-002), production guards
(SC-003/SC-004), live-backend integration (SC-001), plugability audit (SC-005), full
suite (SC-006/SC-007).

**Organization**: Tasks are grouped by phase (dependency-ordered). Phase 1 blocks all
other phases (the multi-tenant refactor touches every call site).

## Format: `[ID] [P?] [Phase] Description`
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
- [ ] T019 [P3] Add `tests/server/test_production_guards.py`: assert the server raises at boot when `ENV=production` + `GAMEBOOK_DEV_MODE=1`; assert `/docs` returns 404 when `ENV=production`; assert auth failures are logged. (SC-003, SC-004)

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

**Checkpoint**: LOW findings closed; ADR numbering clean.

---

## Phase 6: Verification

**Purpose**: All success criteria verified before merge.

- [ ] T030 [P6] Run `uv run pytest -q` (full backend suite) — must be green. (SC-006)
- [ ] T031 [P6] Run `uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q` (plugability audit) — must be green. (SC-005)
- [ ] T032 [P6] Run `cd frontend && npm test` (vitest unit suite) — must be green. (SC-007)
- [ ] T033 [P6] Run `cd frontend && npx playwright test` (e2e, including the new live-backend suite) — must be green. (SC-001)
- [ ] T034 [P6] Verify `CLAUDE.md` ADR table lists ADRs 014–021 exactly once each with correct numbers and titles. (SC-008, FR-016)
- [ ] T035 [P6] Run `/sdd-final-review` to dispatch cycle-2 (QA + Security + Tech Leader) and confirm the cycle-1 findings are closed.

**Checkpoint**: All success criteria met; ready for SDD cycle-2 review.
