# Implementation Plan: Narrator Tool-Use Refactor

**Branch**: `007-narrator-tool-use-refactor` | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-narrator-tool-use-refactor/spec.md`

---

## Summary

Eliminate the `effects[]` deferred-execution pattern from the PydanticAI narrator and replace
it with direct MCP tool calls during generation — identical to how the Phase 1 terminal narrator
works. The narrator's system prompt changes from "emit engine operations as effects[]" to "call
MCP tools, see real results, narrate real numbers." Seven named constructs are removed with no
replacements. Combat resolves inside the turn. The `Scene` model shrinks to `narrative + choices`.

**Pre-condition (PC-001)**: ✅ RESOLVED — `update_character_sheet` is set-based (absolute values,
not deltas). Idempotent under retry. Source: `src/gamebook/mcp/server.py:158-165`.

---

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5.x

**Primary Dependencies**: PydanticAI (narrator agent), FastAPI (web service), FastMCP (MCP server),
Pydantic v2 (models), pytest (backend tests), Vitest (frontend tests)

**Storage**: PostgresStorage behind StorageBackend — unchanged. Engine state unchanged.

**Testing**: `uv run pytest -q` (backend), `npm run test` in `frontend/` (frontend)

**Target Platform**: FastAPI web service (Linux server) + React SPA (browser)

**Project Type**: Web service + SPA (backend refactor + minor frontend contract update)

**Performance Goals**: No regression — narrator turn latency may increase slightly (narrator
makes more tool calls during generation instead of a deferred batch). Acceptable trade-off.

**Constraints**: MCP tool contract unchanged. `NarratorBackend` protocol unchanged.
`StorageBackend` interface unchanged. Engine (`src/gamebook/`) unchanged.

**Scale/Scope**: 5 backend files modified, 3 files deleted, 1 file simplified, ~20-30 tests
updated. Minor frontend type update. ~2-3 days of focused implementation.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **I. Numbers Never in Prose** | ✅ ENFORCED BY DESIGN | This slice's purpose. After: narrator calls tools, sees real numbers, narrates them. No validator needed. |
| **II. Dependency on Interfaces Only** | ✅ NO VIOLATION | `NarratorBackend` protocol stays. Scene model simplifies but doesn't break the port. Engine interfaces unchanged. |
| **III. CONTRACTS.md Single Source of Truth** | ⚠️ REQUIRED UPDATE | `CONTRACTS.md §10` must be updated in the same change (Scene drops effects[]). Covered in Phase 1 contracts. |
| **IV. Determinism and Isolated Testing** | ✅ NO VIOLATION | Plugability audit unaffected. FakeNarrator updated to not use effects[]. All tests must stay green. |
| **V. Domain Invariants and Atomic Persistence** | ✅ NO VIOLATION | PC-001 confirmed set-based mutations. No atomicity regression vs current design. |

**Gate result**: PASS. Constitution check re-evaluated post-design (Phase 1) — no violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/007-narrator-tool-use-refactor/
├── plan.md              # This file
├── research.md          # Phase 0 — PC-001 audit + mutation semantics
├── data-model.md        # Phase 1 — Scene before/after, TurnResponse changes
├── quickstart.md        # Phase 1 — validation guide
├── contracts/
│   └── http-api-changes.md   # Phase 1 — removed endpoints + updated response shapes
├── checklists/
│   └── requirements.md       # Spec quality checklist (already created)
└── tasks.md             # Phase 2 — /speckit-tasks output (not yet created)
```

### Source Code Changes

```text
# MODIFIED
src/gamebook_web/harness/agent.py
    - Remove _scene_contains_fabricated_numbers, _RESULT_KEYS, _NUMBERS_NEVER_IN_PROSE_RULE
    - Update system prompt: direct tool use instead of effects[]
    - Simplify output_validator: narrative quality only (not fabricated number detection)
    - Keep toolsets=[toolset] pass-through (already correct)

src/gamebook_web/harness/scene.py
    - Remove EFFECT_TO_MCP_TOOL, EffectType, Effect
    - Scene: keep narrative + choices, remove effects field

src/gamebook_web/harness/base.py
    - Update FakeNarrator _DEFAULT_OPENING_SCENE and _DEFAULT_FOLLOWUP_SCENE
      (remove effects[] from both default scenes)
    - Update NarratorContext docstring (remove "effects[] are the only state-change path" claim)

src/gamebook_web/api/play.py
    - Remove _apply_scene_effects, _build_tool_args, _CHANGES_WRAPPED
    - Remove EFFECT_TO_MCP_TOOL import
    - Remove effects_applied step from take_turn (Step 4 of current flow)
    - Remove effects_applied field from TurnResponse

docs/CONTRACTS.md
    - Update §10: Scene = {narrative: str, choices: list[Choice]} — no effects
    - Update TurnResponse shape (remove effects_applied)

frontend/src/api/types.ts (or equivalent)
    - Remove effects_applied from TurnResponse type

# DELETED
src/gamebook_web/harness/combat_subagent.py       ← removed entirely
src/gamebook_web/api/combat.py                     ← removed entirely
tests/server/test_scene_effects_contract.py        ← removed (no lockstep to test)

# UPDATED TESTS
tests/server/test_api_play_loop.py ← remove all effects_applied assertions (canonical name; test_play_routes.py does not exist)
# Note: test_narrator.py does not exist — FakeNarrator-based assertions are in test_api_play_loop.py and test_scene_numbers.py
[any test asserting TurnResponse.effects_applied or Scene.effects]
```

