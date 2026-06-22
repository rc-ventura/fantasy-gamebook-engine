# ADR-002: Context-compaction strategy for the narrator

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [07-harness](../07-harness.md), [CONTRACTS §6](../CONTRACTS.md)
**Code**: `.claude/skills/game-master/SKILL.md`

---

## Context

A play session is long-running and the narrator's context window is finite. If the story
lives only in conversation prose, it is lost when the context is compacted or a new session
starts. The harness spec (07) requires that, periodically, the master compacts a summary and
that "hard facts migrate to world/events (structured), not just prose." We needed a concrete,
durable strategy the Game Master follows.

## Decision

Two complementary mechanisms, both routed through MCP:

1. **Periodic narrative compaction.** Roughly **every ~6 turns, or whenever the player
   changes zones**, the master writes a tight running recap via `update_summary(text)`: who
   the hero is, where they are, key choices, current goals, unresolved threads. This is
   written as *guidance*, not a hard-coded counter, so the master uses judgement.
2. **Promote hard facts to structured state as they happen.** Durable facts (NPC freed, key
   taken, location cleared, clue learned, zone entered) are recorded with
   `register_event(type, data)` and/or World `flags`/`current_location`/`visited_locations`
   — independently of, and before, any compaction.

On session open, the master rehydrates from `read_summary` + `read_world` + `read_events`
(see ADR session-opening rule) so nothing durable is lost across compaction or restart.

## Alternatives considered

### Alternative A: Rely on conversation history alone

**Why not chosen**:
- Lost on compaction/new session; violates the "resume from the exact point" requirement.

### Alternative B: Fixed hard-coded compaction interval (e.g. exactly every 5 turns)

**Why not chosen**:
- Brittle: a quiet stretch and a dense combat stretch need different cadences. Guidance +
  zone-change trigger adapts better.

## Consequences

### Accepted

- The story survives compaction and restarts; sessions resume faithfully.
- Structured facts (events/flags) are queryable and feed the victory check and `/mapa`.
- Summary stays lean, controlling token cost.

### Trade-offs

- Relies on the master's discipline to promote facts and compact on time; a missed promotion
  could lose a detail. Mitigated by a per-turn checklist in the SKILL.

### Conditions that invalidate this decision

1. Phase 2's structured `Cena` output captures state changes explicitly, changing how facts
   are promoted.
2. The MCP summary/event tools change shape (CONTRACTS §6 revised).

## References

- CONTRACTS.md §6 (`update_summary`, `register_event`, `read_summary`, `read_events`,
  `read_world`).
