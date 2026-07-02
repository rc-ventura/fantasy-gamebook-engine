# Feature Specification: Cycle-1 Remediation (001 + 002 + 003 + 004 + 005)

**Feature Branch**: `006-cycle1-remediation`

**Created**: 2026-06-28

**Status**: Active — absorbing 2026-07-01 architectural decisions (D1: backend-scoped campaign management; D2: ADR-018 Option A confirmed; ADR-019 + ADR-028 superseded by ADR-029)

**Epic**: `001-web-platform-migration` — remediation slice addressing the SDD final
review cycle-1 findings from **five** blocked/conditional slices:

1. `001-web-platform-migration` (report:
   `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`) —
   2 CRITICAL, 5 HIGH, 5 MEDIUM, 3 LOW/GOVERNANCE.
2. `002-persistence-foundation` (report:
   `reports/sdd-final-review/002-persistence-foundation/cycle-1-20260628-1113.md`) —
   0 CRITICAL, 1 HIGH, 2 MEDIUM, 4 LOW/QA.
3. `003-web-backend-mvp` (report:
   `reports/sdd-final-review/003-web-backend-mvp/cycle-1-20260628-1010.md`) —
   3 CRITICAL, 5 HIGH, 5 MEDIUM, 4 LOW (re-verifies 001 findings + new items).
4. `004-accounts-hardening-obs` (report:
   `reports/sdd-final-review/004-accounts-hardening-obs/cycle-1-20260628-1043.md`) —
   3 CRITICAL, 5 HIGH, 8 MEDIUM, 3 LOW.
5. `005-professional-spa` (report:
   `reports/sdd-final-review/005-professional-spa/cycle-1-20260628-1223.md`) —
   PASS WITH CONDITIONS: 4 HIGH (2 sec + 2 QA), 4 MEDIUM, 11 LOW/deferred.

Depends on `002-persistence-foundation`, `003-web-backend-mvp`, `005-professional-spa`
(merged to `dev`), and `feat/004-auth-obs` (the auth/accounts/lease/observability
implementation that was reviewed and returned BLOCKED). The 004 implementation work is
absorbed into this slice — its ADRs are renumbered 022–024 and its findings are
remediated here.

**Input**: The five SDD final reviews returned **BLOCKED** (001–004) or **PASS WITH
CONDITIONS** (005). The architectural decisions are recorded as ADRs 017–028 (017–020
created for the 001 remediation, 022–024 renumbered from the 004 branch, 025 new,
026–027 new for the 002 remediation, 028 new for the 003 remediation). The 005 findings
are implementation bugs and configuration issues — no new ADR is needed. This spec
covers the **implementation work** that follows from those decisions plus the
non-architectural fixes. The 004 slice is **extinct as a separate branch** — all its
remediation lives here. The 002, 003, and 005 slices are already merged to `dev`; their
remediation is implemented in-place on the 006 branch.

## Overview

Close the cycle-1 findings from all five reviews so the web backend + SPA are
**live-mode functional, multi-tenant safe, production-hardened, persistence-safe, and
SPA-hardened**. The scope spans seven areas:

1. **Multi-tenant engine + contract alignment (from 001/003 reviews)**: the engine is
   scoped per `campaign_id` (ADR-018); the frontend types conform to the backend
   (ADR-017); the SPA plays against the live backend.
2. **Persistence foundation hardening (from 002 review)**: PostgreSQL connections are
   TLS-enforced by default (ADR-026); event sequence allocation is concurrency-safe
   (ADR-027); `PostgresStorage` has deterministic lifecycle cleanup; snapshots are
   read consistently; swap-boundary tests cover the Postgres backend.
3. **Auth/accounts/lease hardening (from 004 review)**: OIDC auth is fail-closed
   (ADR-022); the dev stub is removed from the production path; campaign ownership is
   DB-backed (ADR-025); session lease semantics match the contract (ADR-023).
4. **Observability + PII discipline (from 004 review)**: OTel is correctly
   instrumented (ADR-024); metrics are emitted; no raw tracebacks or PII leak into
   spans or logs; security audit logging covers auth, lease, and destructive
   operations.
5. **Combat victory path + narrator test coverage (from 003 review)**: the explicit
   combat round route handles victory as well as death (ADR-028); the
   `PydanticNarrator` live path and `combat_subagent.py` are exercised by tests
   (SC-005); the rate limiter is keyed on account_id.
6. **Production guards + cleanup (from 001/003 reviews)**: dev-auth production guard,
   `/docs` disabled in production, security event logging, victory flag moved to
   adventure-module config, `create_campaign` keeps the `name`, missing endpoints
   gated, vite pinned, dev-token aligned, CORS narrowed, allowlist for fabricated
   numbers (ADR-019), ADR renumbering (ADR-020), dependency upper bounds.
7. **SPA production hardening (from 005 review)**: source maps disabled in production;
   Content-Security-Policy headers; ErrorBoundary component; CombatPanel participants
   validation; 401/403 redirect to `/auth`; token expiration checking; useEffect
   stale-closure fix; free-text input validation; error message sanitization; security
   headers; vitest upgrade.

The scope is deliberately bounded: **no new features**, only fixes, refactor, and
the hardening of the 002 and 004 implementations. Production guards, Postgres
integration tests, and ADR renumbering are included to leave the slice in a clean,
deployable state.

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

### Governance findings (001 review)

- Duplicate ADR numbers: `ADR-014` is shared by the Postgres sync/async bridge and the
pydantic-ai MCPToolset pattern; two "moved" stubs remain in `docs/adrs/`. The
`CLAUDE.md` table perpetuates the ambiguity. This is addressed by ADR-020.

### QA findings (004 review — selected)

- **Coverage at 61%**: uncovered critical paths include JWKS key rotation, account
  upsert against live DB, DB campaign creation, GDPR export, DB-backed `/me`
  endpoints, DB-backed session endpoints, lease acquire/validate/renew, lease guard
  middleware, OTLP exporter, span helpers, and the entire `PostgresStorage` backend.
- **HIGH**: production auth falls back to the dev stub when `OIDC_JWKS_URI` is unset;
  a single known `dev-token` bypasses authentication.
- **HIGH**: campaign ownership/registry is still in-memory; the DB-backed
  `AccountRepository` campaign methods are dead code, not wired into play routes.
- **HIGH**: OpenTelemetry FastAPI auto-instrumentation is ineffective
  (`FastAPIInstrumentor().instrument()` called without the app); no request/turn
  metrics are wired.
- **MEDIUM**: `span_set_error` records the full exception (message + traceback),
  violating the no-PII rule.
- **MEDIUM**: `LeaseService.takeover` ignores `current_token` and always
  force-acquires.
- **MEDIUM**: `AccountRepository.create_campaign` silently ignores duplicate IDs.
- **MEDIUM**: `DELETE /me` returns 204 even if the account does not exist.
- **MEDIUM**: `GET /me/export` omits `save_slot` snapshots.
- **MEDIUM**: `PostgresStorage._ensure_campaign` inserts campaign rows with
  `account_id = NULL`, breaking session ownership for DB-created campaigns.
- **LOW**: validated-token cache uses full SHA-256 instead of `sha256(token)[:16]`.
- **LOW**: `LeaseService.acquire` treats `expires_at == now()` as still valid
  (`<` instead of `<=`).

### Security findings (004 review — selected)

- **CRITICAL A07**: hardcoded `DEV_TOKEN = "dev-token"` and `GAMEBOOK_DEV_MODE` env
  flag bypass real OIDC validation entirely.
- **CRITICAL A07**: production falls back to the dev auth stub when `OIDC_JWKS_URI`
  is unset; the static `dev-token` is then sufficient to authenticate.
- **CRITICAL A04**: engine toolset is singleton-scoped to `GAMEBOOK_CAMPAIGN_ID`; the
  web API serves arbitrary `campaign_id` routes but all engine calls read/write the
  same engine campaign — cross-campaign/cross-account data leakage. *(Already
  addressed by ADR-018 in the 001 remediation track.)*
- **HIGH A07**: `OIDC_ISSUER` defaults to empty string and issuer verification is
  skipped when unset.
- **HIGH A07**: JWT decode does not require the `exp` claim; a valid token without
  `exp` could be accepted indefinitely.
- **HIGH A04**: `DELETE /me` deletes the entire account and all game data without
  confirmation, MFA, or rate limiting.
- **MEDIUM A02**: OIDC key selection falls back to the first JWKS key when `kid` is
  missing.
- **MEDIUM A02/A05**: OTLP gRPC exporter uses `insecure=True`, sending telemetry
  without TLS.
- **MEDIUM A05/A09**: `span.record_exception()` records the full exception message
  and stack trace; generic handler logs full traceback via `logger.exception`.
- **MEDIUM A05**: `/docs`, `/redoc`, `/openapi.json` exposed by default in production.
  *(Already addressed by FR-009.)*
- **MEDIUM A05**: CORS can be configured with `*` origins while
  `allow_credentials=True`.
- **MEDIUM A04**: `POST /campaigns/{id}/session/takeover` accepts `current_token` but
  ignores it; any session of the same account can force-displace the lease.
- **MEDIUM A09**: no security audit logs for sign-in/out, failed auth, lease
  acquire/takeover/release, or account deletion.
- **Dependency risk**: `python-jose@3.5.0` is a high-risk JWT component; a public
  bypass of the CVE-2024-33663 guard via DER-encoded keys has been reported. Consider
  migrating to `PyJWT` or `authlib`.

### Governance findings (004 review)

- The `feat/004-auth-obs` branch created ADRs 017–019 (OIDC, session lease, OTel)
  which collide with the 006 ADRs 017–019 (contract, multi-tenant, allowlist). The
  004 ADRs are renumbered to 022–024 when absorbed into this slice. This is addressed
  by ADR-020 (extended).

### QA findings (002 review — selected)

- **Coverage at 85–90%**: the raw CRUD surface is well-covered, but the consumer-level
  swap-boundary test (`tests/qa/test_storage_swap.py`) does **not** include
  `PostgresStorage`, so ADR-009 is not proven for the new backend. The atomic-write
  test raises before any `execute()`, so it does not prove a mid-statement failure
  leaves no partial data.
- **MEDIUM**: `append_event` claims “no race condition because we hold the row-level
  lock via the INSERT”, but the `SELECT MAX(seq)` subquery is not locked. Under
  concurrency, two writers can read the same `MAX`, both try to insert the same `seq`,
  and one rolls back on the unique constraint. The comment is misleading and there is
  no retry.
- **MEDIUM**: `PostgresStorage` engines/event-loop threads are never disposed/closed.
  Per-test fixtures create new engines and daemon threads without teardown, leaking
  DB connections and threads in live-Postgres runs. The production MCP server also
  relies on process exit to clean up.
