# Contract — `Scene` (narrator structured output)

Feature: Web Platform Migration · Date: 2026-06-26 · Last updated: 2026-06-30 (spec 007, ADR-029)
Status: **authoritative** (folded into `docs/CONTRACTS.md` §10).

> **Spec 007 (ADR-029) breaking change:** `effects[]` field eliminated. The narrator calls MCP
> tools directly during `agent.run()` and narrates only the real results it sees. `Scene` carries
> prose and choices only — no deferred engine operations.

`Scene` is the validated unit produced by the PydanticAI narrator for one turn (ADR-011,
swap boundary #3). The defining safety property: the narrator calls MCP tools and sees real
results; every number in `narrative` comes from an actual tool call (Principle I).
Invalid `Scene` objects are rejected with `422 invalid_scene` and never persisted.

## Shape

```python
class Scene(BaseModel):
    narrative: str              # 2–4 paragraphs, 2nd person, adventure-module tone
    choices:   list[Choice]     # numbered options offered to the player (empty = terminal)
    terminal:  bool = False     # True = death/victory; empty choices expected on terminal scenes

class Choice(BaseModel):
    id:    str    # stable id ("1", "2", …)
    label: str    # what the player sees
```

## Validation rules (Pydantic v2)
- `narrative` non-empty (field validator + `output_validator` raises `ModelRetry` if empty).
- `terminal=False` and `choices=[]` → `ModelRetry` (non-terminal scene must have choices).
- `terminal=True` → `choices` expected to be empty (death/victory end-states).
- No `effects` field — removed by spec 007 (ADR-029).

## Lifecycle (ADR-029)
1. Player submits choice/free text → `POST /campaigns/{id}/turn`.
2. Narrator calls MCP tools during `agent.run()` — reads state, resolves dice/combat/luck, updates state.
3. Narrator emits `Scene` with real numbers already in `narrative`.
4. API validates `Scene` (structural) → re-reads engine state (post-turn) → checks terminal state → stores scene.
5. Returns `TurnResponse` with scene + authoritative character + world from engine.

## Terminal scenes
- Death → `terminal=True`, `choices=[]`, campaign → `ended`, `ArchiveRecord` written.
- Victory (module flag, e.g. `malachar_defeated`) → `terminal=True`, epilogue narrative; campaign → `ended`.
- A turn on an already-`ended` campaign → `409 run_ended` (no new `Scene`).

## Authoritative source
`docs/CONTRACTS.md` §10 (updated 2026-06-30). `src/gamebook_web/harness/scene.py`.
