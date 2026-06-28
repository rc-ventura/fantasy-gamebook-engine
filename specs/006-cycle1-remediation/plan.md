# Implementation Plan: Cycle-1 Remediation

**Branch**: `006-cycle1-remediation` | **Date**: 2026-06-28 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-cycle1-remediation/spec.md` and the
SDD final review `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`.
Architectural decisions are recorded in ADRs 017–020 (created alongside this plan).

## Summary

Close the cycle-1 SDD findings so the web backend + SPA are live-mode functional and
safe to deploy behind a single-campaign dev constraint. The work has three tracks:

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
   numbers (ADR-019), ADR renumbering (ADR-020).

Session-lease enforcement (FR-025) is deferred to slice `004`.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript (frontend).

**Primary Dependencies**:
- *Existing, unchanged*: `fastmcp`, `pydantic` v2, `fastapi`, `pydantic-ai`,
  `uvicorn`, `slowapi`, the `PostgresStorage` + Alembic stack, React/Vite/Playwright.
- *No new dependencies* — this is a fix slice, not a feature slice.

**Storage**: PostgreSQL via `PostgresStorage` (unchanged interface); the
`storage_factory` in ADR-018 constructs per-campaign `PostgresStorage` instances.

**Testing**: `pytest` (backend), `vitest` + `playwright` (frontend). New tests:
`test_multi_campaign_isolation.py`, `test_production_guards.py`, a live-backend
Playwright suite. The plugability audit stays a merge gate.

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

**Scale/Scope**: One process serving N campaigns (SC-005). No new accounts (dev auth
stub remains; real auth is `004`).

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
- **ADR renumbering (ADR-020)**: rename the pydantic-ai ADR file to ADR-021; delete the two "moved" stubs; update `CLAUDE.md` and the learning-lesson cross-link.

## Complexity Tracking

| Complexity | Description | Simpler rejected alternative |
|---|---|---|
| `storage_factory` seam in `build_server` | New `Callable[[str], StorageBackend]` parameter; per-campaign cache | Single storage + env-var campaign (rejected: causes the CRITICAL cross-account leak) |
| `campaign_id` on every MCP tool | 18 tool signatures change; CONTRACTS.md §6 update | Subprocess per campaign (rejected: heavy at 1k campaigns, ADR-018 option 1) |
| Frontend `CampaignState` assembly | `useGame` composes state from granular fields instead of reading `res.campaign` | Backend aggregates `campaign` per response (rejected: backend re-reads full state every turn) |
| Allowlist per effect type | `_ALLOWED_EFFECT_PARAMS` mapping + validator rewrite | Expand the denylist (rejected: whack-a-mole, ADR-019 option 1) |

## Action Items

- [ ] CONTRACTS.md §6 updated for `campaign_id` (FR-017, Principle III)
- [ ] HTTP API contract draft reconciled with ADR-017 canonical shapes
- [ ] ADRs 017–020 linked from `CLAUDE.md` ADR table; ADR-021 (renamed pydantic-ai) listed
- [ ] `docs/learning-lessons/pydantic_ai_v2_mcp_toolset_direct_call_pattern.md` cross-link updated to ADR-021
- [ ] SDD cycle-1 report referenced from the remediation spec

## Pre-Implementation High-Level Task Breakdown

See [tasks.md](./tasks.md) for the ordered, dependency-grouped task list. Phases:

1. **Phase 1 — ADR-018 multi-tenant engine** (CRITICAL, blocks everything): `build_server` + tool signatures + `main()` + web call sites + test fixtures.
2. **Phase 2 — ADR-017 contract alignment** (HIGH): frontend TS types + `useGame` assemblers + integration test.
3. **Phase 3 — Production guards** (CRITICAL/HIGH): dev-auth guard + docs disable + security logging.
4. **Phase 4 — MEDIUM fixes**: victory flag, `create_campaign` name, session-lease gating, `GET /me`, vite pin.
5. **Phase 5 — LOW + GOVERNANCE**: dev-token, CORS, allowlist (ADR-019), ADR renumbering (ADR-020).
6. **Phase 6 — Verification**: full suite + plugability audit + live Playwright + multi-campaign isolation test.