- **LOW**: `save_slot`, `load_slot`, `load_combat`, `remove_combat` do not validate
  string identifiers. Unlike `JSONStorage`, `PostgresStorage` accepts empty strings and
  raises an obscure SQLAlchemy error on `None`, creating a behavioral parity gap.

### Security findings (002 review — selected)

- **HIGH A02/A05**: PostgreSQL engine is created without TLS/SSL enforcement
  (`create_async_engine(url, pool_pre_ping=True)`). If `DATABASE_URL` omits
  `sslmode=require`, database credentials and all game state/campaign data travel in
  plaintext.
- **MEDIUM A04**: `append_event` sequence allocation is not concurrency-safe despite
  the comment claiming otherwise. The current single-threaded private event loop
  mitigates this for the stdio MCP server, but the design is unsafe for multi-writer
  deployments.
- **MEDIUM A04**: `_build_snapshot` reads mutable campaign state across multiple
  tables without an explicit transaction boundary, so the snapshot used by `save_slot`
  may be inconsistent under concurrent modification.

### QA findings (003 review — selected, new items beyond 001 re-verification)

The 003 review re-verifies all 001 findings against the current `dev` code (all still
present). The following are **new findings** not already captured by the 001 review:

- **MEDIUM**: Explicit combat round route (`POST /combat/round`) only handles hero
  death (`winner == "enemy"`); it never calls `_check_terminal_state` on victory
  (`winner == "hero"`). Winning the final boss via the explicit combat route never
  triggers victory archiving / campaign end. Victory is only checked inside
  `take_turn` via `_check_terminal_state`.
- **MEDIUM**: `request: Request = None` default on rate-limited routes is
  non-standard; slowapi's `@limiter.limit()` expects a non-null `Request` to extract
  the client IP. Works under TestClient but is fragile under other call paths.
- **LOW**: `combat_subagent.py` and `PydanticNarrator` live path have **zero test
  coverage** — production-only code paths are unverified (blocks SC-005).
- **LOW**: `list_campaigns` response omits `name` and timestamps
  (`created_at`/`updated_at`) that the frontend `CampaignSummary` type expects.

### Security findings (003 review — selected, new items beyond 001 re-verification)

- **MEDIUM A05**: Rate limiter keyed on `get_remote_address` only. Behind a load
  balancer/proxy without trusted `X-Forwarded-For` handling, all traffic shares one
  IP key — either a single attacker exhausts the bucket for everyone, or NAT'd users
  are collectively throttled. No per-account/per-token keying despite an
  authenticated API.
- **Dependency risk**: All Python deps use floating `>=` ranges with no upper bound
  (`fastapi>=0.115.0`, `sqlalchemy>=2.0.0`, `uvicorn>=0.32.0`, `mcp>=1.28.0`, etc.).
  A future major release can introduce breaking/insecure behavior with no lockfile
  gate. Recommend pinning or adding upper bounds.

### Governance findings (003 review)

- **New ADR needed**: A decision record for the **combat victory path gap** — the
  explicit `POST /combat/round` route only handles hero death, never victory, and
  does not call `_check_terminal_state`. This is a logic gap that warrants its own
  decision (whether to unify terminal-state checking into a shared helper called from
  both `take_turn` and `combat_round`). Addressed by ADR-028.
- **New learning lessons needed**: (1) API/frontend contract drift requires a live
  integration test, not eyeballing field names; (2) booting a single shared engine
  subprocess scoped to an env var is a multi-tenancy anti-pattern — per-call
  `campaign_id` is mandatory from the start.

### QA findings (005 review — selected)

The 005 review returned **PASS WITH CONDITIONS** — the SPA is functionally working but
lacks production hardening and comprehensive test coverage. The following are the
blocking and significant findings:

- **HIGH**: Missing ErrorBoundary — no global error boundary to catch React render
  errors. `frontend/src/App.tsx:1-51`.
- **HIGH**: CombatPanel assumes `participants` array has at least 2 elements without
  validation. `frontend/src/components/CombatPanel.tsx:79-80`.
- **MEDIUM**: `useEffect` dependency on `load` in `useGame`/`useCampaign` could cause
  stale closures if `load` changes. `frontend/src/hooks/useGame.ts:98-107`,
  `frontend/src/hooks/useCampaign.ts:45-47`.
- **MEDIUM**: Session lease release on unmount is best-effort only — errors silently
  ignored. `frontend/src/hooks/useGame.ts:102-106`.
- **MEDIUM**: No input validation on free-text field — could accept empty/malformed
  input. `frontend/src/components/ChoicesPanel.tsx:82-88`.
- **LOW**: TypeScript types manually defined instead of generated from OpenAPI contract.
  *(Already tracked as Out of Scope — future hardening slice.)*

### Security findings (005 review — selected)

- **HIGH A05**: Source maps enabled in production builds (`sourcemap: true`) — exposes
  source code to attackers. `frontend/vite.config.ts:36`.
- **HIGH A05**: No Content-Security-Policy headers configured — allows inline scripts,
  eval, external resource loading. `frontend/index.html:1-24`.
- **MEDIUM A01**: No handling of 401/403 auth errors — app shows generic error instead
  of redirecting to login. `frontend/src/hooks/useGame.ts:79-95`.
- **MEDIUM A07**: No token expiration handling — session lease `expires_at` not checked
  or auto-refreshed. `frontend/src/hooks/useGame.ts:65-76`.
- **MEDIUM A02**: Auth tokens stored in sessionStorage (XSS-exposed) — dev auth stub;
  acceptable until slice 004 OIDC. *(Addressed by 004 OIDC migration; sessionStorage
  replacement deferred to future slice.)*
- **LOW A09**: Error messages displayed to users without sanitization — could leak
  sensitive backend details. `frontend/src/hooks/useGame.ts:92-94, 133-135, 153-155`.
- **Dependency**: `vitest@^2.0.5` (CRITICAL, CVSS 9.8, GHSA-5xrq-8626-4rwp) — devDependency
  only, not shipped to production. `vite@^5.4.1` (HIGH, GHSA-fx2h-pf6j-xcff) — already
  addressed by FR-011 (pin to `>=5.4.12`).

### Governance findings (005 review)

- The 005 Tech Leader noted that the 006 spec (at the time of review) did **not**
  explicitly track the 005-specific items (source maps, CSP, ErrorBoundary, CombatPanel
  validation, 401/403 handling, token expiration). This update folds those items into
  the 006 spec.
- No new ADR needed — all 005 findings are implementation bugs and configuration
  issues, not architectural decisions.

| ADR | Decision | Finding addressed |
|---|---|---|
| [ADR-017](../../docs/adrs/ADR-017-api-frontend-contract-canonical-shape.md) | Backend Pydantic models are canonical; frontend TS types conform | 001 HIGH Bugs #1–4, #6 |
| [ADR-018](../../docs/adrs/ADR-018-multi-tenant-engine-per-call-campaign-id.md) | Every MCP tool gains `campaign_id`; `build_server` takes a `storage_factory` | 001 CRITICAL A01, 004 CRITICAL A04 |
| [ADR-019](../../docs/adrs/ADR-019-allowlist-for-fabricated-number-detection.md) | Allowlist of legal param keys per effect type replaces the denylist | 001 LOW `_RESULT_KEYS` |
| [ADR-020](../../docs/adrs/ADR-020-resolve-duplicate-adr-numbering.md) | Renumber colliding ADR-014 (pydantic-ai) → ADR-021; delete "moved" stubs; renumber 004 ADRs 017–019 → 022–024 | 001 + 004 GOVERNANCE |
| [ADR-022](../../docs/adrs/ADR-022-oidc-jwt-jwks-validation-pattern.md) | OIDC JWT/JWKS validation + graceful degradation; fail-closed when OIDC not configured | 004 CRITICAL A07, HIGH A07 |
| [ADR-023](../../docs/adrs/ADR-023-session-lease-acquire-takeover-semantics.md) | Session lease — single active session per campaign; `takeover` validates `current_token` | 004 MEDIUM A04, MEDIUM |
| [ADR-024](../../docs/adrs/ADR-024-opentelemetry-auto-instrumentation.md) | OTel auto-instrumentation + no-PII-in-spans; `instrument_app(app)`; metrics emitted | 004 HIGH, MEDIUM A05/A09 |
| [ADR-025](../../docs/adrs/ADR-025-db-backed-campaign-registry.md) | Replace in-memory `CampaignRegistry` with DB-backed `AccountRepository` in all play routes | 004 HIGH, MEDIUM |
| [ADR-026](../../docs/adrs/ADR-026-postgres-tls-policy.md) | PostgreSQL connections must use TLS by default; `sslmode=require` or equivalent | 002 HIGH A02/A05 |
| [ADR-027](../../docs/adrs/ADR-027-postgres-concurrency-and-lifecycle.md) | Concurrency-safe event `seq` allocation; `PostgresStorage` deterministic lifecycle | 002 MEDIUM A04, MEDIUM QA |
| [ADR-028](../../docs/adrs/ADR-028-combat-terminal-state-unification.md) | Unify terminal-state checking into a shared helper called from both `take_turn` and `combat_round` | 003 MEDIUM (combat victory path gap) |

The cycle-1 findings from all five reviews require twelve architectural decisions,
recorded as ADRs 017–028. ADRs 017–020 address the 001 review; ADRs 022–024 are
renumbered from the `feat/004-auth-obs` branch (where they were 017–019) and amended
with the remediation; ADR-025 is new; ADRs 026–027 are new for the 002 review; ADR-028
is new for the 003 review. The 005 review requires no new ADRs — its findings are
implementation bugs and configuration issues. They are the blueprint for the
implementation work in this spec.

### ADR-017 — Backend-scoped API / backend-canonical contract shape

**Amended 2026-07-01 (D1)**: The original ADR-017 kept `/campaigns/{id}/...` routes
with the frontend managing `campaign_id` explicitly. This is amended to a
**backend-scoped** design: the frontend has no awareness of `campaign_id`. The backend
resolves the active campaign from the JWT (`JWT → account_id → SELECT campaign WHERE
status='active'`). One active campaign per account at a time.

**Route redesign** — from resource-scoped to session-scoped:

| Old (resource-scoped) | New (session-scoped) |
|---|---|
| `POST /campaigns` | `POST /me/game` — create or resume active campaign |
| `GET /campaigns` | `GET /me/graveyard` — past ended campaigns |
| `GET /campaigns/{id}` | `GET /me/game` — current campaign state |
| `DELETE /campaigns/{id}` | `DELETE /me/game` — abandon current campaign |
| `POST /campaigns/{id}/turn` | `POST /me/game/turn` |
| `GET /campaigns/{id}/character` | `GET /me/game/character` |
| `POST /campaigns/{id}/character` | `POST /me/game/character` |
| `GET /campaigns/{id}/scene` | `GET /me/game/scene` |
| `POST /campaigns/{id}/save` | `POST /me/game/save` |
| `POST /campaigns/{id}/session` | `POST /me/game/session` |
| `POST /campaigns/{id}/session/takeover` | `POST /me/game/session/takeover` |
| `DELETE /campaigns/{id}/session` | `DELETE /me/game/session` |

