# ADR-019: Allowlist for fabricated-number detection

**Status**: Accepted | **Date**: 2026-06-28 | **Branch**: `feat/006-cycle1-remediation`

## Context

The SDD final review (cycle-1) flagged a **LOW-severity** defense-in-depth gap in the
"numbers never in prose" gate (Principle I). `PydanticNarrator.output_validator`
(`agent.py:63-91`) uses a **denylist** `_RESULT_KEYS` to detect narrator-fabricated
result values sneaking into `Scene.effects[].params`:

```python
_RESULT_KEYS = frozenset({
    "result", "total", "roll", "rolls", "current", "new_value",
    "damage", "stamina_after", "luck_after", "hero_stamina",
    "hero_as", "enemy_as",
})
```

A narrator could fabricate a number under an unrecognized key name (e.g. `hp`,
`value`, `amount`, `stamina_value`) and the validator would not catch it. The regex
for prose (`agent.py:84`) only catches `stamina|skill|luck|gold` followed by
`is|was|becomes|dropped to` — it misses "you lost 5 points", "took 3 damage", and any
number in a choice label.

This is a defense-in-depth gap, not a current violation (the narrator is trusted to
follow the system prompt). But Principle I is NON-NEGOTIABLE, so the gate should be
as robust as feasible.

Options considered:

1. **Keep the denylist, expand it** (status quo + more keys): whack-a-mole; every new
   result-key synonym is a new bypass. Does not fix the structural weakness.
2. **Allowlist of effect param keys** (chosen): instead of banning known result keys,
   define the **exhaustive set of legal param keys per effect type**. Any param key
   not in the allowlist for that effect type is rejected. This is structural — a
   narrator cannot sneak a number under any key the engine does not expect.
3. **Typed Effect params (Pydantic models per effect type)**: replace
   `params: dict[str, Any]` with a discriminated union of typed models
   (`UpdateCharacterParams`, `StartCombatParams`, etc.). Strongest typing, but a
   larger refactor of `scene.py` and every effect-handling call site.

## Decision

**Option 2: an allowlist of legal param keys per effect type.** The validator is
inverted: instead of scanning for banned result keys, it checks that every key in
`effect.params` is in the allowlist for `effect.type`. Any unknown key → `ModelRetry`.

### Design

A module-level mapping in `agent.py` (or `scene.py`, co-located with the
`EFFECT_TO_MCP_TOOL` mapping):

```python
_ALLOWED_EFFECT_PARAMS: dict[EffectType, frozenset[str]] = {
    EffectType.UPDATE_CHARACTER: frozenset({"skill", "stamina", "luck", "name",
        "inventory", "gold", "provisions", "conditions", "alive"}),
    EffectType.UPDATE_WORLD: frozenset({"current_location", "visited_locations",
        "known_npcs", "flags", "turn"}),
    EffectType.REGISTER_EVENT: frozenset({"type", "data"}),
    EffectType.START_COMBAT: frozenset({"enemies", "flee_allowed"}),
    EffectType.RESOLVE_COMBAT_ROUND: frozenset({"combat_id", "use_luck"}),
    EffectType.FLEE_COMBAT: frozenset({"combat_id"}),
    EffectType.END_COMBAT: frozenset({"combat_id"}),
    EffectType.TEST_LUCK: frozenset(),
    EffectType.ROLL_DICE: frozenset({"notation"}),
    EffectType.ARCHIVE_CHARACTER: frozenset({"destination"}),
    EffectType.SAVE_PROGRESS: frozenset({"slot"}),
    EffectType.LOAD_PROGRESS: frozenset({"slot"}),
}
```

The validator:
1. For each effect, reject if `set(effect.params) - _ALLOWED_EFFECT_PARAMS[effect.type]`
   is non-empty (unknown key).
2. Reject any `int`/`float` value under a key whose name *looks* like a result
   (defensive regex on key names: `result|total|roll|damage|_after|_as$`) — a
   belt-and-suspenders check that catches a misnamed allowlist entry.
3. Keep the prose regex (`agent.py:84`) but extend it to also catch "lost N points",
   "took N damage", "N hp" patterns.

The allowlist is derived from the MCP tool signatures in `server.py` and
`EFFECT_TO_MCP_TOOL` — it is the single source of truth for "what params does this
effect type legally carry". When a tool signature changes, the allowlist changes in
the same commit (Principle III).

### Why not option 3 (typed params)

- It is the right long-term shape, but it is a larger refactor (discriminated union,
  every `_build_tool_args` call site, every test fixture). The remediation spec
  scopes it out; option 2 captures 90% of the safety with ~30 lines.
- Option 2 is a pure validator change — no `scene.py` schema change, no call-site
  change. It can ship in the remediation slice without destabilizing the Scene
  contract that slice 005 depends on.

## Consequences

**Positive**:
- Structural protection: a narrator cannot fabricate a number under any key the
  engine does not expect. Principle I gate is robust, not heuristic.
- The allowlist documents the legal param surface per effect type — a secondary
  contract artifact.
- Small, localized change (~30 lines + tests).

**Negative**:
- The allowlist must be kept in sync with `EFFECT_TO_MCP_TOOL` and the MCP tool
  signatures. A new effect type or param requires an allowlist update, or the
  validator rejects a legal scene (fail-closed — safe but noisy).
- `params: dict[str, Any]` remains untyped; a narrator can still send a wrong *type*
  (e.g. `enemy_skill: "12"` string instead of int). The MCP tool layer's typed
  Python params catch this at call time (FastMCP coerces/rejects), but the validator
  does not. Option 3 would fix this; deferred.
- The extended prose regex may false-positive on legitimate narrative that mentions
  numbers (e.g. "you see 3 goblins"). The regex must be scoped to stat-assertion
  patterns, not any number in prose.

## When to retire

Superseded when option 3 (typed discriminated-union Effect params) lands — likely in
a future hardening slice. At that point the allowlist becomes redundant because the
Pydantic models enforce the shape. This ADR records the interim decision.

## Related

- Remediation spec: `specs/006-cycle1-remediation/spec.md`
- SDD review: `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
  (LOW finding on `_RESULT_KEYS`)
- Constitution Principle I (Numbers Never in Prose — NON-NEGOTIABLE)
- `src/gamebook_web/harness/agent.py:63-91` (current denylist)
- `src/gamebook_web/harness/scene.py` (`EFFECT_TO_MCP_TOOL` mapping)
- `src/gamebook/mcp/server.py` (tool signatures — source of truth for the allowlist)
