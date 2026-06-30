# Research: Narrator Tool-Use Refactor

**Feature**: 007-narrator-tool-use-refactor
**Date**: 2026-06-30
**Phase**: 0 (Pre-planning unknowns resolution)

---

## PC-001: `update_character_sheet` mutation semantics

**Question**: Is `update_character_sheet` set-based (absolute values) or delta-based (increments)?
This determines whether a `ModelRetry` during narrator generation can double-apply a mutation.

**Finding**: **SET-BASED. Idempotent.**

**Evidence** (`src/gamebook/mcp/server.py:158-165`):
```python
for field, value in changes.items():
    if field in _ATTRIBUTE_FIELDS:                 # skill, stamina, luck
        data[field] = {**data[field], **value}     # merge: value is {"current": 8}
    else:
        data[field] = value                        # scalar replace
```

Attribute fields (stamina, skill, luck) take a partial dict like `{"current": 8}` — an
**absolute value**. Two calls with `{"stamina": {"current": 8}}` both result in stamina.current
= 8. No accumulation. Domain invariant (`0 <= current <= initial`) is validated by
`CharacterSheet.model_validate()` after the merge — if violated, state is left unchanged.

**Consequence for ADR-029**: The atomicity concern about retry double-applying deltas does NOT
apply. The narrator can call `update_character_sheet({"stamina": {"current": N}})` with an
absolute target value, and retries are safe.

**Decision**: Proceed with migration as planned. No workaround needed.

---

## PydanticAI: tool-use during `output_type=Scene` generation

**Question**: Does PydanticAI's `output_type` constraint prevent tool calls during generation?

**Finding**: No. `output_type` constrains only the **final structured return value**. Tool calls
happen in the agent's intermediate steps during `agent.run()`. The model can call tools,
see results, and then produce a structured `output_type` output that incorporates those results.

**Evidence**: Current code already passes `toolsets=[toolset]` to `agent.run()` in `agent.py:154-158`.
The toolset IS used during generation — the system prompt just tells the model to emit `effects[]`
instead of calling tools. Changing the system prompt is the entire fix.

**Decision**: No PydanticAI API changes needed. The infrastructure (`toolsets=[toolset]`) is
already in place. Only the system prompt instruction changes.

---

## Combat tool safety under narrator retry

**Question**: If the narrator calls `start_combat` during generation but produces an invalid Scene
(triggering `ModelRetry`), is the engine state corrupted?

**Finding**: Partial risk, mitigated by skill instructions.

- `start_combat` creates a `Combat` record in storage with a `combat_id`.
- If the narrator retries, it may call `start_combat` again → second `Combat` record (new `combat_id`).
- Phase 1 terminal avoided this by never retrying mid-combat (stdout/stdin loop had no ModelRetry).
- Web narrator with `output_validator` can trigger retry.

**Mitigation strategy** (system prompt enforcement):
1. Narrator must call `read_character_sheet` at the start of each turn — this reveals if there's
   an active combat (`sheet.alive` etc.; world state includes combat flags).
2. On retry, the narrator sees updated state (including any partial combat) and can continue
   the active combat rather than starting a new one.
3. System prompt must instruct: "If you see an active combat in the world state, continue it
   (call `resolve_combat_round`) — never start a new combat while one is active."
4. `output_validator` should NOT reject a scene just for mentioning combat — it should only
   reject structurally invalid scenes (empty narrative, missing choices on non-terminal scenes).

**Alternative** (simpler, lower risk): The narrator can resolve combat in a dedicated
"combat turn" flow: if the player's choice triggers combat, the turn response says "combat
begins" with the enemy info and the narrator returns immediately. The next turn resolves the
fight. This splits combat into two turns and avoids mid-generation retry risk entirely.

**Decision**: Use single-turn resolution as the primary approach (ADR-029). Include the
"active combat detection" instruction in the system prompt. Evaluate the two-turn alternative
if integration tests reveal retry issues.

---

## SkillsCapability (community package) — deferred

**Question**: Should `SkillsCapability` from `pydantic-ai-skills` be included in this slice?

**Finding**: Out of scope. The system prompt already injects `game-master/SKILL.md` content
directly (`_load_adventure_lore()` in `agent.py:48-52`). `SkillsCapability` provides a
standardized loader that would make the SKILL.md the single source of truth across Phase 1 and
Phase 2. However:
- It's a community package (not PydanticAI core) with unclear stability
- The core fix (system prompt change + direct tool use) works without it
- Adding a community dependency in this slice increases risk with no functional benefit

**Decision**: Deferred to a future optional enhancement. Not part of this slice.

---

## Summary of Decisions

| Unknown | Decision | Rationale |
|---|---|---|
| PC-001: mutation semantics | SET-BASED, proceed | Confirmed idempotent, no workaround needed |
| PydanticAI tool-use compatibility | Already works | `toolsets` already passed; only prompt changes |
| Combat retry safety | Mitigate via prompt | Active combat detection instruction in system prompt |
| SkillsCapability | Deferred | Community dep risk, not needed for core fix |