**Rationale**: A gamebook player thinks "I am playing", not "I am managing campaign
abc-123". `campaign_id` is an internal routing detail (like a database row ID) that
does not belong in URLs or frontend state. The backend resolves it from auth context.
This also eliminates the need for the frontend to store, pass, or validate `campaign_id`.

**Backend canonical response shapes** (unchanged in structure, updated for spec 007):

| Response type | Backend shape (canonical) |
|---|---|
| `TurnResponse` | `{ scene, character?, world?, status }` (no `effects_applied` — removed spec 007) |
| `GameState` | `{ status, character?, world?, current_scene? }` |
| `CampaignSummary` (graveyard) | `{ campaign_id, status, name?, created_at?, updated_at? }` |

Note: `CombatRoundResponse` and `FleeCombatResponse` are **obsolete** — combat routes
removed by spec 007 (ADR-029). Combat is auto-resolved inside `POST /me/game/turn`.

### ADR-018 — Multi-tenant engine via per-call `campaign_id`

Multi-tenancy is implemented at the **MCP server layer**, not by rewriting the
`StorageBackend` Protocol. Every MCP tool gains `campaign_id: str` as its first
parameter; `build_server` receives a `storage_factory: Callable[[str], StorageBackend]`
that returns a cached-or-new backend scoped to the campaign. The web layer passes
`campaign_id` on every `call_engine(...)` invocation. This preserves Principle II
(interface stability) and swap boundary #1, keeps **one engine subprocess for all
campaigns**, and makes the campaign dimension explicit in the contract.

**Implementation (Option A — confirmed 2026-07-01)**: `campaign_id: str` is added as
the first parameter of all 18 MCP tools. The narrator receives `campaign_id` in the
system prompt and the LLM includes it in every tool call. The web layer validates
post-narration (via `result.all_messages()`) that all tool calls used the correct
`campaign_id`. One MCP subprocess at startup serves all campaigns.

**Production scaling path**: When horizontal scaling is required, the transport layer
migrates from `StdioTransport` to `StreamableHTTPTransport` (MCP HTTP transport). With
HTTP transport, `campaign_id` moves to an HTTP header or URL path — the tool schemas
stay unchanged. This migration is a transport-layer swap, not a redesign.

Rejected alternatives:
- **Subprocess per campaign (Option B)**: creates one Python subprocess per active
  campaign (~40–50 MB each). Does not scale; rejected.
- **Multi-tenant `StorageBackend`**: would rewrite every storage method and every test,
  violating the spirit of swap boundary #1.
- **Per-request toolset (Option B variant)**: same memory problem as subprocess per
  campaign, plus subprocess cold-start latency on every request.

### ~~ADR-019 — Allowlist for fabricated-number detection~~ SUPERSEDED BY ADR-029

**Superseded 2026-06-30 by spec 007 (ADR-029)**: `EffectType`, `Effect`, `effects[]`,
`_RESULT_KEYS`, and `_scene_contains_fabricated_numbers` were all **deleted** in spec
007. The narrator now calls MCP tools directly during `agent.run()` and narrates only
what it sees from real tool responses. Principle I ("numbers never in prose") is
enforced by design — there is no post-hoc validator to bypass. T027 in tasks.md is
marked OBSOLETE. No implementation work required.

### ADR-020 — Resolve duplicate ADR numbering (extended for 004 absorption)

`ADR-014-postgres-storage-sync-async-bridge.md` keeps number 014. The pydantic-ai
MCPToolset ADR is renumbered from 014 to **021** and renamed. The two "moved" stubs are
deleted. The `CLAUDE.md` ADR table is corrected to list each ADR exactly once.

**Extended for 004 absorption**: the `feat/004-auth-obs` branch created ADRs 017–019
(OIDC, session lease, OTel) which collide with the 006 ADRs 017–019. These are
renumbered to **022–024** when the 004 work is absorbed into this slice. The ADR files
are renamed and their headers updated. The `CLAUDE.md` ADR table lists each ADR exactly
once with the corrected numbers.

### ADR-022 — OIDC JWT/JWKS validation + fail-closed auth (renumbered from 004's ADR-017)

The OIDC validation pattern from the 004 branch is retained but **amended to be
fail-closed**:

1. **No dev stub fallback in production.** When `OIDC_JWKS_URI` is unset and
   `GAMEBOOK_DEV_MODE` is not explicitly enabled, the app refuses to start (or every
   request receives `401`). The `DEV_TOKEN = "dev-token"` constant is removed from
   production code paths; it survives only in test fixtures.
2. **`OIDC_ISSUER` is mandatory** when OIDC is the active auth; `verify_iss=True`
   always. No empty-string default.
3. **`exp` claim is required** in every JWT; tokens without `exp` are rejected.
4. **JWKS key selection**: when `kid` is missing from the JWT header, the token is
   rejected (no fallback to the first JWKS key).
5. **Validated-token cache key** uses `sha256(token)[:16] + exp` per the learning
   lesson and `CONTRACTS.md` — not the full SHA-256 digest.
6. **Graceful degradation** is retained: JWKS cache (5 min TTL) + validated-token
   cache survive short OIDC outages. On JWKS fetch failure with no cached token →
   `503 auth_unavailable`.

The auth seam (FastAPI dependency override) is unchanged. `python-jose` is retained
for this slice; a future hardening slice may migrate to `PyJWT` or `authlib` (noted as
a dependency risk, not a blocker).

### ADR-023 — Session lease with `current_token` validation (renumbered from 004's ADR-018)

The session lease design from the 004 branch is retained but **amended**:

1. **`takeover` validates `current_token`**: the `current_token` body parameter is
   used to validate the current holder before force-acquiring. If `current_token` is
   wrong or missing, the takeover is rejected with `409`. This closes the MEDIUM A04
   finding where any session of the same account could force-displace the lease.
2. **Lease expiry boundary**: `expires_at <= now()` is treated as expired (not `<`).
3. **DB-backed enforcement**: the lease is stored in Postgres (the `session_lease`
   table from the 004 implementation). The in-memory `CampaignRegistry` is not used
   for lease state.
4. **`LeaseGuardMiddleware`** is retained; it validates `X-Session-Lease` on mutating
   requests and renews the TTL on success.

### ADR-024 — OTel auto-instrumentation + no-PII discipline (renumbered from 004's ADR-019)

The observability design from the 004 branch is retained but **amended**:

1. **`FastAPIInstrumentor.instrument_app(app)`** is used instead of
   `FastAPIInstrumentor().instrument()` — the current call is a no-op without the app
   reference.
2. **`turn_span` and `narrator_span` are wired** into the `/turn` route and the
   narrator call respectively. The span helpers exist but are never invoked in the
   current code.
3. **Metric counters are emitted**: `http_requests_total`, `turn_duration_seconds`,
   `active_campaigns`, `combat_rounds_total` are actually incremented/recorded at
   the appropriate call sites.
4. **`span_set_error` records only `type(exc).__name__`** — no message, no traceback.
   The current `record_exception(exc)` call is replaced with a manual event or
   attribute override.
5. **Generic exception handler logs exception type only** — `logger.exception` is
   replaced with `logger.error("unhandled %s", type(exc).__name__)` (no traceback).
6. **OTLP exporters default to TLS**: `insecure=True` is removed; the exporter uses
   TLS unless explicitly disabled for local development.
7. **No PII in span attributes**: only opaque UUIDs (`campaign_id`, `account_id`,
   `turn_number`). Character names, inventory, narrative text, world flags, and OIDC
   `sub` are forbidden.

### ADR-025 — DB-backed campaign registry (new)

The in-memory `CampaignRegistry` is replaced by the DB-backed `AccountRepository` in
all play routes. This formalizes the replacement that the 004 implementation started
but did not wire into the state-changing routes.

1. **`CampaignRegistry` is removed** (or reduced to a thin transient-state cache for
   the current scene/combat id only). Campaign ownership, creation, listing, and
   deletion are all backed by `AccountRepository` methods against Postgres.
2. **`AccountRepository.create_campaign`** is fixed: duplicate IDs raise `409`
   (instead of silently returning the requester as owner); the `account_id` is always
   set (never `NULL`).
3. **`PostgresStorage._ensure_campaign`** inserts campaign rows with the correct
   `account_id` (not `NULL`), so session ownership works for DB-created campaigns.
4. **Play routes** (`create/list/get/delete campaign`) call `AccountRepository`
   methods, not `CampaignRegistry`. The lease's "account owns campaign" assumption is
   enforced by the routes that actually mutate state.
5. **`DELETE /me`** returns `404` if the account does not exist (not `204`); a
   confirmation token or password re-entry is required before erasure.
6. **`GET /me/export`** includes `save_slot` snapshots in the export payload.

### ADR-026 — PostgreSQL TLS policy (new)

All PostgreSQL connections created by `PostgresStorage` must use TLS in production.
The default engine configuration enforces `sslmode=require` (or the asyncpg/SQLAlchemy
`ssl=True` equivalent). A non-production override exists only for local development with
an explicit, documented env var (e.g., `POSTGRES_SSL_MODE=disable`). This closes the
HIGH A02/A05 finding that credentials and game state could travel in plaintext when
`DATABASE_URL` omits `sslmode`.

### ADR-027 — PostgresStorage concurrency + lifecycle (new)

Two production-hardening decisions for the persistence foundation:

1. **Concurrency-safe event sequence allocation.** `append_event` must allocate the
   next `seq` in a way that is serializable across concurrent writers. Options:
   `SELECT MAX(seq) FROM event WHERE campaign_id = :cid FOR UPDATE`, a PostgreSQL
   advisory lock per campaign, or a generated sequence/column. The misleading inline
   comment claiming "no race condition because we hold the row-level lock via the
   INSERT" is removed or corrected. A concurrent-append test proves the fix.
2. **Deterministic `PostgresStorage` lifecycle.** `PostgresStorage` exposes a
   `close()` method that disposes the async engine and stops the private daemon event
   loop. Live-Postgres test fixtures call it in teardown; the MCP server calls it on
   graceful shutdown. This closes the MEDIUM finding that engines/threads leak per test.

### ~~ADR-028 — Combat terminal-state unification~~ SUPERSEDED BY ADR-029

