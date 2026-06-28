# Implementation Plan: Cycle-1 Remediation (001 + 002 + 003 + 004 + 005)

**Branch**: `006-cycle1-remediation` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-cycle1-remediation/spec.md` and five
SDD final reviews:
- `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
- `reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md`
- `reports/sdd-final-review/003-web-backend-mvp/cycle-1-20260628-1010.md`
- `reports/sdd-final-review/004-accounts-hardening-obs/cycle-1-20260628-1043.md`
- `reports/sdd-final-review/005-professional-spa/cycle-1-20260628-1223.md`

Architectural decisions are recorded in ADRs 017–028 (017–020 for the 001 remediation,
022–024 renumbered from the 004 branch, 025 new, 026–027 new for the 002 remediation,
028 new for the 003 remediation). The 005 review requires no new ADRs — its findings
are implementation bugs and configuration issues.

## Summary

Close the cycle-1 SDD findings from **all five** reviews so the web backend + SPA are
live-mode functional, multi-tenant safe, production-hardened, persistence-safe, and
SPA-hardened. The work has nine tracks:

1. **Multi-tenant engine (ADR-018, CRITICAL)**: every MCP tool gains a `campaign_id`
   parameter; `build_server` takes a `storage_factory` instead of a single storage
   instance; the web layer passes `campaign_id` on every `call_engine` call. The
   `StorageBackend` interface is unchanged (Principle II preserved).
2. **Contract alignment (ADR-017, HIGH)**: the frontend TS types conform to the
   backend Pydantic response models; `campaign_id` is the identifier everywhere; an
   integration test runs the SPA against the live backend.
3. **Production guards + cleanup (CRITICAL/MEDIUM/LOW)**: dev-auth production guard,
   `/docs` disabled in production, security event logging, victory flag moved to
   adventure-module config, `create_campaign` keeps the `name`, missing endpoints
   gated, vite pinned, dev-token aligned, CORS narrowed, allowlist for fabricated
   numbers (ADR-019), ADR renumbering (ADR-020), dependency upper bounds.
4. **Persistence foundation hardening (ADR-026/027, HIGH/MEDIUM)**: enforce TLS for
   PostgreSQL by default; make `append_event` sequence allocation concurrency-safe; add
   `PostgresStorage.close()` lifecycle; wrap `_build_snapshot` in a read-only
   transaction; validate identifiers to match `JSONStorage` parity; extend swap-boundary
   and atomic-write tests to cover Postgres.
5. **Fail-closed OIDC auth (ADR-022, CRITICAL/HIGH)**: remove dev stub from production
   path; require `OIDC_ISSUER` + `exp`; strict JWKS key binding; cache key alignment.
6. **DB-backed campaign ownership + session lease fixes (ADR-023/025, HIGH/MEDIUM)**:
   replace `CampaignRegistry` with `AccountRepository` in play routes; fix
   `create_campaign` duplicate handling; fix `_ensure_campaign` `account_id`;
   `DELETE /me` confirmation; `save_slot` in GDPR export; `takeover` validates
   `current_token`; lease expiry `<=`.
7. **Observability + PII discipline (ADR-024, HIGH/MEDIUM)**: fix FastAPI
   instrumentation; wire `turn_span`/`narrator_span`; emit metrics; redact exceptions
   in spans and logs; secure OTLP defaults; security audit logging; CORS `*` rejection.
8. **Combat victory path + narrator test coverage (ADR-028, MEDIUM/LOW, from 003)**:
   unify terminal-state checking into a shared helper called from both `take_turn` and
   `combat_round`; fix `request: Request = None` default; key rate limiter on
   `account_id`; exercise `PydanticNarrator` and `combat_subagent` with tests;
   `list_campaigns` includes `name`/timestamps; record two new learning lessons.
