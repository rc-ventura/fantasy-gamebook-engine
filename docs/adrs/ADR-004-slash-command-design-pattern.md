# ADR-004: Slash-command design pattern (system commands)

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [08-comandos](../08-comandos.md), [CONTRACTS §6/§8](../CONTRACTS.md)
**Code**: `.claude/commands/{stats,mochila,mapa,salvar}.md`

---

## Context

Module 08 defines player "system" actions outside the narrative — consult the sheet,
inventory, map, and save — the digital equivalent of a gamebook's Adventure Sheet. The
hard requirement: these must reflect **real MCP state, never a narrated value**, and must not
alter the story (the one exception being using an item, an explicit state change). We needed a
uniform, easily extensible pattern so adding `/diario`, etc., is trivial.

## Decision

Each command is a `.claude/commands/<name>.md` file following one uniform pipeline:

> **trigger → read (and sometimes write) MCP → print formatted → return to the current turn**

Concrete mappings (all tool names per CONTRACTS §6):
- `/stats` → `read_character_sheet` → print skill/stamina/luck (current/initial), gold,
  provisions, inventory, conditions. **Available even during combat.**
- `/mochila` → `read_character_sheet` → detail inventory; **using an item** writes via
  `update_character_sheet` (the one allowed state change), respecting the patch semantics and
  the heal-cap-at-`initial` invariant.
- `/mapa` → `read_world` → `current_location` + `visited_locations`.
- `/salvar` → `save_progress(slot?)` → confirm the checkpoint.

Every command states explicitly that it reads real state, prints only tool output, and does
not advance the story.

## Alternatives considered

### Alternative A: Let the narrator answer "what are my stats?" from memory/prose

**Why not chosen**:
- Directly violates the §8 acceptance criterion: `/stats` must reflect real MCP state, never a
  narrated value. Prose drifts from persisted state.

### Alternative B: One mega-command with subcommands

**Why not chosen**:
- Less discoverable; harder to map to Phase-2 UI components (each command becomes a panel/
  button). One file per command keeps the "add a command = add a file" property.

## Consequences

### Accepted

- Uniform, predictable commands; adding a new one is a single new file, no rules/narrative
  changes.
- Guarantees state-truth: read-outs come straight from MCP.
- Maps cleanly to Phase-2 UI (sheet panel, inventory modal, map) over the same data.

### Trade-offs

- `/mochila`'s item use is a state mutation living in a "command", so it must carefully honor
  invariants (heal cap, inventory replace-not-append) — documented in the file.

### Conditions that invalidate this decision

1. Phase 2 replaces text commands with UI components.
2. CONTRACTS §6 read/write tool names change.

## References

- CONTRACTS.md §6 (tool contract), §8 (harness & commands); 08-comandos.md acceptance
  criteria.