**Superseded 2026-06-30 by spec 007 (ADR-029)**: `combat.py` and both explicit combat
routes (`POST /combat/round`, `POST /combat/flee`) were **deleted**. Combat is now
auto-resolved by the narrator calling MCP tools directly during `agent.run()`. There is
only one entry point for terminal-state checking: `_check_terminal_state` called from
`take_turn` in `play.py`. The original finding (victory never triggered via the explicit
route) is moot — that route no longer exists. T085 and T094 in tasks.md are updated
accordingly. No new unification work required.

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
3. **Frontend has no awareness of `campaign_id` (D1, 2026-07-01).** The SPA uses
   backend-scoped routes (`/me/game/turn`, `/me/game/character`, etc.). The backend
   resolves `campaign_id` from the JWT (`account_id → active campaign`). The frontend
   never stores, passes, or validates `campaign_id`. `useGame` is a parameterless hook.
4. **Session lease endpoints are implemented (spec 004 merged).** `acquireSession`,
   `takeoverSession`, and `releaseSession` exist in `src/gamebook_web/api/sessions.py`.
   The `VITE_SESSION_LEASE` gate in the frontend is removed; lease calls use the
   new backend-scoped routes (`/me/game/session`, `/me/game/session/takeover`).
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
10. **Fail-closed OIDC is the default.** The production auth path never falls back to
    the dev stub. `GAMEBOOK_DEV_MODE=1` is only honored in non-production environments
    and test fixtures. When `OIDC_JWKS_URI` is unset and dev mode is off, the server
    refuses to start.
11. **`OIDC_ISSUER` and `exp` are mandatory.** No empty-string defaults; `verify_iss`
    is always `True`; JWTs without `exp` are rejected.
12. **JWKS key binding is strict.** When `kid` is missing from the JWT header, the
    token is rejected — no fallback to the first JWKS key.
13. **Validated-token cache key** is `sha256(token)[:16] + exp`, not the full digest.
14. **DB-backed campaign ownership is the only path.** The in-memory
    `CampaignRegistry` is removed from all state-changing routes.
    `AccountRepository.create_campaign` raises `409` on duplicate IDs and always sets
    `account_id`.
15. **`PostgresStorage._ensure_campaign` sets `account_id`.** Campaign rows created by
    the storage layer carry the owning account's ID, not `NULL`.
16. **Lease `takeover` validates `current_token`.** A takeover with the wrong token is
    rejected with `409`. The `current_token` parameter is used, not ignored.
17. **Lease expiry is `<=`.** `expires_at <= now()` is expired; the current `<` check
    allows a one-instant window of stale access.
18. **OTel uses `instrument_app(app)`.** The `FastAPIInstrumentor().instrument()` call
    without the app is a no-op; the correct API is `instrument_app(app)`.
19. **`turn_span`/`narrator_span` are wired.** The span helpers are invoked in the
    `/turn` route and the narrator call, not just defined.
20. **Metrics are emitted.** The four `GamebookMetrics` instruments are actually
    incremented/recorded at the appropriate call sites.
21. **`span_set_error` records only the exception class name.** No message, no
    traceback — prevents PII and internal details from reaching telemetry consumers.
22. **Generic handler logs type only.** `logger.error("unhandled %s",
    type(exc).__name__)` replaces `logger.exception(...)`.
23. **OTLP defaults to TLS.** `insecure=True` is removed; TLS is the default.
24. **`save_slot` snapshots in GDPR export.** The export payload includes save slot
    data, not just the account and campaign rows.
25. **Security audit logging.** Sign-in, sign-out, failed auth, lease
    acquire/takeover/release, and account deletion are logged at `INFO` or `WARNING`
    with opaque IDs (no PII).
26. **`DELETE /me` requires confirmation.** A confirmation token or password
    re-entry is required; the endpoint returns `404` if the account does not exist.
27. **CORS rejects `*` with credentials.** When `allow_credentials=True`,
    `GAMEBOOK_CORS_ORIGINS=*` is rejected at startup.
28. **Postgres integration tests.** Tests that run against a live Postgres with
    `DATABASE_URL` cover account upsert, campaign ownership, lease
    acquire/validate/takeover/release, GDPR export/erasure, and
    `PostgresStorage` campaign scoping.
29. **PostgreSQL TLS is default-on.** `PostgresStorage.__init__` enforces
    `sslmode=require` (or `ssl=True`) unless an explicit non-production override is
    set. `DATABASE_URL` without `sslmode` is not accepted in production.
30. **Event sequence allocation is serializable.** `append_event` locks the sequence
    range or uses a generated sequence; the misleading "no race condition" comment is
    removed. A concurrent-append test proves no duplicate `seq`.
31. **`PostgresStorage` has a `close()` lifecycle.** The engine and daemon thread are
    disposed deterministically in test teardown and on MCP server shutdown.
32. **`_build_snapshot` reads in a transaction.** `save_slot` captures an internally
    consistent snapshot of the mutable campaign state across all tables.
33. **Identifier validation parity.** `save_slot`, `load_slot`, `load_combat`, and
    `remove_combat` reject empty/`None`/`/`/`\`/`..` identifiers, matching `JSONStorage`.
34. **Swap-boundary test includes Postgres.** `tests/qa/test_storage_swap.py` runs
    the consumer-level combat/storage swap test against `PostgresStorage` when
    `DATABASE_URL` is present, proving ADR-009 for the new backend.
35. **Atomic-write test proves mid-statement failure.** `tests/server/test_atomic_writes.py`
    simulates a failure after at least one `session.execute()` has run, proving no partial
    data is committed.
36. **Combat victory path is unified.** Both `take_turn` and `combat_round` call the
    same `_check_terminal_state` helper when `outcome.ended` is True. Winning the final
    boss via `POST /combat/round` triggers victory archiving and campaign end.
37. **`request: Request` has no `None` default.** Rate-limited routes receive a proper
    `Request` instance; the `= None` default is removed to avoid fragile behavior under
    non-TestClient call paths.
38. **Rate limiter keys on account_id.** When authenticated, the rate limiter uses
    `account_id` as the key (falling back to IP only when unauthenticated). Trusted
    proxy headers (`X-Forwarded-For`) are configured for behind-LB deployments.
39. **Narrator + combat subagent are tested.** The `PydanticNarrator` live path is
    exercised by an integration test with a mocked LLM producing a `Scene` that flows
    through validation → effects → response. `combat_subagent.py` is exercised by a
    test that delegates a combat and verifies the `CombatResult` structure.
40. **Python dependency upper bounds.** Floating `>=` ranges in `pyproject.toml` are
    capped with upper bounds (e.g. `fastapi>=0.115.0,<1.0`) to prevent unexpected
    breaking changes from future major releases.
41. **`list_campaigns` includes `name` and timestamps.** The response carries
    `name`, `created_at`, and `updated_at` for each campaign, matching the frontend
    `CampaignSummary` type.
42. **Two new learning lessons recorded.** (1) API/frontend contract drift requires a
    live integration test, not eyeballing field names; (2) booting a single shared
    engine subprocess scoped to an env var is a multi-tenancy anti-pattern.
43. **Source maps disabled in production.** `frontend/vite.config.ts` sets
    `sourcemap: false` (or conditionally enables only in dev mode) so production builds
    do not expose source code.
44. **CSP headers present.** `frontend/index.html` includes a Content-Security-Policy
    meta tag (or the backend sets the header) restricting `script-src` to `'self'`,
    `style-src` to `'self' 'unsafe-inline'`, and `connect-src` to `'self'`.
45. **ErrorBoundary wraps the App root.** A React ErrorBoundary component catches
    render errors and displays a fallback UI instead of a blank screen.
46. **CombatPanel validates participants.** Before accessing `participants[0]` and
    `participants[1]`, the component checks `participants.length >= 2` and renders a
    fallback if not.
47. **401/403 redirects to `/auth`.** `useGame` intercepts auth errors and redirects
    to the auth page instead of showing a generic error message.
48. **Token expiration is checked.** The SPA parses `expires_at` from the session lease
    and redirects to `/auth` if the token has expired.
49. **useEffect dependencies are correct.** `useGame` and `useCampaign` remove `load`
    from the `useEffect` dependency array to prevent stale closures.
50. **Free-text input is validated.** `ChoicesPanel` rejects empty submissions and
    enforces a max length.
51. **Error messages are sanitized.** Error messages displayed to users do not include
    backend implementation details, stack traces, or PII.
52. **Security headers are configured.** The backend (or a reverse proxy) sets
    `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and
    `Referrer-Policy: strict-origin-when-cross-origin`.
53. **vitest is upgraded.** `frontend/package.json` pins `vitest >= 3.2.6` to address
    GHSA-5xrq-8626-4rwp (CRITICAL, dev-only).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The SPA plays against the live backend (Priority: P1)

A player opens the SPA in live mode (not mock), signs in with the dev token, starts a
game, creates a character, takes turns, and reaches an end-state — every response field
the SPA reads is populated and matches the backend's OpenAPI schema. No `undefined`
fields, no 404s, no field-name mismatches. The SPA never manages a `campaign_id` — the
backend resolves the active campaign from the account's session (D1).

**Why this priority**: This is the entire point of the remediation — the SPA is
currently mock-only because of contract drift AND uses resource-scoped routes that the
backend will no longer expose. Without this, slices 003 and 005 cannot be used
together.

**Independent Test**: Start the FastAPI backend and the Vite dev server with
`VITE_USE_MOCK=false`. Drive the full play loop through a Playwright test against the
live backend: `POST /me/game` → `POST /me/game/character` → `POST /me/game/turn` × 2
→ turn that auto-resolves combat (no separate combat endpoint) → `GET /me/graveyard`
(if ended). Confirm every response renders without `undefined` and the character sheet
reflects engine-rolled values.

**Acceptance Scenarios**:

1. **Given** the backend running and the SPA in live mode, **When** the player starts a
   game (`POST /me/game`), **Then** the response carries `{ status, campaign_id }` and
   the SPA proceeds to character creation without storing the campaign_id in a URL
   parameter or component prop.
2. **Given** a game in progress, **When** the player takes a turn (`POST /me/game/turn`),
   **Then** `TurnResponse` carries `{ scene, character, world }` _(no `effects_applied`
   — removed in spec 007)_ and the SPA renders without reading `res.campaign`.
3. **Given** a turn that triggers combat, **When** `POST /me/game/turn` returns,
   **Then** combat is auto-resolved inside the turn (no separate `/combat/round`
   endpoint) and the `scene.terminal` flag indicates end-state.
4. **Given** a game that ended (hero died or won), **When** the player calls
   `GET /me/graveyard`, **Then** the ended campaign appears in the list.
5. **Given** the backend boots with `ENV=production` and `GAMEBOOK_DEV_MODE=1`,
   **Then** the server refuses to start with a clear error.

### User Story 2 - The engine serves multiple campaigns in one process (Priority: P1)

A single FastAPI process serves multiple campaigns simultaneously. Each campaign has
its own character, world, events, and combat state. A tool call for campaign B cannot
touch campaign A's state.

