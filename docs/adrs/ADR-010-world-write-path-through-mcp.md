# ADR-010: A World-write path through MCP (resolving the §6 / §2-§4 inconsistency)

**Status**: Accepted (ratified by Tech Lead, cycle 2 — 2026-06-21)
**Date**: 2026-06-21
**Related spec**: [02-dominio](../02-dominio.md), [03-storage](../03-storage.md), [05-mcp.md](../05-mcp.md), [07-harness](../07-harness.md), [CONTRACTS §2/§4/§6/§7](../CONTRACTS.md)
**Code**: `src/gamebook/mcp/server.py`, `src/gamebook/storage/json_storage.py` (`save_world` — already implemented), `.claude/skills/game-master/SKILL.md`, `.claude/skills/ignarok/SKILL.md`

---

## Context

The MCP façade (module 05) is the **only** surface through which the harness mutates
engine state — that is the enforcement mechanism for the project's hard rule, "the AI
never invents numbers or state in prose; everything goes through MCP." For three of the
four persistent entities this holds: `CharacterSheet` (`update_character_sheet`),
`Event` (`register_event`), and the narrative summary (`update_summary`) each have a
write tool. **`World` does not.**

This is an **internal inconsistency in the contract itself**, not a coding defect:

- **CONTRACTS §2** models `World` as a *mutable* entity (`current_location`,
  `visited_locations`, `known_npcs`, `flags`, `turn`).
- **CONTRACTS §4** mandates `StorageBackend.save_world(world)` — and `JSONStorage`
  *implements it correctly and it is unit-tested* (storage parity).
- **CONTRACTS §6** freezes "exactly these 17 tools," and **none of them calls
  `storage.save_world`.** `register_event` *reads* `world.turn` to stamp an event but
  never writes the World back.
- **ADR-002** (compaction) tells the master to promote hard facts to "World
  `flags`/`current_location`/`visited_locations`"; **ADR-003** makes the victory
  condition a single World flag (`malachar_defeated`); **ADR-004** has `/mapa` read
  `current_location` + `visited_locations`. The `game-master` and `ignarok` SKILLs
  instruct the GM to "set the World flag," "update `current_location`/
  `visited_locations`," and "**you** set that World flag" in ~8 places.

Net effect of the gap, end to end:

- `world.turn` is permanently `0` → every `register_event` stamps `turn=0`;
  `archive_character` records `turns=0`, `location=""`.
- `current_location` / `visited_locations` never persist → `/mapa` is always empty.
- `flags` never persist → the victory flag `malachar_defeated` **can never be set** →
  a full Ignarok playthrough cannot record progress or trigger victory.
- The harness is told to write World state it has **no tool to write**, forcing the GM
  to either narrate the flag (violating the foundational "state via MCP" rule) or dead-end.

`save_world` already exists at the storage layer; the missing piece is a façade tool to
reach it. This is a façade-completeness gap, **not** a layering violation — the golden
rule, the swap boundaries, and determinism are all intact.

## Decision

Add a single write tool to the façade — **`update_world(changes: dict) -> World`** —
that mirrors the proven `update_character_sheet` patch pattern and calls the
already-existing `storage.save_world`. This makes the 17-tool count **18** and requires
a deliberate amendment to **CONTRACTS §6** (the count and the tool table). §4 already
sanctions `save_world`; no storage change is needed.

Proposed semantics (to be ratified with §6):

- `changes` is a partial dict over the writable `World` fields
  (`current_location`, `visited_locations`, `known_npcs`, `flags`, `turn`).
- Scalars/lists (`current_location`, `visited_locations`, `known_npcs`) are
  shallow-replaced; `flags` is **merged** (so setting one flag does not drop others),
  consistent with the existing "merge sub-object, replace scalars" convention.
- An unknown-field guard + an `_UPDATABLE_WORLD_FIELDS` allowlist, exactly like
  `_UPDATABLE_FIELDS`, to preserve the mass-assignment protection Security validated.
- Invariants validated via `World.model_validate` (e.g. `turn >= 0`); on error nothing
  is persisted (state unchanged), matching `update_character_sheet`.
- **Turn advancement:** `update_world({"turn": n})` covers it explicitly. Whether the
  master advances the turn each narrative beat or the engine auto-increments is a
  harness-policy question deferred to implementation, but the *mechanism* must exist so
  events and archives carry a real turn count.

## Alternatives considered

### Alternative A: Fold World writes into `register_event` (event also mutates World)

**Why not chosen**:
- Conflates the **append-only chronicle** with **mutable** World state, breaking the
  clean SRP split the design relies on (`register_event`'s contract is "append a hard
  fact," nothing more). It would also make the victory flag a side effect of logging an
  event, which is surprising and hard to test.

### Alternative B: Several narrow tools (`advance_turn`, `set_flag`, `move_location`)

**Why not chosen**:
- Inflates the tool count by 3+ and fragments the World write surface; `update_world`
  with patch semantics covers all of them with one tool that maps 1:1 to the Phase-2
  structured-state update. Symmetric with `update_character_sheet`.

### Alternative C: Document the gap as deferred to Phase 2

**Why not chosen**:
- It blocks a **complete Phase-1 Ignarok playthrough right now** (no victory, no map, no
  turn count) and leaves the harness instructing an impossible action — a live violation
  of the foundational "state via MCP" rule, not a cosmetic omission.

## Consequences

### Accepted

- Restores the design's core promise: **all** persistent state — including World — is
  reachable only through MCP. ADR-002/003/004's intent becomes achievable.
- Reuses the already-tested `save_world` and the proven `update_character_sheet` patch
  shape; the change is additive and localized to `mcp/server.py` + the contract.
- Unblocks victory, `/mapa`, real turn stamping on events, and accurate `archive_character`.

### Trade-offs

- The "exactly 17 tools" freeze becomes "exactly 18"; CONTRACTS §6 must be amended
  deliberately (owned by the Tech Lead), and the harness SKILLs updated to name
  `update_world` where they currently say "set the World flag."
- A second patch-dict write surface to keep allowlisted (mitigated by copying the
  `_UPDATABLE_FIELDS` pattern verbatim).

### Conditions that invalidate this decision

1. CONTRACTS §2 is changed to make `World` immutable in Phase 1 (then ADR-002/003/004
   must change too — unlikely, since victory depends on a World flag).
2. Phase 2's structured `Cena` output absorbs World mutation through a different channel.

## References

- CONTRACTS §2 (`World` schema), §4 (`save_world`), §6 (tool contract — to amend
  17→18), §7 (victory flag in World).
- ADR-002 (compaction → World flags), ADR-003 (victory = World flag), ADR-004
  (`/mapa` reads World).
- Mirrors the `update_character_sheet` patch design and its mass-assignment allowlist.
