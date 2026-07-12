# Probabilistic encounter rolls must use the engine's seeded RNG, not Python's random module

**Date**: 2026-07-11  
**Spec**: [009-deterministic-turn-dispatcher](../../specs/009-deterministic-turn-dispatcher/)  
**Code**: `src/gamebook_web/harness/graph.py::_resolve_zone_encounters`

## What happened

When implementing zone-entry probabilistic encounter rolling (T033), the first impulse was
to use Python's `random.random()` directly. The engine already has a seeded `random.Random`
injected at `build_server()` time (ADR-005), but the web harness only talks to the MCP server
through `call_engine()` and has no direct access to that RNG.

Using `random.random()` would have made encounter rolls non-deterministic in tests: two
runs of the same test with the same `InMemoryStorage` state would produce different
encounter-presence decisions, causing flaky failures.

## The resolution

Use `call_engine(toolset, "roll_dice", campaign_id=..., notation="1d100")` and compare
`result["total"] <= int(probability * 100)`. The engine's seeded `random.Random` is the
one source of randomness in this system; routing the probability roll through it keeps
all dice — encounter rolls, combat rounds, luck tests — under the same seed.

```python
roll_result = await call_engine(toolset, "roll_dice", campaign_id=campaign_id, notation="1d100")
roll_value = roll_result.get("total", 100) if isinstance(roll_result, dict) else 100
present = roll_value <= int(enc.probability * 100)
```

Tests using `_fresh_in_memory_server()` with `random.Random(SEED)` are now fully
deterministic: the same seed always produces the same encounter-presence sequence.

## Rule

Any randomness in the harness layer that affects game state MUST go through a `roll_dice`
MCP call — never through `random.random()` or `os.urandom()` directly. The engine's
seeded RNG is the single source of truth for all in-game randomness.

**Exception**: non-game-state randomness (e.g. generating a UUID for a request ID,
shuffling a display list) may use Python's random freely since it does not affect
reproducible outcomes.