**Why this priority**: This is the CRITICAL security finding (A01). Without
per-campaign isolation, the backend is a cross-account data leak.

**Independent Test**: Using the documented API with two different accounts, create a
campaign per account (via `POST /me/game`), create a character in each, take a turn in
each, and assert `GET /me/game/character` for account A does not return B's character.
Run `test_multi_campaign_isolation.py` against a two-account fixture and confirm no
cross-talk. The test passes `campaign_id` to all 18 MCP tools directly (not via env
var or URL).

**Acceptance Scenarios**:

1. **Given** two accounts (A and B) each with one active campaign, **When** a
   character is created in A's campaign, **Then** a read of B's character
   (`GET /me/game/character` authenticated as B) returns 404 — B has no character.
2. **Given** the engine subprocess is started once, **When** 100 campaigns are
   created across accounts, **Then** the process does not spawn 100 subprocesses (one
   process, one `storage_factory`, per-campaign backends cached).
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

### User Story 4 - OIDC auth is fail-closed (Priority: P1)

An operator deploys the backend without `OIDC_JWKS_URI` configured. The server refuses
to start (or every request receives `401`) — it does not silently fall back to the
dev auth stub. A token without `exp`, without `kid`, or with the wrong issuer is
rejected. The hardcoded `dev-token` is not accepted in any production path.

**Why this priority**: This is the CRITICAL A07 finding from the 004 review. Without
fail-closed auth, any production deployment can be bypassed with a single known token.

**Independent Test**: Boot the server with `ENV=production` and no `OIDC_JWKS_URI` —
assert it refuses to start. Boot with `OIDC_JWKS_URI` set and send a token without
`exp` — assert `401`. Send a token with a wrong issuer — assert `401`. Send a token
without `kid` — assert `401`.

**Acceptance Scenarios**:

1. **Given** `ENV=production` and `OIDC_JWKS_URI` unset, **When** the server boots,
   **Then** it raises `RuntimeError` (or every request returns `401`).
2. **Given** OIDC is configured, **When** a JWT without `exp` is sent, **Then** the
   response is `401` and the token is not cached.
3. **Given** OIDC is configured, **When** a JWT with `kid` missing is sent, **Then**
   the response is `401` (no fallback to the first JWKS key).
4. **Given** OIDC is configured, **When** a JWT with `iss != OIDC_ISSUER` is sent,
   **Then** the response is `401`.
5. **Given** the validated-token cache, **When** a token is cached, **Then** the cache
   key is `sha256(token)[:16] + exp` (verified by inspecting the cache in a test).

### User Story 5 - Campaign ownership is DB-backed and enforced (Priority: P1)

A player creates a campaign, lists their campaigns, and deletes one. All operations
go through `AccountRepository` against Postgres. The in-memory `CampaignRegistry` is
not used for ownership. A duplicate campaign ID is rejected. A campaign created by
the storage layer carries the owning account's ID.

**Why this priority**: This is the HIGH finding from the 004 review — campaign
ownership is split across two stores, and the DB-backed methods are dead code.

**Independent Test**: With a live Postgres, create a campaign, list campaigns, and
delete one — all through the API. Assert the campaign row in Postgres has the correct
`account_id`. Assert a duplicate ID returns `409`.

**Acceptance Scenarios**:

1. **Given** an authenticated account, **When** the player creates a campaign,
   **Then** the campaign row in Postgres has `account_id` set to the account's ID
   (not `NULL`).
2. **Given** a campaign exists, **When** the player creates a campaign with the same
   ID, **Then** the response is `409` (not silent success).
3. **Given** an account with 3 campaigns, **When** the player lists campaigns,
   **Then** the response contains exactly those 3 campaigns from Postgres (not from
   in-memory registry).
4. **Given** a campaign, **When** the player deletes it, **Then** the campaign row is
   removed from Postgres and the in-memory registry (if any) is invalidated.
5. **Given** `DELETE /me` is called for a non-existent account, **Then** the response
   is `404` (not `204`).
6. **Given** `DELETE /me` is called without a confirmation token, **Then** the
   response is `400` (confirmation required).
7. **Given** `GET /me/export`, **When** the export is generated, **Then** the payload
   includes `save_slot` snapshots.

### User Story 6 - Session lease semantics match the contract (Priority: P2)

A player opens a campaign on two devices. The second device sends a takeover request
with the wrong `current_token` — it is rejected. The lease expiry boundary is
inclusive (`<=`), so a lease that expires at exactly `now()` is treated as expired.

**Why this priority**: This is the MEDIUM A04 finding — `takeover` ignores
`current_token`, allowing any session to force-displace the lease.

**Independent Test**: With a live Postgres, acquire a lease, then send a takeover with
the wrong `current_token` — assert `409`. Send a takeover with the correct
`current_token` — assert success. Wait until `expires_at == now()` and assert the
lease is expired.

**Acceptance Scenarios**:

1. **Given** a lease held by session A, **When** session B sends a takeover with the
   wrong `current_token`, **Then** the response is `409`.
2. **Given** a lease held by session A, **When** session B sends a takeover with the
   correct `current_token`, **Then** the lease is transferred to session B.
3. **Given** a lease with `expires_at == now()`, **When** the lease is validated,
   **Then** it is treated as expired (not still valid).

### User Story 7 - Observability is wired and PII-free (Priority: P2)

An operator sends a request that triggers an error. The trace contains the
`campaign_id` and `account_id` but no character names, narrative text, or stack
traces. The metric counters are incremented. The FastAPI auto-instrumentation
produces a span for every HTTP request.

**Why this priority**: This is the HIGH + MEDIUM findings from the 004 review — OTel
code exists but is not wired, and PII/tracebacks leak into spans and logs.

**Independent Test**: Send a `/turn` request that triggers a narrator error. Inspect
the in-memory span exporter — assert the span has `campaign_id` but no narrative text.
Assert `http_requests_total` was incremented. Assert the log line contains only the
exception class name, not the traceback.

**Acceptance Scenarios**:

1. **Given** a `/turn` request, **When** it completes, **Then** a `turn_span` child
   span exists with `campaign_id` and `account_id` attributes (no PII).
2. **Given** a `/turn` request that triggers an error, **When** the span is inspected,
   **Then** the span status is `ERROR` with only `type(exc).__name__` (no message, no
   traceback).
3. **Given** any HTTP request, **When** it completes, **Then** `http_requests_total`
   is incremented (method/path/status labels).
4. **Given** a narrator call, **When** it completes, **Then** a `narrator_span` child
   span exists.
5. **Given** an unhandled exception, **When** the generic handler runs, **Then** the
   log line contains only `type(exc).__name__` (no traceback).
6. **Given** `OTLP_ENDPOINT` is set, **When** the exporter is configured, **Then**
   TLS is used (no `insecure=True`).

### User Story 8 - Persistence foundation is production-hardened (Priority: P2)

The backend stores game state in Postgres. Connections are encrypted by default;
concurrent appends to the event log never produce duplicate sequence numbers; saves
capture a consistent snapshot; the storage backend can be shut down cleanly without
leaking threads or connections.

**Why this priority**: These are the HIGH + MEDIUM findings from the 002 review —
the persistence foundation works but is not production-hardened for TLS, concurrency,
lifecycle, or consistency.

**Independent Test**: Run the live-Postgres test suite (`DATABASE_URL=... uv run pytest
 tests/server/test_postgres_*.py -v`). Assert TLS is enforced by default; assert two
concurrent `append_event` calls produce distinct `seq` values; assert `PostgresStorage.close()`
stops the daemon thread; assert `save_slot` reads a consistent snapshot.

**Acceptance Scenarios**:

1. **Given** a production `DATABASE_URL` without `sslmode`, **When** the app boots,
   **Then** it refuses to start or upgrades to TLS (no plaintext connection).
2. **Given** two concurrent writers appending events to the same campaign, **When**
   both commits succeed, **Then** all `seq` values are unique and monotonic.
3. **Given** a `PostgresStorage` instance, **When** `close()` is called, **Then** the
   async engine is disposed and the daemon thread stops.
4. **Given** a save slot written while another transaction mutates the campaign, **When**
   the snapshot is read, **Then** it reflects a single, consistent point in time.
5. **Given** `load_slot("")` or `load_combat(None)`, **When** the call is made,
   **Then** the response is a clear validation error (not an obscure SQLAlchemy error).

### ~~User Story 9~~ OBSOLETE — superseded by spec 007 (ADR-029)

~~Combat victory works via the explicit combat route.~~

**Why obsolete**: `combat.py` and its routes (`POST /combat/round`,
`POST /combat/flee`) were deleted in spec 007 (ADR-029). Combat is now auto-resolved
by the narrator calling MCP tools directly during `agent.run()`. Victory and death are
detected by `_check_terminal_state` called from `take_turn` — the only combat entry
point. The reduced scope of FR-044 (task T085) reflects this: ensure
`_check_terminal_state` handles both victory and death from `take_turn`, no
unification needed.

**What replaced it**: User Story 2 (multi-tenant engine isolation) covers the engine
correctness path. The narrator auto-resolves combat inside `POST /me/game/turn`, and
SC-025 is updated below accordingly.

### User Story 10 - Narrator is tested (Priority: P2)

The `PydanticNarrator` live path (LLM → calls MCP tools during `agent.run()` →
validates `Scene` → returns `TurnResponse`) is exercised by an integration test.
Currently this path has zero test coverage. _(Note: `combat_subagent.py` was deleted
in spec 007 — no subagent to test. Scenario 2 about fabricated-number `ModelRetry`
is also obsolete — the `effects[]` validator was deleted in spec 007; Principle I is
now enforced by design, not a post-hoc validator.)_

**Why this priority**: LOW finding from the 003 review — production-only code paths
are unverified. Without this test, the live narrator cannot be trusted.

**Independent Test**: Run an integration test with a mocked LLM that produces a valid
`Scene`; assert the scene flows through validation → response. Assert no `effects`
field in `Scene` and no `effects_applied` in `TurnResponse`.

**Acceptance Scenarios**:

1. **Given** a mocked LLM producing a valid `Scene` (narrative + choices, no effects),
   **When** the `PydanticNarrator` runs, **Then** the scene passes structural
   validation, `TurnResponse` carries `{ scene, character?, world? }`, no
   `effects_applied` field exists.
2. **Given** a mocked LLM producing a `Scene` with `terminal=True`, **When** the
   `PydanticNarrator` runs and `take_turn` calls `_check_terminal_state`, **Then** the
   campaign is marked `ended` if the hero is dead or the victory flag is set.
3. ~~Given a mocked LLM with fabricated numbers~~ — **OBSOLETE**: the
   `_scene_contains_fabricated_numbers` validator was deleted in spec 007 (ADR-029).

### User Story 11 - SPA is production-hardened (Priority: P2)

