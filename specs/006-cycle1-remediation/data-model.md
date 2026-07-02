# Data Model: Cycle-1 Remediation (006)

**Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

This remediation slice does not introduce new domain entities — it refactors seams,
fixes bugs, and hardens existing paths. The data model changes below are either new
helper types (GraveyardEntry), signature changes (storage_factory, MCP tools), or
field additions (CampaignState.name).

---

## Changed: MCP tool signatures (ADR-018, Option A)

Every MCP tool in `src/gamebook/mcp/server.py` gains `campaign_id: str` as its **first
parameter**. The tools are unchanged in behaviour; `campaign_id` routes the call to the
correct per-campaign `StorageBackend`.

```
Before: read_character_sheet() -> CharacterSheet | None
After:  read_character_sheet(campaign_id: str) -> CharacterSheet | None

Before: create_character(name: str) -> CharacterSheet
After:  create_character(campaign_id: str, name: str) -> CharacterSheet

Before: roll_dice(notation: str) -> DiceResult
After:  roll_dice(campaign_id: str, notation: str) -> DiceResult
```

All 18 tools follow the same pattern. See `docs/CONTRACTS.md` §6 for the full list.

---

## Changed: `build_server` signature (ADR-018)

```python
# Before
def build_server(storage: StorageBackend, rng: RandomSource) -> FastMCP

# After
def build_server(
    storage_factory: Callable[[str], StorageBackend],
    rng: RandomSource,
) -> FastMCP
```

`storage_factory` takes a `campaign_id: str` and returns (or creates) the
`StorageBackend` for that campaign. The factory is cached internally:

```python
_cache: dict[str, StorageBackend] = {}

def _factory(campaign_id: str) -> StorageBackend:
    if campaign_id not in _cache:
        _cache[campaign_id] = make_backend(campaign_id)
    return _cache[campaign_id]
# Note: replace dict with LRU (max_size ~500) before production at scale
```

---

## New: `ScopedMCPToolset` (D2, T006b)

Helper in `src/gamebook_web/harness/agent.py` that wraps `MCPToolset` and overrides
`campaign_id` on every tool call.

```python
class ScopedMCPToolset:
    base: MCPToolset
    campaign_id: str

    async def call_tool(name: str, arguments: dict, **kw) -> Any:
        arguments = {**arguments, "campaign_id": campaign_id}
        return await base.call_tool(name, arguments, **kw)
```

Used by the narrator during `agent.run()`. Ensures the LLM cannot pass a wrong
`campaign_id` to engine tools.

---

## Changed: `CampaignState` (in `sessions/campaign.py`)

```python
# Added field
name: str | None = None       # optional run name set at campaign creation
```

Used by `POST /me/game` (body.name), `GET /me/game`, and `GET /me/graveyard`.

---

## New: `GraveyardEntry` (frontend type + API response)

```typescript
// frontend/src/types/index.ts
interface GraveyardEntry {
  campaign_id: string
  status: 'ended'
  name?: string
  created_at?: string
  ended_at?: string
  ended_reason?: 'death' | 'victory'
}
```

Backend: `GET /me/graveyard` returns `list[GraveyardEntry]` — all campaigns for the
authenticated account with `status = 'ended'`.

---

## Changed: `TurnResponse` (removed `effects_applied`)

```python
# Before (spec 007 deleted effects[])
class TurnResponse(BaseModel):
    scene: dict
    status: str
    character: dict | None = None
    world: dict | None = None
    # effects_applied: list  ← DELETED in spec 007

# After
class TurnResponse(BaseModel):
    scene: dict
    status: str
    character: dict | None = None
    world: dict | None = None
```

Frontend `TurnResponse` type also removes `effects_applied`. `CombatRoundResponse` and
`FleeCombatResponse` are fully removed.

---

## Changed: `GameState` (frontend, replaces `CampaignState` on the frontend)

```typescript
// frontend/src/types/index.ts
// Before
interface CampaignState {
  campaign_id: string   // ← REMOVED per D1 (frontend has no campaign_id awareness)
  status: CampaignStatus
  character?: CharacterSheet
  world?: WorldState
  current_scene?: Scene
  combat?: CombatState | null  // ← REMOVED (combat auto-resolved in turn)
}

// After
interface GameState {
  status: 'active' | 'ended' | 'no_active_campaign'
  character?: CharacterSheet
  world?: WorldState
  current_scene?: Scene
}
```

---

## Unchanged: StorageBackend interface

The `StorageBackend` Protocol in `src/gamebook/storage/base.py` is **unchanged**. The
multi-tenancy is at the MCP server layer (via `storage_factory`), not in the storage
interface. Principle II (dependency on interfaces only) is preserved.

---

## Entities NOT changed

| Entity | Status | Reason |
|--------|--------|--------|
| `CharacterSheet` | Unchanged | Domain entity; not modified |
| `World` / `WorldState` | Unchanged | Domain entity; not modified |
| `Event` / `ArchiveRecord` | Unchanged | Domain entity; not modified |
| `Combat` | Unchanged | Domain entity; not modified |
| `Scene` / `Choice` | Unchanged | Spec 007 already updated |
| DB schema (Alembic) | No new migration | Existing tables cover accounts, campaigns, leases |
