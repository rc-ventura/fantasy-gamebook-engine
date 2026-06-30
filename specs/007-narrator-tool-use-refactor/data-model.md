# Data Model: Narrator Tool-Use Refactor

**Feature**: 007-narrator-tool-use-refactor
**Date**: 2026-06-30

This document tracks the before/after shape of every model changed by this slice.
No new entities are introduced. Existing entities simplify.

---

## Scene (harness/scene.py)

### Before

```python
EFFECT_TO_MCP_TOOL: dict[str, str] = {
    "roll_dice": "roll_dice",
    "test_luck": "test_luck",
    "update_character": "update_character_sheet",
    "register_event": "register_event",
    "update_world": "update_world",
    "start_combat": "start_combat",
    "resolve_combat_round": "resolve_combat_round",
    "flee_combat": "flee_combat",
    "end_combat": "end_combat",
}

EffectType = Literal[
    "roll_dice", "test_luck", "update_character", "register_event",
    "update_world", "start_combat", "resolve_combat_round", "flee_combat", "end_combat"
]

class Effect(BaseModel):
    type: EffectType
    params: dict[str, Any] = {}

class Choice(BaseModel):
    id: str
    label: str

class Scene(BaseModel):
    narrative: str
    choices: list[Choice] = []
    effects: list[Effect] = []        # ← REMOVED

    @field_validator("narrative")
    @classmethod
    def narrative_not_empty(cls, v: str) -> str: ...

    @property
    def is_terminal(self) -> bool:
        return len(self.choices) == 0
```

### After

```python
class Choice(BaseModel):
    id: str
    label: str

class Scene(BaseModel):
    narrative: str
    choices: list[Choice] = []

    @field_validator("narrative")
    @classmethod
    def narrative_not_empty(cls, v: str) -> str: ...

    @property
    def is_terminal(self) -> bool:
        return len(self.choices) == 0
```

**Removed**: `EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect`, `Scene.effects` field.

---

## TurnResponse (api/play.py)

### Before

```python
class TurnResponse(BaseModel):
    scene: dict[str, Any]
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None
    effects_applied: list[dict[str, Any]] = []    # ← REMOVED
```

### After

```python
class TurnResponse(BaseModel):
    scene: dict[str, Any]
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None
```

---

## NarratorContext (harness/base.py)

No field changes. Docstring update only: remove the claim that state changes happen only via
`Scene.effects[]`.

### Before (docstring excerpt)

```python
"""Engine state snapshot read before narrating a turn.
State changes happen ONLY via ``Scene.effects[]`` executed through MCP — never
by the narrator directly (Principle I).
"""
```

### After

```python
"""Engine state snapshot read before narrating a turn.
The narrator reads these fields and then calls MCP tools directly during generation.
State is updated during narrator.narrate() — not after.
"""
```

---

## CombatResult (harness/combat_subagent.py) — REMOVED

This model is deleted with `combat_subagent.py`. No replacement. Combat outcome is narrated
directly by the main narrator agent from `end_combat` tool result.

---

## Frontend: TurnResponse type

### Before (approximate TypeScript)

```typescript
interface TurnResponse {
  scene: Scene;
  character?: CharacterSheet;
  world?: World;
  effects_applied: EffectResult[];   // ← REMOVED
}
```

### After

```typescript
interface TurnResponse {
  scene: Scene;
  character?: CharacterSheet;
  world?: World;
}
```

---

## CONTRACTS.md §10 — Scene contract

### Before

```
Scene: { narrative: str, choices: list[Choice], effects: list[Effect] }
Effect: { type: EffectType, params: dict }
EffectType: Literal["roll_dice", "test_luck", "update_character", "register_event",
    "update_world", "start_combat", "resolve_combat_round", "flee_combat", "end_combat"]

Lifecycle: POST /turn → narrator emits Scene → validator rejects literals →
effects[] executed through MCP → Scene returned to UI.
```

### After

```
Scene: { narrative: str, choices: list[Choice] }

Lifecycle: POST /turn → narrator calls MCP tools during generation (reads state,
resolves combat, applies changes) → returns Scene (all state already updated) →
API refreshes state, checks terminal conditions, returns TurnResponse.
```

---

## Entities unchanged

The following engine domain models are **not modified** by this slice:

- `CharacterSheet` (`domain/models.py`) — unchanged
- `World` (`domain/models.py`) — unchanged
- `Event` (`domain/models.py`) — unchanged
- `Combat` (`domain/models.py`) — unchanged
- `ArchiveRecord` (`domain/models.py`) — unchanged
- `StorageBackend` interface — unchanged
- All 18 MCP tool signatures — unchanged
- `NarratorBackend` protocol — unchanged