The SPA is safe to deploy to production: source maps are disabled, CSP headers are
present, an ErrorBoundary catches render errors, combat data is validated before
rendering, auth errors redirect to login, and token expiration is checked. Currently
the SPA has 4 HIGH and 4 MEDIUM findings from the 005 review that block production
deployment.

**Why this priority**: The 005 review returned PASS WITH CONDITIONS — the blocking
items (source maps, CSP, ErrorBoundary, CombatPanel validation, 401/403 handling,
token expiration) must be fixed before the SPA is production-ready.

**Independent Test**: Build the SPA in production mode and verify no source maps are
generated. Load the app and verify CSP headers are present. Trigger a render error and
verify the ErrorBoundary catches it. Send a 401 and verify redirect to `/auth`.

**Acceptance Scenarios**:

1. **Given** a production build, **When** the bundle is inspected, **Then** no source
   maps are present.
2. **Given** the SPA is loaded, **When** the page headers are inspected, **Then** a
   Content-Security-Policy header is present.
3. **Given** a React render error, **When** the error is thrown, **Then** the
   ErrorBoundary displays a fallback UI (not a blank screen).
4. **Given** a combat with missing participants, **When** CombatPanel renders, **Then**
   a fallback is shown (not a crash).
5. **Given** a 401 response from the backend, **When** `useGame` handles it, **Then**
   the user is redirected to `/auth`.
6. **Given** an expired session lease, **When** the SPA checks `expires_at`, **Then**
   the user is redirected to `/auth`.

## Functional Requirements

### FR-001 (ADR-018) Multi-tenant engine via per-call campaign_id
Every MCP tool in `src/gamebook/mcp/server.py` gains a `campaign_id: str` first
parameter. `build_server` takes a `storage_factory: Callable[[str], StorageBackend]`
instead of a single `storage` instance. The factory caches per-campaign backends.

### FR-002 (ADR-018) Web layer passes campaign_id on every engine call
Every `call_engine(toolset, tool_name, ...)` call site in `play.py` passes
`campaign_id=campaign_id`. _(combat.py was deleted in spec 007 — only play.py call
sites remain.)_ `GAMEBOOK_CAMPAIGN_ID` is no longer read by the web backend lifespan;
the `campaign_id` is resolved by `_get_active_campaign(account)` on each request.

### FR-003 (ADR-017 + D1) Frontend conforms to backend-scoped API contract
`frontend/src/types/index.ts` is updated: `TurnResponse` → `{ scene, character?,
world? }` _(no `effects_applied` — removed in spec 007)_; remove
`CombatRoundResponse` and `FleeCombatResponse` _(combat endpoints deleted in spec
007)_. Add `GraveyardEntry` type for `GET /me/graveyard`. `useGame.applyTurnResponse`
assembles `GameState` from `{ character, world, current_scene }` — no `campaign_id`
threaded through frontend state (D1).

### FR-004 (ADR-017 + D1) Frontend has no campaign_id awareness — backend-scoped design
The SPA API client uses `/me/game/...` routes (no `{campaign_id}` path parameter).
`useGame()` takes no `campaignId` argument — the backend resolves the active campaign
from the authenticated account. The frontend treats the game as a singleton session;
the graveyard (`GET /me/graveyard`) is the only multi-campaign view.

### FR-004b (D1) Backend routes redesigned to `/me/game/...`
All game-play routes in `src/gamebook_web/api/play.py` are renamed from
`/campaigns/{id}/...` to `/me/game/...`. `_get_active_campaign(account)` replaces
`_campaign_or_404(registry, campaign_id, account)` as the auth/ownership helper. When
no active campaign exists for the account (first visit, or all campaigns ended), it
returns `404 no_active_campaign` with `hint: "POST /me/game to start a new game"` —
never a generic 404 — so the SPA can route the player to the start screen.
`GET /me/graveyard` lists ended campaigns (death + victory) and is read-only in this
slice. **Known gap (deferred)**: individual graveyard entries cannot be deleted by the
player in this slice — only `DELETE /me` (GDPR erasure) removes them. If individual
entry deletion is needed in the future, `DELETE /me/graveyard/{id}` is the natural
extension point. The `contracts/http-api.md` is updated to reflect these routes.

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

### ~~FR-014~~ SUPERSEDED BY ADR-029 / spec 007
~~Allowlist for fabricated-number detection (`_ALLOWED_EFFECT_PARAMS`, `EffectType`,
`_RESULT_KEYS`, `_scene_contains_fabricated_numbers`).~~
All of `effects[]`, `EffectType`, and the fabricated-number validator were deleted in
spec 007 (ADR-029). The narrator now calls MCP tools directly during generation —
Principle I (no AI-invented numbers) is enforced by design. No replacement needed.

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

### FR-018 (ADR-022, CRITICAL) Fail-closed OIDC auth
`src/gamebook_web/auth/dev_auth.py` `DEV_TOKEN` is removed from production code paths
(kept only in test fixtures). `src/gamebook_web/api/app.py` lifespan does not fall
back to the dev stub when `OIDC_JWKS_URI` is unset — it raises `RuntimeError` (or
every request returns `401`). `GAMEBOOK_DEV_MODE=1` is only honored in non-production
environments.

### FR-019 (ADR-022, HIGH) Require OIDC issuer and exp claim
`src/gamebook_web/auth/oidc_auth.py` makes `OIDC_ISSUER` mandatory (no empty-string
default); `verify_iss=True` always; JWTs without `exp` are rejected.

### FR-020 (ADR-022, MEDIUM) Strict JWKS key binding
`src/gamebook_web/auth/oidc_auth.py` rejects tokens when `kid` is missing from the
JWT header — no fallback to the first JWKS key.

### FR-021 (ADR-022, LOW) Validated-token cache key alignment
`src/gamebook_web/auth/oidc_auth.py` cache key changes from full SHA-256 to
`sha256(token)[:16] + exp` per `CONTRACTS.md` and the learning lesson.

### FR-022 (ADR-025, HIGH) Wire DB-backed campaign ownership into play routes
`src/gamebook_web/api/play.py` `create/list/get/delete` campaign routes call
`AccountRepository` methods, not `CampaignRegistry`. The in-memory registry is removed
or reduced to a transient-state cache (current scene/combat id only).

### FR-023 (ADR-025, MEDIUM) Fix `AccountRepository.create_campaign`
`src/gamebook_web/accounts.py` `create_campaign` raises `409` on duplicate IDs
(instead of silently returning the requester as owner); `account_id` is always set.

### FR-024 (ADR-025, MEDIUM) Fix `PostgresStorage._ensure_campaign`
`src/gamebook/storage/postgres.py` `_ensure_campaign` inserts campaign rows with the
correct `account_id` (not `NULL`), so session ownership works for DB-created
campaigns.

### FR-025 (ADR-025, MEDIUM) Fix `DELETE /me` semantics
`src/gamebook_web/api/account.py` `DELETE /me` returns `404` if the account does not
exist (not `204`); requires a confirmation token or password re-entry before erasure.

### FR-026 (ADR-025, MEDIUM) `save_slot` snapshots in GDPR export
`src/gamebook_web/accounts.py` `export_account` includes `save_slot` rows in the
export payload.

### FR-027 (ADR-023, MEDIUM) Fix `LeaseService.takeover` semantics
`src/gamebook_web/sessions/lease.py` `takeover` validates `current_token` against the
current holder before force-acquiring. Wrong/missing token → `409`.

### FR-028 (ADR-023, LOW) Fix lease expiry boundary
`src/gamebook_web/sessions/lease.py` `acquire` and `validate` treat
`expires_at <= now()` as expired (change `<` to `<=`).

### FR-029 (ADR-024, HIGH) Fix OTel FastAPI instrumentation
`src/gamebook_web/observability/setup.py` changes
`FastAPIInstrumentor().instrument()` to `FastAPIInstrumentor.instrument_app(app)`.

### FR-030 (ADR-024, HIGH) Wire `turn_span`/`narrator_span` and emit metrics
`src/gamebook_web/api/play.py` `/turn` route wraps the handler in `turn_span`;
`src/gamebook_web/harness/agent.py` narrator call wraps in `narrator_span`. The four
`GamebookMetrics` instruments (`http_requests_total`, `turn_duration_seconds`,
`active_campaigns`, `combat_rounds_total`) are incremented/recorded at the
appropriate call sites.

### FR-031 (ADR-024, MEDIUM) Redact exceptions in spans and logs
`src/gamebook_web/observability/tracing.py` `span_set_error` records only
`type(exc).__name__` (no message, no traceback). `src/gamebook_web/api/app.py`
generic handler changes `logger.exception(...)` to
`logger.error("unhandled %s", type(exc).__name__)`.

### FR-032 (ADR-024, MEDIUM) Secure OTLP defaults
`src/gamebook_web/observability/setup.py` removes `insecure=True` from OTLP
exporters; TLS is the default. `insecure=True` is only set when explicitly configured
for local development.

### FR-033 (MEDIUM) Security audit logging
`src/gamebook_web/api/account.py`, `src/gamebook_web/api/sessions.py`,
`src/gamebook_web/middleware/lease_guard.py`, and `src/gamebook_web/auth/oidc_auth.py`
log security events at `INFO` or `WARNING`: sign-in, sign-out, failed auth, lease
acquire/takeover/release, account deletion. Logs use opaque IDs (no PII).

### FR-034 (MEDIUM) CORS rejects `*` with credentials
`src/gamebook_web/api/app.py` CORS config rejects `GAMEBOOK_CORS_ORIGINS=*` at
startup when `allow_credentials=True`.

### FR-035 (CRITICAL/HIGH) Postgres integration tests
`tests/server/test_postgres_accounts.py`, `test_postgres_leases.py`,
`test_postgres_campaign_ownership.py`, `test_postgres_gdpr.py` run against a live
Postgres with `DATABASE_URL`. They cover account upsert, campaign ownership, lease
acquire/validate/takeover/release, GDPR export/erasure, and `PostgresStorage`
campaign scoping.

### FR-036 (ADR-020) Renumber 004 ADRs 017–019 → 022–024
`docs/adrs/ADR-017-oidc-jwt-jwks-validation-pattern.md` → `ADR-022-...`;
`ADR-018-session-lease-acquire-takeover-semantics.md` → `ADR-023-...`;
`ADR-019-opentelemetry-auto-instrumentation.md` → `ADR-024-...`. Headers updated.
`CLAUDE.md` ADR table corrected. New `ADR-025-db-backed-campaign-registry.md` created.

### FR-037 (ADR-026, HIGH) Enforce TLS for PostgreSQL
`src/gamebook/storage/postgres.py` creates the async engine with TLS enabled by default
(`sslmode=require` or `ssl=True`). In production, a `DATABASE_URL` without TLS is rejected
at startup. A non-production override (e.g., `POSTGRES_SSL_MODE=disable`) is available for
local development only.