9. **SPA production hardening (HIGH/MEDIUM/LOW, from 005)**: disable source maps in
   production; add CSP headers; add ErrorBoundary; validate CombatPanel participants;
   401/403 redirect to `/auth`; token expiration checking; fix useEffect stale closure;
   free-text input validation; error message sanitization; security headers; vitest
   upgrade.

The 004 slice is extinct as a separate branch — all its remediation lives here. The 002,
003, and 005 slices are already merged to `dev`; their remediation is implemented
in-place.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript (frontend).

**Primary Dependencies**:
- *Existing, unchanged*: `fastmcp`, `pydantic` v2, `fastapi`, `pydantic-ai`,
  `uvicorn`, `slowapi`, `python-jose`, `opentelemetry-sdk`,
  `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`, the
  `PostgresStorage` + Alembic stack, React/Vite/Playwright.
- *No new dependencies* — this is a fix/hardening slice, not a feature slice.
  (`python-jose` is retained; migration to `PyJWT`/`authlib` is deferred per ADR-022.)

**Storage**: PostgreSQL via `PostgresStorage` (unchanged interface); the
`storage_factory` in ADR-018 constructs per-campaign `PostgresStorage` instances.
Campaign ownership and session leases are stored in Postgres via `AccountRepository`
and `LeaseService` (ADR-025, ADR-023).

**Testing**: `pytest` (backend), `vitest` + `playwright` (frontend). New tests:
`test_multi_campaign_isolation.py`, `test_production_guards.py`,
`test_oidc_fail_closed.py`, `test_otel_instrumentation.py`,
`test_security_audit_logging.py`, `test_account_endpoints.py`,
`test_postgres_accounts.py`, `test_postgres_leases.py`,
`test_postgres_campaign_ownership.py`, `test_postgres_gdpr.py`, a live-backend
Playwright suite. The 002 remediation adds/enhances: `test_postgres_storage.py`
(TLS enforcement, concurrent append, lifecycle, consistent snapshot, identifier
validation), `test_storage_swap.py` (Postgres parametrization), and
`test_atomic_writes.py` (mid-statement failure). The plugability audit stays a merge gate.

**Target Platform**: Linux server (backend); the SPA runs in any browser.

**Project Type**: web service remediation (backend + frontend).

**Performance Goals**: No new goals — the multi-tenant refactor must not regress
SC-006 (95% turns < 2s). The `storage_factory` cache avoids re-opening a Postgres
connection per call.

**Constraints**:
- Principle I (numbers never in prose) — the allowlist (ADR-019) strengthens the gate.
- Principle II (interfaces only) — `StorageBackend` is unchanged; multi-tenancy is at
  the MCP server layer.
- Principle III (CONTRACTS.md is SSOT) — §6 is updated for `campaign_id`; the HTTP API
  contract is reconciled with ADR-017.
- Principle IV (determinism + isolated testing) — the in-memory storage factory for
  tests keeps the engine testable in full isolation.
- Principle V (atomic persistence) — unaffected; per-campaign backends write atomically.

**Scale/Scope**: One process serving N campaigns (SC-005). Real OIDC auth is
fail-closed (ADR-022); the dev stub survives only in test fixtures. Campaign
ownership and session leases are DB-backed (ADR-023/025). PostgreSQL connections are
TLS-hardened by default (ADR-026); event sequence allocation and storage lifecycle are
production-safe (ADR-027).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0:

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| **I. Numbers Never in Prose** | PASS | The allowlist (ADR-019) makes the fabricated-number gate structural, not heuristic. The multi-tenant refactor does not touch the numbers flow. |
| **II. Dependency on Interfaces Only** | PASS | `StorageBackend` interface is unchanged. The `storage_factory` is a new composition-root seam, not a new interface — `build_server` takes a `Callable[[str], StorageBackend]`, which is the factory pattern already used at `main()`. The web layer still depends only on `MCPToolset`. |
| **III. CONTRACTS.md is SSOT** | PASS | §6 is updated for `campaign_id` in the same change (FR-017). The HTTP API contract is reconciled with ADR-017. No silent drift. |
| **IV. Determinism and Isolated Testing** | PASS | The in-memory `storage_factory` for tests returns per-campaign dict-backed storage; `rules` and `combat` tests stay isolated with seeded RNG. The plugability audit is extended to cover the new factory seam. |
| **V. Domain Invariants and Atomic Persistence** | PASS | Per-campaign `PostgresStorage` instances write atomically (unchanged). `JSONStorage` per-campaign directories write atomically (temp + rename, unchanged). |