---

## Complexity Tracking

No Constitution violations requiring justification. All gates passed.

---

## Phase 0: Research

*See [research.md](./research.md) for full findings.*

**Summary of resolved unknowns**:

| Unknown | Resolution |
|---|---|
| PC-001: `update_character_sheet` mutation semantics | SET-BASED. Confirmed idempotent. |
| PydanticAI tool-use during `output_type` generation | Supported by design — toolsets are called during run, output_type constrains only the final return. |
| Combat tool call safety under narrator retry | `start_combat` creates state; `end_combat` closes it. Narrator skill must finish combat before returning Scene. Validated by existing Phase 1 pattern. |

---

## Phase 1: Design Artifacts

### 1. Data Model Changes

*See [data-model.md](./data-model.md) for full before/after.*

**Scene** (simplified):
```python
# BEFORE
class Scene(BaseModel):
    narrative: str
    choices: list[Choice] = []
    effects: list[Effect] = []          # ← REMOVED

# AFTER
class Scene(BaseModel):
    narrative: str
    choices: list[Choice] = []
```

**TurnResponse** (simplified):
```python
# BEFORE
class TurnResponse(BaseModel):
    scene: dict[str, Any]
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None
    effects_applied: list[dict[str, Any]] = []   # ← REMOVED

# AFTER
class TurnResponse(BaseModel):
    scene: dict[str, Any]
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None
```

### 2. Contracts

*See [contracts/http-api-changes.md](./contracts/http-api-changes.md).*

**Endpoints removed**:
- `POST /campaigns/{id}/combat/round`
- `POST /campaigns/{id}/combat/flee`

**Response shapes updated**:
- `TurnResponse`: `effects_applied` field removed
- `Scene` (embedded in TurnResponse): `effects` field removed

**Endpoints unchanged**: all others (`/turn`, `/character`, `/campaigns`, `/save`, `/scene`).

### 3. Narrator System Prompt

**Core change** (`agent.py`):

```python
# BEFORE
_NUMBERS_NEVER_IN_PROSE_RULE = """
CRITICAL RULE — NUMBERS NEVER IN PROSE:
...every number ... must come from an MCP tool result via effects[].
Your Scene's effects[] describe ENGINE OPERATIONS to perform, not their outcomes.
The engine executes them; you narrate.
"""
# + system prompt: "effects: engine operations to apply this turn"

# AFTER (inline in system prompt)
"""
CRITICAL RULE — NUMBERS NEVER IN PROSE:
You have MCP tools. Call them during generation. See real results.
Use those results in your narrative.
- Call roll_dice → see the result → narrate the result.
- Call update_character_sheet → see the new stamina → narrate the new stamina.
- Call start_combat → resolve rounds → call end_combat → narrate the outcome.
Return Scene(narrative, choices). The effects field does not exist.
"""
```

### 4. Migration Phases (from ADR-029)

The slice is delivered in 5 phases, each independently mergeable:

| Phase | Change | Risk | Gate |
|---|---|---|---|
| 1 | System prompt: direct tool use. effects[] still accepted but narrator won't emit them. | Low | Integration test: narrator calls tools during generation |
| 2 | Remove effects[] from Scene. Remove _apply_scene_effects from play.py. Update FakeNarrator. | Medium | All tests green |
| 3 | Remove scaffolding: EFFECT_TO_MCP_TOOL, EffectType, Effect, _scene_contains_fabricated_numbers, _RESULT_KEYS. Simplify output_validator. | Low | All tests green |
| 4 | Remove combat_subagent.py. Remove combat.py router + endpoints. | Low | Tests green; 404 on /combat/* |
| 5 | Update CONTRACTS.md §10, TurnResponse, frontend types, test_scene_effects_contract.py removed. | Low | Contract tests green; grep confirms no effects_applied refs |

---

## Agent Context

*CLAUDE.md updated to reference this plan under the `<!-- SPECKIT START -->` block.*