### FR-038 (ADR-027, MEDIUM) Concurrency-safe event sequence allocation
`src/gamebook/storage/postgres.py` `append_event` allocates the next `seq` in a
serializable way (e.g., `SELECT MAX(seq) FROM event WHERE campaign_id = :cid FOR UPDATE`,
advisory lock, or generated sequence). The misleading inline comment at `src/gamebook/storage/postgres.py:230-232`
is removed or corrected. A concurrent-append test proves no duplicate `seq`.

### FR-039 (ADR-027, MEDIUM) `PostgresStorage` deterministic lifecycle
`src/gamebook/storage/postgres.py` exposes a `close()` method that disposes the async
engine and stops the private daemon event loop. Live-Postgres test fixtures call it in
teardown; the MCP server calls it on graceful shutdown.

### FR-040 (ADR-027, MEDIUM) Consistent snapshot reads
`src/gamebook/storage/postgres.py` `_build_snapshot` wraps its multi-table reads in an
explicit read-only transaction (`async with session.begin()`) so `save_slot` captures an
internally consistent snapshot.

### FR-041 (ADR-027, LOW) Identifier validation parity
`src/gamebook/storage/postgres.py` validates string identifiers in `save_slot`,
`load_slot`, `load_combat`, and `remove_combat`, rejecting empty/`None`/`/`/`\`/`..` to
match `JSONStorage` behavior.

### FR-042 (ADR-009, MEDIUM) Swap-boundary test includes Postgres
`tests/qa/test_storage_swap.py` includes `PostgresStorage` when `DATABASE_URL` is present,
so the consumer-level combat/storage swap boundary is proven for every backend.

### FR-043 (MEDIUM) Atomic-write test exercises mid-statement failure
`tests/server/test_atomic_writes.py` simulates a failure after at least one
`session.execute()` has run, proving that a crash mid-statement leaves no partial data.

### ~~FR-044~~ SUPERSEDED BY ADR-029 / spec 007
~~Unify combat terminal-state checking across `combat.py` and `take_turn`.~~
`combat.py` was deleted in spec 007 — `_check_terminal_state` is only called from
`take_turn`. Task T085 reduces to: ensure `_check_terminal_state` handles both victory
(`victory_flag`) and death from the single `take_turn` entry point. No unification
needed; no `combat.py` to merge.

### ~~FR-045~~ SUPERSEDED BY ADR-029 / spec 007
~~Fix `request: Request = None` default on combat.py routes.~~
`combat.py` was deleted in spec 007. The `= None` default only remains (if at all) on
`play.py` routes. Task T086 is reduced to: remove `= None` from `play.py` rate-limited
routes only.

### FR-046 (MEDIUM, from 003) Rate limiter keys on account_id
`src/gamebook_web/limiter.py` keys the rate limiter on `account_id` when authenticated,
falling back to IP only when unauthenticated. Trusted proxy headers
(`X-Forwarded-For`) are configured for behind-LB deployments.

### FR-047 (LOW, from 003) Narrator integration test coverage
`tests/server/test_narrator_integration.py` exercises the `PydanticNarrator` live path
with a mocked LLM producing a valid `Scene` (narrative + choices, no `effects` field).
Asserts `TurnResponse` has no `effects_applied`. _(Fabricated-number `ModelRetry`
scenario is obsolete — validator deleted in spec 007. `test_combat_subagent.py` is
obsolete — `combat_subagent.py` deleted in spec 007.)_

### FR-048 (LOW, from 003 + D1) `GET /me/graveyard` includes `name` and timestamps
With D1 backend-scoped design, there is no `list_campaigns` endpoint. The graveyard
(`GET /me/graveyard`) lists ended campaigns. Each `GraveyardEntry` includes `name`,
`created_at`, `ended_at` (or `updated_at`), and `ended_reason` (death or victory).
The frontend `GraveyardEntry` type matches. _(The old `list_campaigns` → `CampaignSummary`
type is removed in T010.)_

### FR-049 (from 003) Python dependency upper bounds
`pyproject.toml` floating `>=` ranges are capped with upper bounds
(e.g. `fastapi>=0.115.0,<1.0`) to prevent unexpected breaking changes from future
major releases.

### FR-050 (from 003) Record two new learning lessons
`docs/learning-lessons/contract_drift_requires_live_integration_test.md` — API/frontend
contract drift requires a live integration test, not eyeballing field names.
`docs/learning-lessons/single_shared_engine_subprocess_antipattern.md` — booting a
single shared engine subprocess scoped to an env var is a multi-tenancy anti-pattern.

### FR-051 (HIGH, from 005) Disable source maps in production
`frontend/vite.config.ts` sets `sourcemap: false` or conditionally enables only in dev
mode (`sourcemap: import.meta.env.DEV`). Production builds must not generate source
maps.

### FR-052 (HIGH, from 005) Add Content-Security-Policy headers
`frontend/index.html` includes a CSP meta tag, or the backend sets the
`Content-Security-Policy` header. Recommended policy:
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'`.

### FR-053 (HIGH, from 005) Add ErrorBoundary component
`frontend/src/components/ErrorBoundary.tsx` wraps the App root in `App.tsx`. It catches
React render errors and displays a fallback UI with a "reload" button.

### FR-054 (HIGH, from 005) CombatPanel participants validation
`frontend/src/components/CombatPanel.tsx` checks `participants.length >= 2` before
accessing indices 0 and 1. If the array is too short, a fallback message is rendered
instead of crashing.

### FR-055 (MEDIUM, from 005) 401/403 redirect to `/auth`
`frontend/src/hooks/useGame.ts` intercepts `err.code === 'unauthenticated'` or
`err.code === 'forbidden'` and redirects to `/auth` instead of showing a generic error.

### FR-056 (MEDIUM, from 005) Token expiration checking
`frontend/src/hooks/useGame.ts` (or `useAuth.ts`) parses `expires_at` from the session
lease and redirects to `/auth` if the token has expired. A timer or interval checks
periodically.

### FR-057 (MEDIUM, from 005) Fix useEffect stale closure
`frontend/src/hooks/useGame.ts` and `frontend/src/hooks/useCampaign.ts` remove `load`
from the `useEffect` dependency array (or wrap `load` in `useCallback` with stable
dependencies) to prevent stale closures.

### FR-058 (MEDIUM, from 005) Free-text input validation
`frontend/src/components/ChoicesPanel.tsx` rejects empty submissions (after trim) and
enforces a max length (e.g. 1000 chars). The submit button is disabled when input is
empty.

### FR-059 (LOW, from 005) Error message sanitization
Error messages displayed to users in `frontend/src/hooks/useGame.ts` do not include
backend implementation details, stack traces, or PII. A generic "Something went wrong"
message is shown, with the detailed error logged to console only in dev mode.