## Architecture / Design

### Track 1: Multi-tenant engine (ADR-018)

**`build_server` signature change**:
```python
def build_server(
    storage_factory: Callable[[str], StorageBackend],
    combat_factory: Callable[[StorageBackend], CombatEngine],  # or a combined factory
    rng: RandomSource,
) -> FastMCP:
```
Each tool gains `campaign_id: str` as the first parameter:
```python
@server.tool(name="read_character_sheet")
def read_character_sheet(campaign_id: str) -> CharacterSheet:
    storage = storage_factory(campaign_id)
    sheet = storage.load_character()
    ...
```
The factory caches backends per campaign (a `dict[str, StorageBackend]` for the MVP;
bounded LRU with idle eviction is a future hardening concern, noted in ADR-018).

**`main()` composition root**: builds a `storage_factory` closure that, given a
`campaign_id`, returns `PostgresStorage(database_url, campaign_id)` (Phase-2) or
`JSONStorage(f"estado/{campaign_id}")` (Phase-1). The `GAMEBOOK_CAMPAIGN_ID` env var
is no longer used by the web path; the Phase-1 terminal harness path can still use it
to pick a default campaign.

**Web layer**: `call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)`
— `direct_call_tool` forwards kwargs as tool arguments, so `mcp_host.py` needs no
change beyond the call sites. Every call site in `play.py` (~15) and `combat.py` (~5)
adds `campaign_id=campaign_id`.

**Test fixtures**: `tests/server/conftest.py` provides an in-process
`storage_factory` that returns per-campaign `InMemoryStorage` instances. Existing
tests pass `campaign_id="dev-campaign"` (or a fixture-provided id).

### Track 2: Contract alignment (ADR-017)

**Frontend TS types** (`frontend/src/types/index.ts`):
- `TurnResponse` → `{ scene: Scene; character?: CharacterSheet; world?: WorldState; effects_applied: EffectResult[] }`
- `CombatRoundResponse` → `{ outcome: RoundOutcome; final_result?: FinalResult; character?: CharacterSheet; campaign_ended: boolean }`
- `FleeCombatResponse` → `{ result: FleeResult; character?: CharacterSheet; campaign_ended: boolean }`
- `CampaignSummary` → `{ campaign_id: string; status: CampaignStatus; name?: string; created_at?: string; updated_at?: string }`
- `CampaignState` → `{ campaign_id: string; status: CampaignStatus; character?: CharacterSheet; world?: WorldState; current_scene?: Scene; combat?: CombatState | null }`

**`useGame` assemblers**: `applyTurnResponse` builds `CampaignState` from
`{ campaign_id (kept from prior state), status (kept), character: res.character, world: res.world, current_scene: res.scene, combat (kept) }`. `applyCombatResponse` updates `character` and `combat` from the response fields.

**Integration test**: a new `frontend/tests/e2e/live-play-loop.spec.ts` runs against
the live backend (started in a Playwright global setup), with `VITE_USE_MOCK=false`.
It drives: create campaign → create character → take 2 turns → combat round → end.
This is the test that would have caught the contract drift.

### Track 3: Production guards + cleanup

