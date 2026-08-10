# World.flags was typed dict[str, bool] — widening it for a counter needs a domain-model + CONTRACTS.md change, not a workaround

**Date**: 2026-08-09
**Spec**: [009-deterministic-turn-dispatcher](../../specs/009-deterministic-turn-dispatcher/)
**Code**: `src/gamebook/domain/models.py::World.flags`, `docs/CONTRACTS.md` §2

## What happened

Fixing issue #28 (narrator can loop a player in a zone forever) needed a per-zone
turn-dwell counter, persisted the same way T033/T034's encounter-roll memory already is:
write it to `World.flags` via the `update_world` MCP tool, read it back next turn. The
natural design — `flags["_zone_turn_count"] = <int>` and
`flags["_zone_turn_location"] = <zone id string>` — failed at the engine boundary:

```
pydantic_ai.exceptions.ModelRetry: Error executing tool update_world: 1 validation error
for World flags._zone_turn_location
  Input should be a valid boolean, unable to interpret input [type=bool_parsing, ...]
```

`World.flags: dict[str, bool]` (`src/gamebook/domain/models.py`) had only ever needed to
hold booleans up to this point (encounter presence, victory conditions) — nothing enforced
that invariant except that every prior caller happened to only ever write bools.

## The resolution

Considered and rejected a one-hot boolean encoding (a `_zone_turn.<n>` flag per count
level, one flag per possible zone as a "last visited" marker) — workable but needlessly
convoluted for what is a legitimate, permanent data-shape need, not a one-off hack.
Instead widened the actual contract: `flags: dict[str, bool | int | str]` in both the
domain model and `docs/CONTRACTS.md` §2 (the project's binding English contract — CLAUDE.md:
"CONTRACTS.md governs — if you must deviate, update it deliberately"). Backward compatible:
every existing bool-only caller is still valid, JSON/Postgres JSONB storage needed no
changes (JSON already represents int/str/bool natively — only the Pydantic validation
layer was bool-only).

## Rule

When a fix needs to persist a new *kind* of value into an existing engine-side field, check
the domain model's actual declared type before designing around it — don't assume "it's
just a flags dict, it'll take anything." If the constraint is real and the new data shape is
a legitimate, recurring need (not a one-off), the correct fix is usually to widen the typed
contract deliberately (domain model + `CONTRACTS.md` together) rather than encode around it
with a more complex workaround at the call site. Grep the field's other consumers for
`isinstance(v, bool)`-style assumptions before widening — none existed here (every consumer
already just read/copied values), which is what made it safe.
