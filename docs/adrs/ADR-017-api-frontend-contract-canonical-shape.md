# ADR-017: API/frontend contract canonical shape (backend wins)

**Status**: Accepted | **Date**: 2026-06-28 | **Branch**: `feat/006-cycle1-remediation`

## Context

The SDD final review (cycle-1, 20260628-0752) found **HIGH-severity contract drift**
between the FastAPI backend (slice 003) and the React SPA (slice 005). The frontend was
developed entirely in mock mode (`VITE_USE_MOCK=true`) and was never integrated against
the live backend, so the TypeScript types drifted from the Pydantic response models:

| Endpoint | Backend response (Pydantic) | Frontend type (TS) |
|---|---|---|
| `POST /turn` | `{scene, character, world, effects_applied}` | `{scene, campaign}` |
| `POST /combat/round` | `{outcome, final_result, character, campaign_ended}` | `{round, combat, campaign}` |
| `POST /combat/flee` | `{result, character, campaign_ended}` | `{campaign}` |
| Campaign identifier | `campaign_id` | `id` |

In live mode `res.campaign` is `undefined`, so `setCampaign(undefined)` breaks the play
loop (`useGame.ts:112`). The SPA is currently mock-only.

Options considered:

1. **Backend canônico** (chosen): the frontend TS types are adjusted to match the
   existing Pydantic models. The OpenAPI schema (auto-generated from Pydantic) is the
   single source of truth; the SPA consumes it.
2. **Frontend canônico**: the backend Pydantic models are rewritten to deliver
   `{scene, campaign}`, `{round, combat, campaign}`, `id`. More backend work; the
   aggregated `campaign` envelope requires the backend to re-read full state after
   every turn/combat call.
3. **Híbrido por endpoint**: decide per endpoint which side concedes. Maximizes local
   convenience at the cost of a consistent rule.

## Decision

**The backend Pydantic models are canonical.** The frontend TypeScript types are
adjusted to match them. Specifically:

- `TurnResponse` (TS) → `{ scene, character?, world?, effects_applied }`
- `CombatRoundResponse` (TS) → `{ outcome, final_result?, character?, campaign_ended }`
- `FleeCombatResponse` (TS) → `{ result, character?, campaign_ended }`
- Campaign identifier everywhere → `campaign_id` (not `id`)
- `CampaignSummary` (TS) → `{ campaign_id, status, name?, created_at?, updated_at? }`
  (backend extends `CampaignResponse` with `name`/timestamps in the remediation spec)

The OpenAPI document at `/openapi.json` is the **frozen contract** the SPA consumes.
A codegen step (or manual type sync) keeps the TS types aligned with the OpenAPI
schema; the integration test added in the remediation spec enforces this at CI time.

## Consequences

**Positive**:
- One canonical source of truth (Pydantic → OpenAPI → TS), aligned with Principle III
  (CONTRACTS.md is the single source of truth) and SC-007 (full play loop via API docs).
- No backend re-read of full campaign state after every turn — the SPA composes
  `CampaignState` from the granular fields it already receives (`character`, `world`).
- The OpenAPI document remains the externally-usable surface (FR-017) — external
  clients see the same shape the SPA sees.
- Minimal backend churn; the remediation work concentrates on the frontend.

**Negative**:
- The SPA loses the convenience of a single aggregated `campaign` object per response;
  `useGame.applyTurnResponse` must assemble `CampaignState` from `character` + `world`
  + the existing `campaign` (for fields not in the response, e.g. `current_scene`).
- TS types must be kept in sync with OpenAPI; without codegen this is manual. The
  integration test is the safety net, not a guarantee.

## When to retire

Not retired. If a future slice introduces OpenAPI codegen (e.g. `openapi-typescript`),
the manual sync is replaced by codegen; the decision (backend canonical) stands.

## Related

- Remediation spec: `specs/006-cycle1-remediation/spec.md`
- SDD review: `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
  (Bugs #1–4, #6)
- CONTRACTS.md §6 (MCP tool contract) and the HTTP API contract draft
  (`specs/001-web-platform-migration/contracts/http-api.md`) must be reconciled with
  this decision in the remediation spec.