- **Dev-auth guard** (`app.py` lifespan): `if os.getenv("ENV") == "production" and os.getenv("GAMEBOOK_DEV_MODE", "0") in ("1", "true"): raise RuntimeError("GAMEBOOK_DEV_MODE must not be enabled in production")`.
- **Docs disabled in production**: `docs_url = None if os.getenv("ENV") == "production" else "/docs"` (same for redoc, openapi).
- **Security logging**: `_unauthenticated` logs `logger.warning("auth failed: path=%s reason=%s", ...)` before raising.
- **Victory flag**: move `malachar_defeated` to an adventure-module config (e.g. a `victory_flag: str` field in the Ignarok SKILL metadata or a small `adventure_module.py` config); the API reads the flag name from config.
- **`create_campaign` name**: `CampaignState.name: str | None`; `registry.create(account_id, name=None)`; `CampaignResponse` includes `name`; `list_campaigns` includes `name`.
- **Session-lease gating**: `useGame` wraps `acquireSession` in `if (import.meta.env.VITE_SESSION_LEASE === 'true')`. Default off → no 404.
- **`GET /me`**: add a trivial `@router.get("/me")` returning `{ id: account.account_id }` (dev stub; real identity in `004`).
- **Vite pin**: `package.json` `"vite": ">=5.4.12"`.
- **Dev-token alignment**: `.env.local.example` → `VITE_DEV_TOKEN=dev-token`; `AuthPage.tsx` fallback → `dev-token`.
- **CORS narrowing**: `allow_methods=["GET","POST","DELETE","OPTIONS"]`, `allow_headers=["Content-Type","Authorization"]`.
- **Allowlist (ADR-019)**: replace `_RESULT_KEYS` with `_ALLOWED_EFFECT_PARAMS` in `agent.py`; extend prose regex.
- **ADR renumbering (ADR-020)**: rename the pydantic-ai ADR file to ADR-021; delete the two "moved" stubs; update `CLAUDE.md` and the learning-lesson cross-link. Renumber the 004 branch ADRs 017–019 → 022–024; create ADR-025 (DB-backed campaign registry).

### Track 4: Persistence foundation hardening (ADR-026/027)

**`src/gamebook/storage/postgres.py`**:
- Enforce TLS by default (`sslmode=require` or `ssl=True`). Add a non-production
  override env var (e.g., `POSTGRES_SSL_MODE=disable`) for local development. Reject
  plaintext URLs in production.
- Make `append_event` sequence allocation concurrency-safe: use
  `SELECT MAX(seq) FROM event WHERE campaign_id = :cid FOR UPDATE`, an advisory lock,
  or a generated sequence. Remove/correct the misleading inline comment.
- Add a `close()` method that disposes the engine and stops the daemon event loop.
- Wrap `_build_snapshot` in an explicit read-only transaction so `save_slot` captures
  a consistent snapshot.
- Validate string identifiers (`slot`, `combat_id`) to match `JSONStorage` parity.

**`tests/server/test_postgres_storage.py`**: add/enhance tests for TLS enforcement,
concurrent append, `close()` lifecycle, consistent snapshot, and identifier validation.

**`tests/qa/test_storage_swap.py`**: parametrize the consumer-level swap-boundary test
with `PostgresStorage` when `DATABASE_URL` is present.

**`tests/server/test_atomic_writes.py`**: simulate a failure after at least one
`session.execute()` has run, proving no partial data is committed.

**`docs/CONTRACTS.md` §11**: update the storage contract to reflect TLS, concurrency,
and lifecycle requirements.

### Track 5: Fail-closed OIDC auth (ADR-022)

**`app.py` lifespan**: when `OIDC_JWKS_URI` is unset and `GAMEBOOK_DEV_MODE` is not
explicitly enabled, raise `RuntimeError` (or install a dependency override that
returns `401` for every request). The current fallback to `dev_auth` is removed.

