# ADR-006: Combat luck tally is ephemeral, not persisted in Combat state

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [04-combate](../04-combate.md), [CONTRACTS §2/§5](../CONTRACTS.md)
**Code**: `src/gamebook/combate/implementation.py`

---

## Context

`end_combat` returns a `FinalResult` that includes `luck_spent` (how many luck
tests the hero made during the fight) and `rounds`. The combat must survive a
process restart — the authoritative `Combat` record is persisted per `combat_id`
via `StorageBackend`.

But the `Combat` domain model (CONTRACTS §2) has a **fixed schema** — `combat_id`,
`enemies`, `round`, `flee_allowed`, `ended`, `winner`. It has *no* field for a
luck-spent counter, and the domain layer is the shared contract I must not drift.
`rounds` is already covered (`Combat.round` is persisted and incremented each
round), so only `luck_spent` lacks a home.

## Decision

Keep `luck_spent` as an **ephemeral per-combat counter in `CombatService` memory**
(`self._luck_spent: dict[str, int]`), incremented whenever a round actually tests
luck and read (then popped) in `end_combat`. The authoritative combat state —
enemy stamina, round number, ended/winner, and the hero sheet — is fully
persisted; only the luck *tally for the final summary line* is in memory.

Lookups are defensive (`.get(id, 0)` / `.pop(id, 0)`), so a service constructed
after a restart simply reports `luck_spent = 0` for a resumed fight rather than
crashing. Combat correctness (who wins, who dies, stamina) is never affected.

## Alternatives considered

### Alternative A: Add a `luck_spent` field to the `Combat` domain model

**Why not chosen**:
- `Combat`'s schema is part of the cross-module contract (designed to map ~1:1 to
  a Postgres table); changing it unilaterally is exactly the silent drift the
  contract forbids.
- Pollutes a persistent entity with a derived presentation counter.

### Alternative B: Reconstruct `luck_spent` from the character sheet's luck delta

**Why not chosen**:
- `end_combat` does not know the hero's pre-combat luck (not snapshotted), and luck
  could in principle change for non-combat reasons; the delta is not a reliable
  count.

## Consequences

### Accepted

- The `Combat` contract stays untouched; no domain drift.
- The authoritative, restart-critical state is persisted; the only thing lost on a
  mid-fight restart is the cosmetic luck tally in the final summary.

### Trade-offs

- `FinalResult.luck_spent` is **not** restart-durable. Acceptable: it is a summary
  statistic, not game state, and a fight rarely spans a restart.

### Conditions that invalidate this decision

Revisit if:

1. `luck_spent` (or a similar per-combat tally) becomes game-affecting state that
   must survive a restart.
2. The contract owner adds a sanctioned place to persist combat-scoped counters.

### Migration path when needed

If durability is later required, add a sanctioned counter to the persisted combat
record (contract change, coordinated with the Tech Lead) and have the service read
from there instead of the in-memory dict — a localized change in
`CombatService.resolve_round`/`end_combat`.

## References

- CONTRACTS.md §2 (Combat schema), §5 (combate lifecycle, FinalResult)
- 04-combate.md — "Combate em andamento sobrevive a reinício"