### FR-060 (LOW, from 005) Security headers
The backend (or a reverse proxy) sets `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, and `Referrer-Policy: strict-origin-when-cross-origin`
on all responses.

### FR-061 (LOW, from 005) Upgrade vitest to `>=3.2.6`
`frontend/package.json` pins `vitest >= 3.2.6` to address GHSA-5xrq-8626-4rwp
(CRITICAL, CVSS 9.8, dev-only). `npm install` refreshes the lockfile.

## Success Criteria

- **SC-001** (from 001 cycle-1) The SPA plays a full loop against the live backend
  without `undefined` fields or 404s on gated endpoints. Verified by FR-015.
- **SC-002** (from 001 cycle-1) Two campaigns in one process have isolated engine
  state. Verified by `test_multi_campaign_isolation.py`.
- **SC-003** (from 001 cycle-1) The server refuses to boot with dev auth in
  production. Verified by `test_production_guards.py`.
- **SC-004** (from 001 cycle-1) `/docs` returns 404 in production. Verified by
  `test_production_guards.py`.
- **SC-005** The plugability audit (`tests/qa/test_dependencies.py`,
  `tests/qa/test_isolation.py`) stays green after the ADR-018 refactor.
- **SC-006** The full test suite (`uv run pytest -q`) stays green.
- **SC-007** The frontend test suite (`npm test`) stays green after the type changes.
- **SC-008** ADRs 017–028 are listed exactly once each in `CLAUDE.md` with correct
  numbers.
- **SC-009** (from 004 cycle-1) OIDC auth is fail-closed: no dev stub fallback in
  production; `OIDC_ISSUER` and `exp` are mandatory; `kid` missing → reject. Verified
  by `test_oidc_fail_closed.py`.
- **SC-010** (from 004 cycle-1) Campaign ownership is DB-backed: play routes use
  `AccountRepository`, not `CampaignRegistry`; duplicate IDs → `409`;
  `account_id` is never `NULL`. Verified by `test_postgres_campaign_ownership.py`.
- **SC-011** (from 004 cycle-1) Session lease `takeover` validates `current_token`;
  lease expiry is `<=`. Verified by `test_postgres_leases.py`.
- **SC-012** (from 004 cycle-1) OTel is correctly instrumented: `instrument_app(app)`;
  `turn_span`/`narrator_span` wired; metrics emitted; no PII/traceback in spans or
  logs. Verified by `test_otel_instrumentation.py`.
- **SC-013** (from 004 cycle-1) `DELETE /me` returns `404` for non-existent accounts
  and requires confirmation. Verified by `test_account_endpoints.py`.
- **SC-014** (from 004 cycle-1) `GET /me/export` includes `save_slot` snapshots.
  Verified by `test_postgres_gdpr.py`.
- **SC-015** (from 004 cycle-1) Security audit logs cover sign-in/out, failed auth,
  lease ops, and account deletion. Verified by `test_security_audit_logging.py`.
- **SC-016** (from 004 cycle-1) CORS rejects `*` with credentials; OTLP defaults to
  TLS. Verified by `test_production_guards.py`.
- **SC-017** (from 004 cycle-1) Postgres integration tests pass against a live DB
  with `DATABASE_URL` set.
- **SC-018** (from 002 cycle-1) PostgreSQL connections use TLS by default in
  production. Verified by `test_postgres_storage.py` and `test_production_guards.py`.
- **SC-019** (from 002 cycle-1) `append_event` is concurrency-safe: concurrent writers
  produce unique, monotonic `seq` values. Verified by a new concurrent-append test in
  `test_postgres_storage.py`.
- **SC-020** (from 002 cycle-1) `PostgresStorage` has deterministic cleanup: `close()`
  disposes the engine and stops the daemon thread. Verified by teardown assertions in
  live-Postgres fixtures.
- **SC-021** (from 002 cycle-1) `_build_snapshot` captures an internally consistent
  snapshot. Verified by `test_postgres_storage.py`.
- **SC-022** (from 002 cycle-1) Identifier validation parity with `JSONStorage`:
  empty/`None`/`/`/`\`/`..` identifiers are rejected. Verified by
  `test_postgres_storage.py` and `test_storage_roundtrip.py`.
- **SC-023** (from 002 cycle-1) Consumer swap-boundary test includes `PostgresStorage`
  when `DATABASE_URL` is present. Verified by `tests/qa/test_storage_swap.py`.
- **SC-024** (from 002 cycle-1) Atomic-write test exercises a real mid-statement
  failure. Verified by `tests/server/test_atomic_writes.py`.
- **~~SC-025~~** SUPERSEDED BY ADR-029 / spec 007. ~~Combat victory via `POST /combat/round`~~
  — `combat.py` was deleted in spec 007. Replaced by: **SC-025b** — combat victory
  auto-resolved inside `POST /me/game/turn` triggers `_check_terminal_state`,
  archives the character, and marks the campaign ended. Verified by
  `test_combat_victory.py` (updated to use `POST /me/game/turn` path).
- **SC-026** (from 003 cycle-1) `PydanticNarrator` live path is exercised by an
  integration test with a mocked LLM (no `effects_applied`, no fabricated-number
  validator — both removed in spec 007). Verified by `test_narrator_integration.py`.
- **~~SC-027~~** SUPERSEDED BY ADR-029 / spec 007. ~~`combat_subagent.py` test.~~
  `combat_subagent.py` was deleted in spec 007 (ADR-029). No replacement needed.
- **SC-028** (from 003 cycle-1) Rate limiter keys on `account_id` when authenticated.
  Verified by `test_rate_limiter.py`.
- **SC-029** (from 003 cycle-1, updated for D1) `GET /me/graveyard` includes `name`,
  `created_at`, `ended_at`, and `ended_reason` for each ended campaign. Verified by
  `test_api_play_loop.py` (extended). _(With D1, there is no `list_campaigns` endpoint;
  the graveyard is the only multi-campaign view.)_
- **SC-030** (from 003 cycle-1) Python dependency ranges have upper bounds in
  `pyproject.toml`. Verified by inspection.
- **SC-031** (from 005 cycle-1) Source maps are disabled in production builds. Verified
  by `npm run build` and inspecting the output for `.map` files.
- **SC-032** (from 005 cycle-1) Content-Security-Policy header is present. Verified by
  inspecting `index.html` or response headers.
- **SC-033** (from 005 cycle-1) ErrorBoundary catches render errors. Verified by a test
  that throws in a child component and asserts the fallback UI.
- **SC-034** (from 005 cycle-1) CombatPanel validates `participants.length >= 2`.
  Verified by a test that renders CombatPanel with an empty/short participants array.
- **SC-035** (from 005 cycle-1) 401/403 redirects to `/auth`. Verified by a test that
  mocks a 401 response and asserts the redirect.
- **SC-036** (from 005 cycle-1) Token expiration is checked. Verified by a test that
  mocks an expired `expires_at` and asserts the redirect to `/auth`.

## Out of Scope

- OpenAPI codegen for TS types → future hardening slice (ADR-017 notes this).
- Typed discriminated-union Effect params (ADR-019 option 3) → future slice.
- Per-campaign subprocess isolation (ADR-018 option 1) → rejected, see ADR-018.
- Multi-tenant `StorageBackend` interface (ADR-018 option 3) → rejected, see ADR-018.
- Migration from `python-jose` to `PyJWT`/`authlib` → future hardening slice (noted
  as a dependency risk in ADR-022, not a blocker).
- MFA for `DELETE /me` (full multi-factor) → future hardening slice; this slice
  requires a confirmation token or password re-entry (FR-025).
- Bounded LRU cache with idle eviction for the `storage_factory` → future hardening
  concern (noted in ADR-018).
- SPA unit tests for Inventory, MapPanel, EmptyState, LoadingState, ErrorState,
  SessionConflict → deferred to a test-focused follow-up (005 QA deferred, non-blocking).
- E2E resume-across-devices (SC-002 from 005) → requires live backend or sophisticated
  mock state machine; defer until 003/004 integration testing.
- E2E single-active-session takeover (FR-013 from 005) → same rationale.
- Accessibility pass (T025 from 005) → important but not blocking for functional MVP.
- Performance measurements (SC-001 <3min onboarding, SC-002 <30s resume from 005) →
  requires production-like environment; defer to observability cycle.
- sessionStorage → httpOnly cookie-based auth → deferred to future hardening slice
  (acceptable until 004 OIDC ships).
- Network failure scenario tests → important but not blocking for MVP.
- Race condition tests in hooks → advanced testing; defer.

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

### Session 2026-06-28 (004 absorption)

- Q: Should 006 absorb all findings from the 004 review? → A: Yes. The 004 slice is
  extinct as a separate branch; all its remediation lives in 006. The `feat/004-auth-obs`
  implementation is the base; its findings are fixed here.
- Q: How to handle the ADR numbering conflict (004 ADRs 017–019 vs 006 ADRs 017–019)?
  → A: The 004 ADRs are renumbered to 022–024 when absorbed. ADR-020 is extended to
  cover this renumbering. A new ADR-025 (DB-backed campaign registry) is created.
- Q: Should `python-jose` be replaced with `PyJWT`/`authlib` in this slice? → A: No,
  retained for this slice. The migration is noted as a dependency risk in ADR-022 and
  deferred to a future hardening slice.
- Q: Should `DELETE /me` require full MFA? → A: No, a confirmation token or password
  re-entry is sufficient for this slice (FR-025). Full MFA is deferred.

### Session 2026-06-28 (002 absorption)

- Q: Should 006 also absorb the 002-persistence-foundation cycle-1 findings? → A: Yes.
  The 002 slice is already merged to `dev`; its remediation is implemented in-place on
  the 006 branch. All 002 findings are tracked as FR-037–FR-043 and SC-018–SC-024.
- Q: Why new ADRs 026–027 instead of amending ADR-014? → A: ADR-014 records the
  sync/async bridge decision, which is unchanged. The TLS policy (ADR-026) and the
  concurrency/lifecycle rules (ADR-027) are distinct production-hardening decisions
  that were not part of the original 002 design.
- Q: How to implement TLS without breaking local development? → A: Default-on TLS with
  an explicit `POSTGRES_SSL_MODE=disable` (or similar) env var for local dev. Production
  refuses to start if the URL lacks `sslmode` and the override is not set.
- Q: Should the 002 remediation include a subprocess-per-campaign redesign? → A: No.
  Per-call `campaign_id` through the MCP tool contract is the 001/006 design (ADR-018);
  the 002 hardening fixes the storage backend itself, not the multi-tenancy seam.

### Session 2026-06-28 (003 absorption)

- Q: The 003 review re-verifies all 001 findings — are those tracked separately? → A:
  No. The 003 re-verification confirms the 001 findings are still present on `dev`. The
  001 remediation (ADRs 017–020, FR-001–FR-017) covers them. Only the **new** 003
  findings (combat victory path, `request: Request = None`, rate limiter keying,
  narrator/combat subagent test coverage, `list_campaigns` fields, dependency upper
  bounds, learning lessons) are tracked as FR-044–FR-050 and SC-025–SC-030.
- Q: Should the combat victory path gap get its own ADR? → A: Yes — ADR-028. The
  decision to unify terminal-state checking into a shared helper (vs. duplicating the
  logic inline) is an architectural choice that warrants a decision record.
- Q: Should the `PydanticNarrator` test use a real LLM? → A: No. The test uses a mocked
  LLM that produces a valid `Scene` (and a fabricated-number scene). A real LLM test is
  non-deterministic and out of scope; the mocked test proves the validation → effects
  → response pipeline.
- Q: Should dependency upper bounds be strict pins? → A: No. Upper bounds
  (e.g. `<1.0`) prevent unexpected breaking changes from major releases while still
  allowing minor/patch updates. Strict pins would require manual updates for every
  patch release.

### Session 2026-07-01 (architectural decisions D1 + D2)

- Q: Should the frontend manage `campaign_id` explicitly (resource-scoped REST) or
  should the backend resolve the campaign from auth context (session-scoped)?
  → A: **Backend-scoped (D1)**. One active campaign per account. Frontend calls
  `/me/game/turn` etc. Backend does `JWT → account_id → SELECT campaign WHERE
  status='active'`. `campaign_id` is an internal routing detail, not exposed to the
  frontend. ADR-017 is amended accordingly.
- Q: Which Option for ADR-018 multi-tenant implementation? Option A (campaign_id in
  tools), Option B (per-campaign subprocess cache), or Option C (transparent wrapper)?
  → A: **Option A (D2)**. One MCP subprocess, `campaign_id: str` as first parameter in
  all 18 tools, `storage_factory: Callable[[str], StorageBackend]` in `build_server`.
  Narrator system prompt includes `campaign_id`; post-narration audit validates it.
  Option B rejected (N subprocesses ≈ N×50 MB, does not scale). Option C rejected
  (hidden complexity, no pydantic-ai extension point for transparent injection).
- Q: What is the production scaling path for the MCP transport?
  → A: Migrate `StdioTransport` → `StreamableHTTPTransport` when horizontal scaling is
  needed. With HTTP transport, `campaign_id` moves to an HTTP header or URL path. The
  18 MCP tool signatures stay unchanged. This is a transport-layer swap, not a
  business logic redesign.
- Q: What about the `/campaigns` list endpoints?
  → A: `/campaigns` (list) becomes `/me/graveyard` — shows ended campaigns (past
  heroes). There is no "list of active campaigns" because there is only one active
  campaign per account at any time.

### Session 2026-06-28 (005 absorption)

- Q: The 005 review returned PASS WITH CONDITIONS, not BLOCKED — should its findings be
  in 006? → A: Yes. The Tech Leader's report explicitly states the 005-specific items
  (source maps, CSP, ErrorBoundary, CombatPanel validation, 401/403, token expiration)
  "must be addressed in the 005 PR before merge or explicitly folded into 006." Folding
  them into 006 is the chosen path.
- Q: Does the 005 review need new ADRs? → A: No. All 005 findings are implementation
  bugs and configuration issues, not architectural decisions. No new ADR is created.
- Q: Should the SPA unit tests for Inventory/MapPanel/etc. be blocking? → A: No. The
  005 Tech Leader deferred them to cycle 2 as non-blocking. They are tracked in Out of
  Scope.
- Q: Should vitest be upgraded given it's a devDependency? → A: Yes. The CRITICAL CVE
  (GHSA-5xrq-8626-4rwp, CVSS 9.8) is dev-only but still a supply-chain risk. The fix
  is a simple version pin.
- Q: Should sessionStorage be replaced with httpOnly cookies? → A: Not in this slice.
  The 005 Security report notes sessionStorage is "acceptable until slice 004 OIDC."
  The 004 OIDC migration is in this slice, but the cookie-based auth swap is deferred
  to a future hardening slice.