**`dev_auth.py`**: `DEV_TOKEN = "dev-token"` is moved to a test-fixture-only location
(e.g. `tests/server/conftest.py` or a `test_constants.py`). The production `dev_auth`
module either does not define `DEV_TOKEN` or defines it only when
`GAMEBOOK_DEV_MODE=1` is explicitly set in a non-production environment.

**`oidc_auth.py`**:
- `OIDC_ISSUER` has no empty-string default; if unset when OIDC is active, raise at
  startup. `verify_iss=True` always.
- JWT decode requires `exp`; tokens without `exp` → `401`.
- When `kid` is missing from the JWT header → `401` (no fallback to first JWKS key).
- Validated-token cache key: `sha256(token)[:16] + str(exp)` (not full SHA-256).

**Tests**: `test_oidc_fail_closed.py` — boot without `OIDC_JWKS_URI` (assert
refusal); send JWT without `exp` (assert `401`); send JWT without `kid` (assert
`401`); send JWT with wrong `iss` (assert `401`); inspect cache key format.

### Track 6: DB-backed campaign ownership + session lease fixes (ADR-023/025)

**`play.py`**: `create_campaign`, `list_campaigns`, `get_campaign`, `delete_campaign`
call `AccountRepository` methods instead of `CampaignRegistry`. The in-memory registry
is removed or reduced to a transient cache for `current_scene_id`/`combat_id` (if
needed at all — these may live in the engine state).

**`accounts.py`**: `create_campaign` raises `409` on duplicate `campaign_id`; always
sets `account_id` on the campaign row. `export_account` includes `save_slot` snapshots.

**`postgres.py`**: `_ensure_campaign` inserts campaign rows with the correct
`account_id` (passed from the caller, not `NULL`).

**`account.py`**: `DELETE /me` returns `404` if the account does not exist; requires
a `confirmation` field in the request body (a token or password re-entry). Without
it → `400`.

**`lease.py`**: `takeover` validates `current_token` against the current holder
before force-acquiring. Wrong/missing → `409`. `acquire` and `validate` use `<=`
for expiry check (not `<`).

**Tests**: `test_postgres_campaign_ownership.py` (create/list/get/delete against
live DB; duplicate → `409`; `account_id` not `NULL`), `test_postgres_leases.py`
(acquire/validate/takeover/release; wrong `current_token` → `409`; expiry `<=`),
`test_account_endpoints.py` (`DELETE /me` `404`/`400`/`204`; `GET /me/export`
includes `save_slot`), `test_postgres_gdpr.py` (export/erasure against live DB).

### Track 7: Observability + PII discipline (ADR-024)

**`observability/setup.py`**: `FastAPIInstrumentor().instrument()` →
`FastAPIInstrumentor.instrument_app(app)`. OTLP exporters: remove `insecure=True`
default; use TLS unless `OTLP_INSECURE=true` is explicitly set for local dev.

**`observability/tracing.py`**: `span_set_error` sets span status to `ERROR` with
only `type(exc).__name__` as an attribute — no `record_exception(exc)` call (or
override the attributes after calling it to strip message/traceback).

**`api/play.py` `/turn` route**: wrap handler in `turn_span(campaign_id, account_id,
turn_number)`. After the turn, record `turn_duration_seconds` and increment
`combat_rounds_total` if combat was involved. Increment `active_campaigns` on
campaign creation, decrement on deletion.

**`harness/agent.py` narrator call**: wrap in `narrator_span()`.

**`api/app.py`**: generic exception handler changes `logger.exception(...)` to
`logger.error("unhandled %s", type(exc).__name__)`. CORS config rejects
`GAMEBOOK_CORS_ORIGINS=*` at startup when `allow_credentials=True`.

**Security audit logging**: `account.py` logs sign-in/sign-out/failed auth/account
deletion at `INFO`/`WARNING` with opaque IDs. `sessions.py` logs lease
acquire/takeover/release. `lease_guard.py` logs lease validation failures.
`oidc_auth.py` logs JWKS fetch failures and token validation failures.

