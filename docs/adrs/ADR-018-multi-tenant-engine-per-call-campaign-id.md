# ADR-018: Multi-tenant engine via per-call campaign_id

**Status**: Accepted | **Date**: 2026-06-28 | **Branch**: `feat/006-cycle1-remediation`

## Context

The SDD final review (cycle-1) found a **CRITICAL** architectural flaw: the web backend
starts ONE `MCPToolset` subprocess at app startup, scoped to a single
`GAMEBOOK_CAMPAIGN_ID` read once from the environment (`app.py:42-44`,
`mcp_host.py:45-56`). Every request from every account calls `call_engine(toolset, …)`
against this same single-campaign engine. The per-request `campaign_id` path parameter
is validated only against the in-memory `CampaignRegistry`; the actual engine state
(character, world, events, combat) is shared and unpartitioned.

Consequences:
- **Security A01**: total cross-account data leakage — Player A reads Player B's character.
- **QA Bug #5**: engine state not scoped per campaign — breaks FR-009 (isolation) and
  FR-011 (per-player persistence).
- **SC-005 unmet**: cannot support 1,000 concurrent campaigns.

The root cause is that `GAMEBOOK_CAMPAIGN_ID` is a **server-side env var, never derived
from the request**. The engine cannot serve multiple campaigns because it does not know
which campaign a call belongs to.

Options considered:

1. **Toolset per campaign** (subprocess pool): spawn one `MCPToolset` subprocess per
   campaign_id on first use, cache in a pool keyed by campaign_id. Each subprocess is
   booted with its own `GAMEBOOK_CAMPAIGN_ID`. Lifecycle: idle timeout → shutdown.
2. **Per-call campaign_id through the MCP tool contract** (chosen): every MCP tool
   gains a `campaign_id: str` parameter. The server maintains a `campaign_id →
   StorageBackend` registry; each tool call looks up (or lazily creates) the backend
   for that campaign and operates on it. The web layer passes `campaign_id` via
   `call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)`.
3. **Stateless engine + multi-tenant storage**: push campaign_id down into every
   `StorageBackend` method signature. The storage layer becomes multi-tenant; the
   engine stays stateless. Most invasive — rewrites the `StorageBackend` Protocol,
   all three implementations, and every test.

## Decision

**Option 2: per-call `campaign_id` through the MCP tool contract.** The
`StorageBackend` interface is **unchanged** (it remains a single-campaign backend —
Principle II preserved). Multi-tenancy is handled at the MCP server layer, which
maintains a `campaign_id → StorageBackend` registry.

### Design

1. **`build_server` gains a `storage_factory: Callable[[str], StorageBackend]`** instead
   of a single `storage` instance. The factory takes a `campaign_id` and returns a
   cached-or-new `StorageBackend` scoped to that campaign.
   - `JSONStorage`: factory returns a `JSONStorage(f"estado/{campaign_id}")`.
   - `PostgresStorage`: factory returns a `PostgresStorage(database_url, campaign_id)`.
   - `InMemoryStorage` (tests): factory returns a per-campaign dict-backed instance.
2. **Every MCP tool gains a `campaign_id: str` first parameter.** The tool body looks
   up `storage = storage_factory(campaign_id)` and proceeds as before. This is a
   **deliberate CONTRACTS.md §6 update** (Principle III) — the MCP tool contract
   changes from "campaign implied by env" to "campaign explicit per call".
3. **The web layer passes `campaign_id` on every `call_engine` call.** `call_engine(
   toolset, "read_character_sheet", campaign_id=campaign_id)` — `direct_call_tool`
   forwards kwargs as tool arguments, so no `mcp_host.py` change beyond the call sites.
4. **`GAMEBOOK_CAMPAIGN_ID` env var is removed from the web backend path.** The
   subprocess no longer boots scoped to one campaign; it boots with a `storage_factory`
   and serves any campaign. The Phase-1 MCP path (terminal harness, single campaign)
   still uses `GAMEBOOK_CAMPAIGN_ID` to pick the factory's default campaign.
5. **`CombatService`** is constructed per-campaign inside the factory (it depends on
   a `StorageBackend`), or the server holds a `campaign_id → CombatEngine` registry
   alongside the storage registry. The RNG can remain shared (it is stateless re:
   campaign).

### Why not option 1 (subprocess pool)

- A subprocess per campaign is heavy (memory, startup latency) at 1,000 concurrent
  campaigns (SC-005). Option 2 keeps one subprocess serving all campaigns.
- Option 1 does not require a contract change, but it hides multi-tenancy behind
  process isolation — the engine still cannot reason about which campaign a call is
  for, so cross-campaign features (e.g. a future admin API) remain impossible.
- Option 2 makes the campaign dimension explicit in the contract, which is honest.

### Why not option 3 (multi-tenant storage)

- It rewrites the `StorageBackend` Protocol — every method gains a `campaign_id`
  parameter — breaking all three implementations and every test. This is the most
  invasive change and violates the spirit of swap boundary #1 (the interface is
  supposed to be stable).
- Single-campaign backends are simpler and easier to reason about; multi-tenancy is
  an orchestration concern, not a storage concern.

## Consequences

**Positive**:
- One engine subprocess serves all campaigns (SC-005 feasible).
- `StorageBackend` interface unchanged — Principle II intact, swap boundary #1
  preserved, ADR-009's three-backend test still passes.
- The campaign dimension is explicit in the MCP contract — no hidden env-var scoping.
- Per-campaign isolation is enforceable: a tool call for campaign B cannot touch
  campaign A's storage because the factory hands back a different backend instance.

**Negative**:
- **CONTRACTS.md §6 must be updated** — every tool signature gains `campaign_id`.
  This is a deliberate contract change (Principle III), documented in the remediation
  spec.
- Every `call_engine(...)` call site in `play.py` and `combat.py` (~20 sites) must add
  `campaign_id=campaign_id`.
- Every engine test fixture must supply a `campaign_id` argument (or a default
  factory that ignores it for the in-memory path).
- The `storage_factory` must cache backends per campaign (otherwise every call
  re-constructs a `PostgresStorage` and re-opens a connection pool). A bounded LRU
  cache with idle eviction is the production shape; the remediation spec details it.

## When to retire

Not retired. If a future slice moves the engine to a multi-tenant storage layer
(option 3), this ADR is superseded — but that is not the current direction.

## Related

- Remediation spec: `specs/006-cycle1-remediation/spec.md`
- SDD review: `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
  (CRITICAL A01, Bug #5, SC-005)
- CONTRACTS.md §6 (MCP tool contract — must be updated in the remediation spec)
- ADR-009 (swap boundary tests through the consumer — must still pass after the change)
- ADR-007 (MCP server FastMCP stdio — unchanged; the transport is not the issue)
