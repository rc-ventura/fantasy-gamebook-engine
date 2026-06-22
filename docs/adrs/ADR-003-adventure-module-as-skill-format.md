# ADR-003: Adventure module encoded as a SKILL.md (swap boundary #2)

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [06-modulo-aventura](../06-modulo-aventura.md), [CONTRACTS §7](../CONTRACTS.md)
**Code**: `.claude/skills/ignarok/SKILL.md`

---

## Context

The adventure (lore: zones, bestiary, victory condition, special rules) is swap boundary #2:
changing adventures must not touch the engine or the harness. CONTRACTS §7 defines an
`AdventureModule` shape (`metadata`, `opening`, `zones[]`, `bestiary[]`, `victory_condition`,
`special_rules[]`). In Phase 1 this lore is consumed by a Claude Code narrator; in Phase 2 it
becomes a data record. We needed a Phase-1 encoding that (a) the Game Master can read and
improvise from, (b) maps 1:1 to the contract, and (c) is trivially swappable.

## Decision

Encode each adventure as a single **`.claude/skills/<adventure>/SKILL.md`** whose sections
mirror the `AdventureModule` contract exactly: `metadata`, `opening`, `zones`, `bestiary`,
`victory_condition`, `special_rules`. The debut module is **`ignarok`**.

Key constraints baked into the format:
- The **bestiary** is a table whose `name`/`skill`/`stamina` columns plug **directly** into
  `start_combat` as `Enemy{name, skill, stamina}`; `behavior`/`drops` are narration-only.
- The **victory condition** is a single verifiable World flag (`malachar_defeated`), not a
  prose judgement.
- **Special rules** are written as directives that resolve through MCP tools (traps →
  `test_luck`, bribes/healing → `update_character_sheet`), never as numbers-in-prose.
- The file declares it carries **no rules and no engine knowledge** — pure static lore.

## Alternatives considered

### Alternative A: Embed the adventure inside the game-master SKILL

**Why not chosen**:
- Couples narrator behavior to one adventure; breaks swap boundary #2 (can't swap lore
  without editing the master).

### Alternative B: Ship the adventure as JSON/YAML data in Phase 1

**Why not chosen**:
- Phase 1's consumer is a prose narrator; Markdown is the natural input and lets the lore
  carry improvisation guidance. JSON is the Phase-2 form; the section-per-contract-field
  layout makes that later translation mechanical.

## Consequences

### Accepted

- New adventure = new SKILL file with the same sections; engine and harness untouched.
- 1:1 mapping to CONTRACTS §7 makes the Phase-2 data-record migration mechanical.
- Bestiary rows are directly usable by `start_combat` with no transformation.

### Trade-offs

- Markdown isn't schema-validated, so a malformed module isn't caught automatically (relies
  on the section-per-field convention + QA).

### Conditions that invalidate this decision

1. Phase 2 moves adventures to a validated data record / DB row.
2. CONTRACTS §7 changes the `AdventureModule` shape.

## References

- CONTRACTS.md §7 (`AdventureModule` contract); original content (no copyrighted material).
