# HTTP API Contract Changes: Narrator Tool-Use Refactor

**Feature**: 007-narrator-tool-use-refactor
**Date**: 2026-06-30
**Base contract**: `docs/CONTRACTS.md §9` (HTTP API) + `§10` (Scene)

This document records every HTTP API surface change introduced by this slice. All other
endpoints and response shapes remain unchanged.

---

## Endpoints Removed

### `POST /campaigns/{campaign_id}/combat/round`

**Status**: Removed (404)

**Reason**: Combat resolves inside the narrator's `POST /turn` call. No stepwise endpoint needed.

**Before**:
- Request: `{ test_luck: bool }`
- Response: `CombatRoundResponse { outcome, final_result?, character?, campaign_ended }`

**After**: 404 Not Found

---

### `POST /campaigns/{campaign_id}/combat/flee`

**Status**: Removed (404)

**Reason**: Flee decision is made pre-combat as a turn choice. No mid-combat flee endpoint needed.

**Before**:
- Request: `{}`
- Response: `FleeCombatResponse { result, character?, campaign_ended }`

**After**: 404 Not Found

---

## Response Shapes Changed

### `POST /campaigns/{campaign_id}/turn` → `TurnResponse`

**Before**:
```json
{
  "scene": {
    "narrative": "You face the goblin...",
    "choices": [{"id": "1", "label": "Fight"}, {"id": "2", "label": "Flee"}],
    "effects": [
      {"type": "start_combat", "params": {"enemies": [...]}},
      {"type": "resolve_combat_round", "params": {}}
    ]
  },
  "character": { ... },
  "world": { ... },
  "effects_applied": [
    {"type": "start_combat", "result": {"combat_id": "abc"}},
    {"type": "resolve_combat_round", "result": {"hero_as": 14, "enemy_as": 11, ...}}
  ]
}
```

**After**:
```json
{
  "scene": {
    "narrative": "You face the goblin. Your sword flashes and finds its mark. After three brutal rounds you stand victorious, stamina reduced but alive.",
    "choices": [{"id": "1", "label": "Search the body"}, {"id": "2", "label": "Press on"}]
  },
  "character": { ... },
  "world": { ... }
}
```

**Key differences**:
- `scene.effects` field removed
- `effects_applied` field removed from `TurnResponse`
- Narrative now contains real combat numbers (narrator saw tool results during generation)

---

### `GET /campaigns/{campaign_id}/scene` → stored `Scene`

The stored `Scene` shape also simplifies (no `effects` field). Clients reading the current scene
get `{ narrative, choices }` only.

---

## Endpoints Unchanged

All other endpoints remain identical in signature and behavior:

| Endpoint | Change |
|---|---|
| `POST /campaigns` | None |
| `GET /campaigns` | None |
| `GET /campaigns/{id}` | None |
| `DELETE /campaigns/{id}` | None |
| `POST /campaigns/{id}/character` | None |
| `GET /campaigns/{id}/character` | None |
| `GET /campaigns/{id}/scene` | Scene shape simplified (no effects field) |
| `POST /campaigns/{id}/save` | None |

---

## Frontend Migration

The frontend must update:
1. Remove rendering of `TurnResponse.effects_applied` (debug panel or any UI that displays effects)
2. Remove `TurnResponse.effects_applied` from TypeScript types
3. Remove `Scene.effects` from `Scene` TypeScript type
4. Remove any combat-round polling logic that relied on `POST /combat/round`

No new frontend endpoints or UI flows are required. Combat is now narrated in prose by the
turn response — no structured combat UI update needed (that would be a future feature).
