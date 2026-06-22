# ADR-005: Determinism via an injected RandomSource Protocol

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [01-regras](../01-regras.md), [CONTRACTS §1/§3/§5](../CONTRACTS.md)
**Code**: `src/gamebook/regras/interfaces.py`, `src/gamebook/regras/implementation.py`, `src/gamebook/combate/implementation.py`

---

## Context

`regras` is the pure, deterministic core of the engine and must travel intact to
Phase 2. The rules functions need randomness (dice) but must be:

- **100% testable in isolation** — no disk, no AI, reproducible under a fixed seed;
- **decoupled** from any concrete RNG, so production could later swap in a
  cryptographic source without touching the rules.

The same question recurs at every module seam: `regras` exposes a randomness
contract, `storage` exposes `StorageBackend`, `combate` exposes `CombatEngine`.
We had to pick how to express these seams (the "depend only on interfaces" golden
rule) and how randomness reaches the pure functions.

## Decision

Express randomness as a **structural `Protocol`** (`RandomSource`) with a single
`randint(a, b) -> int` method, and **inject it as a parameter** into every rules
function and into `CombatService.__init__`. `random.Random` satisfies it out of
the box; tests pass `random.Random(seed)` or a tiny hand-rolled stub.

```python
@runtime_checkable
class RandomSource(Protocol):
    def randint(self, a: int, b: int) -> int: ...

def roll_dice(notation: str, rng: RandomSource) -> DiceResult: ...
```

Use **PEP 544 `Protocol` (structural typing), not `ABC`**, for all three engine
seams (`RandomSource`, `StorageBackend`, `CombatEngine`). No module inherits from
a base class; conformance is by shape. This keeps concrete impls free of import
coupling to the interface module (e.g. `random.Random` is already a valid
`RandomSource` with zero changes, and `InMemoryStorage`/`JSONStorage` need not
subclass anything).

## Alternatives considered

### Alternative A: Module-global RNG (e.g. call `random.randint` directly)

**Why not chosen**:
- Breaks purity and determinism — tests would depend on global seed state.
- Makes parallel/independent tests flaky and order-dependent.

### Alternative B: `abc.ABC` base classes for the seams

**Why not chosen**:
- Forces concrete impls to import and subclass the interface module, reintroducing
  the coupling the golden rule exists to avoid.
- `random.Random` could not satisfy an ABC without an adapter; a Protocol it
  satisfies for free.

**Advantages** (not leveraged): ABCs can enforce implementation at instantiation
time; Protocols only enforce at type-check time (and optionally `isinstance` when
`@runtime_checkable`).

## Consequences

### Accepted

- `regras` is pure and seeded-reproducible; the whole engine is unit-testable
  with no disk and no AI.
- Concrete impls have zero runtime dependency on interface modules.
- `combate` can reference `StorageBackend` under `TYPE_CHECKING` only and still be
  fully typed — no runtime storage coupling at all.

### Trade-offs

- Protocol conformance is checked by the type checker, not at runtime, so a
  malformed impl is caught by CI/mypy rather than at import. (`@runtime_checkable`
  gives a partial `isinstance` safety net.)

### Conditions that invalidate this decision

This should be revisited if:

1. A future RNG needs richer state (streams, reseeding mid-game) that a single
   `randint` cannot express.
2. We need runtime enforcement of interface conformance strong enough to justify
   ABCs.

### Migration path when needed

`RandomSource` can grow methods (e.g. `random()`, `choice()`) additively without
breaking `random.Random` compatibility; only widen the Protocol when a rule needs it.

## References

- CONTRACTS.md §1 (module layering), §3 (regras), §5 (combate)
- PEP 544 — Protocols: structural subtyping