**Tests**: `test_otel_instrumentation.py` (assert `turn_span`/`narrator_span` exist
with correct attributes; assert `http_requests_total` incremented; assert
`span_set_error` has no message/traceback; assert `instrument_app` was called),
`test_security_audit_logging.py` (assert log lines for each event type),
`test_production_guards.py` extended (CORS `*` rejection, OTLP TLS default).

### Track 8: Combat victory path + narrator test coverage (ADR-028, from 003 review)

**`combat.py`**: `combat_round` route calls `_check_terminal_state` (or a shared
terminal-check helper extracted from `play.py`) when `outcome.ended` is True. The
helper handles both victory (adventure module's `victory_flag`) and death, archives
appropriately, and marks the campaign as ended. The same helper is used by
`take_turn` in `play.py` — no duplication.

**`play.py` / `combat.py`**: remove `= None` default from `request: Request`
parameter on all rate-limited routes.

**`limiter.py`**: key the rate limiter on `account_id` when authenticated (fall back
to IP only when unauthenticated). Configure trusted proxy headers
(`X-Forwarded-For`) for behind-LB deployments.

**`play.py` `list_campaigns`**: include `name`, `created_at`, and `updated_at` in the
response for each campaign.

**`pyproject.toml`**: cap floating `>=` ranges with upper bounds
(e.g. `fastapi>=0.115.0,<1.0`).

**Tests**: `test_combat_victory.py` (win via `POST /combat/round` → campaign ended +
archived), `test_narrator_integration.py` (mocked LLM → valid `Scene` → validation →
effects → response; fabricated numbers → `ModelRetry`), `test_combat_subagent.py`
(delegate combat → verify `CombatResult`), `test_rate_limiter.py` (keyed on
`account_id` when authenticated).

**Learning lessons**: `docs/learning-lessons/contract_drift_requires_live_integration_test.md`
and `docs/learning-lessons/single_shared_engine_subprocess_antipattern.md`.

### Track 9: SPA production hardening (from 005 review)

**`frontend/vite.config.ts`**: set `sourcemap: false` (or `sourcemap: import.meta.env.DEV`)
so production builds do not expose source code.

**`frontend/index.html`**: add a Content-Security-Policy meta tag restricting
`script-src 'self'`, `style-src 'self' 'unsafe-inline'`, `connect-src 'self'`.

**`frontend/src/components/ErrorBoundary.tsx`** (new): a React ErrorBoundary class
component that catches render errors and displays a fallback UI with a "reload" button.
Wraps the App root in `App.tsx`.

**`frontend/src/components/CombatPanel.tsx`**: validate `participants.length >= 2`
before accessing indices 0 and 1; render a fallback message if the array is too short.

**`frontend/src/hooks/useGame.ts`**: intercept `err.code === 'unauthenticated'` or
`err.code === 'forbidden'` and redirect to `/auth`. Parse `expires_at` from the session
lease and redirect to `/auth` if expired. Remove `load` from `useEffect` dependency
array (or wrap in `useCallback`). Sanitize error messages displayed to users (generic
message, details to console only in dev).

**`frontend/src/hooks/useCampaign.ts`**: same `useEffect` dependency fix.

**`frontend/src/components/ChoicesPanel.tsx`**: reject empty submissions (after trim)
and enforce a max length (e.g. 1000 chars). Disable the submit button when input is
empty.

**Backend or reverse proxy**: set `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.

**`frontend/package.json`**: pin `vitest >= 3.2.6` (GHSA-5xrq-8626-4rwp, CRITICAL
dev-only).

**Tests**: `test_error_boundary.test.tsx` (throw in child → fallback UI),
`test_combat_panel_validation.test.tsx` (short participants → fallback),
`test_auth_redirect.test.tsx` (401 → redirect to `/auth`; expired token → redirect),
`test_choices_validation.test.tsx` (empty input → disabled button).

## Complexity Tracking

| Complexity | Description | Simpler rejected alternative |
|---|---|---|
| `storage_factory` seam in `build_server` | New `Callable[[str], StorageBackend]` parameter; per-campaign cache | Single storage + env-var campaign (rejected: causes the CRITICAL cross-account leak) |
| `campaign_id` on every MCP tool | 18 tool signatures change; CONTRACTS.md §6 update | Subprocess per campaign (rejected: heavy at 1k campaigns, ADR-018 option 1) |
| Frontend `CampaignState` assembly | `useGame` composes state from granular fields instead of reading `res.campaign` | Backend aggregates `campaign` per response (rejected: backend re-reads full state every turn) |
| Allowlist per effect type | `_ALLOWED_EFFECT_PARAMS` mapping + validator rewrite | Expand the denylist (rejected: whack-a-mole, ADR-019 option 1) |
| Fail-closed OIDC | Remove dev stub fallback; require `OIDC_ISSUER`+`exp`; strict `kid` binding | Keep the fallback with a warning (rejected: CRITICAL A07 — silent insecure deployment) |
| DB-backed campaign registry | Replace `CampaignRegistry` with `AccountRepository` in all play routes | Keep in-memory registry for dev, DB for prod (rejected: split ownership is the root cause of the 004 findings) |
| `takeover` validates `current_token` | `LeaseService.takeover` checks the current holder before force-acquire | Remove `current_token` from the contract (rejected: the contract is the SSOT; fixing the implementation is correct) |
| OTel instrumentation fix | `instrument_app(app)` + wire span helpers + emit metrics | Leave as-is (rejected: HIGH finding — observability code is dead weight without wiring) |
| PII redaction in spans/logs | `span_set_error` records only class name; handler logs type only | Keep `record_exception` (rejected: MEDIUM A05/A09 — leaks PII and internal details) |
| Postgres TLS default-on | `sslmode=require`/`ssl=True` in `PostgresStorage`; override only for local dev | Accept plaintext URLs (rejected: HIGH A02/A05) |
| Concurrency-safe event seq | `FOR UPDATE` / advisory lock / generated sequence in `append_event` | Keep `SELECT MAX(seq)` with misleading comment (rejected: MEDIUM A04 — duplicate seq under concurrency) |
| PostgresStorage lifecycle | `close()` disposes engine + stops daemon thread | Rely on process exit (rejected: MEDIUM QA — leaks threads/connections in tests and long runs) |
| Consistent snapshot reads | `_build_snapshot` in read-only transaction | Multi-table reads without boundary (rejected: MEDIUM A04 — inconsistent snapshot under concurrency) |
| Combat terminal-state unification | Shared `_check_terminal_state` helper called from both `take_turn` and `combat_round` | Inline victory branch in `combat_round` (rejected: duplicates logic, future drift) |
| Rate limiter keying on account_id | Key on `account_id` when authenticated; fall back to IP when unauthenticated | Keep IP-only keying (rejected: MEDIUM A05 — NAT/proxy issues) |
| Narrator integration test | Mocked LLM produces `Scene` → validation → effects → response | Real LLM test (rejected: non-deterministic, out of scope) |
| SPA source maps | `sourcemap: false` in production; dev-only conditional | Keep `sourcemap: true` always (rejected: HIGH A05 — exposes source code) |
| CSP headers | Meta tag in `index.html` or backend header | No CSP (rejected: HIGH A05 — allows inline scripts/eval) |
| ErrorBoundary | Class component wraps App root | No error boundary (rejected: HIGH QA — blank screen on render error) |

## Action Items

- [ ] CONTRACTS.md §6 updated for `campaign_id` (FR-017, Principle III)
- [ ] HTTP API contract draft reconciled with ADR-017 canonical shapes
- [ ] ADRs 017–028 linked from `CLAUDE.md` ADR table; ADR-021 (renamed pydantic-ai) listed; 004 ADRs renumbered 022–024; ADR-025 created; ADR-026, ADR-027, ADR-028 created
- [ ] `docs/learning-lessons/pydantic_ai_v2_mcp_toolset_direct_call_pattern.md` cross-link updated to ADR-021
- [ ] SDD cycle-1 reports (001 + 002 + 003 + 004 + 005) referenced from the remediation spec
- [ ] ADR-022 (OIDC fail-closed) created/renumbered from 004's ADR-017
- [ ] ADR-023 (session lease) created/renumbered from 004's ADR-018
- [ ] ADR-024 (OTel) created/renumbered from 004's ADR-019
- [ ] ADR-025 (DB-backed campaign registry) created
- [ ] ADR-026 (PostgreSQL TLS policy) created
- [ ] ADR-027 (PostgresStorage concurrency + lifecycle) created
- [ ] ADR-028 (combat terminal-state unification) created
- [ ] Two new learning lessons created (contract drift + single-shared-engine antipattern)
- [ ] 005 SPA hardening items tracked as FR-051–FR-061 and SC-031–SC-036

## Pre-Implementation High-Level Task Breakdown

See [tasks.md](./tasks.md) for the ordered, dependency-grouped task list. Phases:

1. **Phase 1 — ADR-018 multi-tenant engine** (CRITICAL, blocks everything): `build_server` + tool signatures + `main()` + web call sites + test fixtures.
2. **Phase 2 — ADR-017 contract alignment** (HIGH): frontend TS types + `useGame` assemblers + integration test.
3. **Phase 3 — Production guards** (CRITICAL/HIGH): dev-auth guard + docs disable + security logging + CORS `*` rejection.
4. **Phase 4 — MEDIUM fixes (001)**: victory flag, `create_campaign` name, session-lease gating, `GET /me`, vite pin.
5. **Phase 5 — LOW + GOVERNANCE (001)**: dev-token, CORS narrowing, allowlist (ADR-019), ADR renumbering (ADR-020).
6. **Phase 6 — Persistence foundation hardening (ADR-026/027, HIGH/MEDIUM)**: Postgres TLS, concurrency-safe `append_event`, `PostgresStorage.close()`, consistent snapshot reads, identifier validation, swap-boundary/atomic-write tests.
7. **Phase 7 — Fail-closed OIDC (ADR-022, CRITICAL/HIGH)**: remove dev stub fallback, require `OIDC_ISSUER`+`exp`, strict `kid`, cache key alignment.
8. **Phase 8 — DB-backed campaign ownership + lease fixes (ADR-023/025, HIGH/MEDIUM)**: replace `CampaignRegistry`, fix `create_campaign`/`_ensure_campaign`, `DELETE /me` confirmation, `save_slot` in export, `takeover` validates `current_token`, lease expiry `<=`.
9. **Phase 9 — Observability + PII discipline (ADR-024, HIGH/MEDIUM)**: `instrument_app(app)`, wire span helpers, emit metrics, redact exceptions, secure OTLP, security audit logging.
10. **Phase 10 — Combat victory path + narrator tests (ADR-028, MEDIUM/LOW, from 003)**: unify terminal-state checking, fix `request: Request = None`, rate limiter keying, narrator/combat subagent tests, `list_campaigns` fields, dependency upper bounds, learning lessons.
11. **Phase 11 — SPA production hardening (HIGH/MEDIUM/LOW, from 005)**: source maps disabled, CSP headers, ErrorBoundary, CombatPanel validation, 401/403 redirect, token expiration, useEffect fix, free-text validation, error sanitization, security headers, vitest upgrade.
12. **Phase 12 — Postgres integration tests (CRITICAL/HIGH)**: account, lease, ownership, GDPR, campaign scoping, storage hardening against live DB.
13. **Phase 13 — Verification**: full suite + plugability audit + live Playwright + multi-campaign isolation + all new tests.
