# Research: Cycle-1 Remediation (006)

**Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This is a remediation slice — all architectural decisions were made before implementation
and are recorded as ADRs 017–029. This document consolidates those decisions in the
format required by the plan workflow: Decision / Rationale / Alternatives considered.

---

## Decision 1: Multi-tenant engine via per-call campaign_id (ADR-018, Option A)

**Decision**: One MCP subprocess at startup serves all campaigns. Every MCP tool
gains `campaign_id: str` as its first parameter. `build_server` takes a
`storage_factory: Callable[[str], StorageBackend]` that returns a cached (or fresh)
backend scoped to the campaign. The `storage_factory` cache is a `dict[str,
StorageBackend]` for the MVP; LRU eviction is documented as a future hardening
requirement.

**Rationale**: The single-process model avoids the N×50MB memory cost of one subprocess
per campaign (N campaigns at 50MB/process = 50GB at 1,000 campaigns). The
`storage_factory` pattern preserves the `StorageBackend` interface (Principle II) and
makes campaign-scoping explicit in the tool contract (Principle III). One subprocess
also avoids subprocess cold-start latency on every request.

**Alternatives considered**:
- **Option B (subprocess per campaign)**: one Python subprocess per active campaign
  (40–50MB each). Does not scale. Rejected.
- **Multi-tenant `StorageBackend`**: rewrites every storage method and every test.
  Violates spirit of swap boundary #1. Rejected.
- **Per-request toolset**: same memory problem as subprocess per campaign, plus
  cold-start latency. Rejected.

---

## Decision 2: Scoped toolset wrapper for campaign_id enforcement (D2 + T006b)

**Decision**: The narrator's `MCPToolset` is wrapped in a `ScopedMCPToolset` that
overrides `campaign_id` on every tool call with the value resolved by the web layer.
The LLM is removed from the security-critical path. A post-narration audit
(`_assert_narrator_campaign`) is kept as belt-and-suspenders.

**Rationale**: The post-narration audit is detection, not prevention — if the LLM passes
the wrong `campaign_id`, the tool side-effects happen against the wrong storage before
the audit fires. The scoped toolset wrapper is prevention: the correct `campaign_id` is
enforced before each tool call reaches the MCP server. The LLM can include `campaign_id`
in its call or omit it — the wrapper enforces the correct value either way.

**Alternatives considered**:
- **Audit-only (post-narration detection)**: detects wrong `campaign_id` but does not
  prevent writes to the wrong storage. Kept as belt-and-suspenders but not the primary
  defense.
- **HTTP transport header (future)**: when `StdioTransport` → `StreamableHTTPTransport`,
  `campaign_id` moves to an HTTP header set by the gateway. The LLM never sees or
  touches it. This is the definitive solution; the scoped wrapper is the correct
  intermediate step.

---

## Decision 3: Backend-scoped routes — `/me/game/...` (ADR-017 amendment, D1)

**Decision**: All game-play routes redesigned from resource-scoped (`/campaigns/{id}/...`)
to session-scoped (`/me/game/...`). The backend resolves `campaign_id` from
`JWT → account_id → active campaign`. One active campaign per account. Frontend has no
awareness of `campaign_id`. Ended campaigns surfaced via `GET /me/graveyard`.

**Rationale**: (1) Eliminates IDOR by design — `campaign_id` does not appear in URLs;
a player cannot guess or enumerate other campaigns' IDs. (2) Single source of truth for
"active campaign" — the backend decides; the frontend treats the game as a singleton
session. (3) Aligns with ADR-029: the narrator calls MCP tools with `campaign_id`
resolved internally, not from URL path parameters. (4) Future-proof for HTTP transport:
`campaign_id` is already internal; migration to HTTP header is transparent to the
frontend.

**Alternatives considered**:
- **Frontend-managed campaign_id** (`useGame(campaignId)`): requires the client to store
  and pass campaign IDs, introducing IDOR risk and unnecessary state. Rejected.
- **Resource-scoped routes with auth checks** (original ADR-017): the `_campaign_or_404`
  pattern was defense-in-depth against IDOR, but left `campaign_id` visible in URLs and
  in frontend state. Superseded by D1.

---

## Decision 4: Graveyard is read-only (scoped to this slice)

**Decision**: `GET /me/graveyard` is a read-only endpoint listing ended campaigns
(death + victory). Individual entry deletion is not implemented in this slice.
`DELETE /me` (GDPR erasure) cascades all data including graveyard entries.

**Rationale**: The MVP scope is bounded — no new features, only fixes. Individual
graveyard deletion is a UX nicety, not a security or correctness requirement.
`DELETE /me/graveyard/{id}` is the natural extension point when needed.

---

## Decision 5: `_get_active_campaign` returns structured 404 for no active campaign

**Decision**: When no active campaign exists (first visit or all campaigns ended),
`_get_active_campaign` returns `404 no_active_campaign` with
`hint: "POST /me/game to start a new game"`, not a generic 404. The SPA intercepts
this specific error code and routes the player to the start screen.

**Rationale**: A generic 404 is ambiguous — the SPA cannot distinguish "campaign not
found" from "server error" without inspecting the error code. A structured error code
enables the SPA to provide the correct UX (start screen) without fragile string matching
on error messages.

---

## Decision 6: ADR-019, ADR-028 superseded by spec 007 / ADR-029

**Decision**: `effects[]`, `EffectType`, `_RESULT_KEYS`, `_scene_contains_fabricated_numbers`,
`combat.py`, `combat_subagent.py`, `CombatRoundResponse`, and `FleeCombatResponse`
were all deleted in spec 007 (ADR-029). No implementation work is needed for
ADR-019 (allowlist) or ADR-028 (combat terminal-state unification).

**Rationale**: The narrator now calls MCP tools directly during `agent.run()` and
narrates only what it observes from real tool responses. Principle I ("numbers never in
prose") is enforced by architecture, not by a post-hoc validator. Combat is
auto-resolved inside `POST /me/game/turn`.

---

## Decision 7: storage_factory cache — dict MVP, LRU future

**Decision**: The `storage_factory` cache is a plain `dict[str, StorageBackend]` for
the MVP. LRU eviction (evict least-recently-used backend when cache size exceeds a
threshold, e.g. 500) is documented in a code comment as a required hardening step before
production at scale.

**Rationale**: At MVP scale (tens to hundreds of campaigns), an unbounded dict is safe.
At production scale (thousands of campaigns), unbounded growth is a memory leak. LRU is
the standard cache pattern; `functools.lru_cache` or a lightweight `OrderedDict`-based
implementation suffices. The code comment preserves this knowledge for the next slice.

---

## Superseded / No-research items

| Item | Disposition |
|------|-------------|
| `python-jose` vs `PyJWT`/`authlib` | Retained per ADR-022; migration deferred |
| OTel backend choice (Jaeger/Tempo/etc.) | Unchanged — OTLP-compatible; choice is ops, not code |
| Session storage for leases | DB-backed via `LeaseService`/`AccountRepository` (ADR-023/025) |
| Frontend auth storage (sessionStorage vs httpOnly cookie) | Deferred to future slice per ADR-022 |
