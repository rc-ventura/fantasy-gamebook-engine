# ADR-001: Combat sub-agent delegation pattern

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [07-harness](../07-harness.md), [CONTRACTS §5/§6](../CONTRACTS.md)
**Code**: `.claude/skills/game-master/SKILL.md`, `.claude/skills/combat-sub-agent/SKILL.md`

---

## Context

The harness (module 07) must resolve Fighting-Fantasy-style combat without the narrator ever
inventing numbers. Combat is the most rule-dense, multi-round part of a session and, if run
inside the main narrator loop, bloats the Game Master's context and tangles fight bookkeeping
with storytelling. Phase 1 runs on Claude Code skills; Phase 2 swaps the harness for a
PydanticAI/FastAPI agent (swap boundary #3) while reusing the same MCP contract. We needed a
combat-handling design that keeps the narrator lean and survives that swap.

## Decision

Split combat into a dedicated **combat-sub-agent SKILL** that the **game-master SKILL**
delegates to. The Game Master never runs a fight itself. It hands off a **self-contained
payload**:

- the hero's current `skill`, `stamina`, `luck` (+ name), read from live MCP state;
- the enemy list as `Enemy{name, skill, stamina}` from the adventure bestiary;
- `flee_allowed`; and brief scene flavor.

The sub-agent runs the entire fight using **only the four combat MCP tools**
(`start_combat` → `resolve_combat_round` / `flee_combat` → `end_combat`), asks the player
"test luck?" each round, narrates each `RoundOutcome`, and returns a single
`FinalResult{winner, hero_final_stamina, luck_spent, rounds, drops}`. The Game Master then
narrates win/death/flee and applies `drops` via `update_character_sheet`.

## Alternatives considered

### Alternative A: Game Master runs combat inline (no sub-agent)

**Why not chosen**:
- Bloats the narrator's context with per-round bookkeeping.
- Mixes rules-loop logic with storytelling, making both harder to evolve.
- Weakens the Phase-2 boundary, where combat may be a structured service.

### Alternative B: Move combat orchestration into the MCP server (a "run_whole_fight" tool)

**Why not chosen**:
- The per-round "test luck?" decision is a *player* interaction, not engine logic; the MCP
  layer is intentionally interaction-free.
- CONTRACTS §6 fixes 17 tools at round granularity; a mega-tool would violate the contract.

## Consequences

### Accepted

- Narrator context stays small; fight logic is isolated and independently testable.
- The handoff is self-contained, so the sub-agent behaves identically whether run inline or
  spawned as a separate subagent — keeping harness swap boundary #3 clean.
- Clear ownership: master owns story/world/archiving and applies drops; sub-agent owns only
  fight resolution and never touches World/events/archive.

### Trade-offs

- A defined handoff payload must be kept in sync between the two SKILLs.
- Drops are surfaced by the sub-agent but applied by the master — a two-step that must not be
  dropped (mitigated by documenting it in both files).

### Conditions that invalidate this decision

1. Phase 2 adopts structured combat output where a single engine call returns a full fight.
2. The MCP combat tool granularity changes (CONTRACTS §6 revised).

## References

- CONTRACTS.md §5 (CombatEngine result types) and §6 (MCP tool contract).
