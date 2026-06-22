# ADR-008: Two-layer plugability audit — static ast + fresh-subprocess runtime isolation

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [00-indice](../00-indice.md), [CONTRACTS §1 (layering + Audit rule)](../CONTRACTS.md)
**Code**: `tests/qa/_audit.py`, `tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`

---

## Context

QA owns the **golden rule** — every module depends only on *interfaces*, never on
concrete implementations — and must prove the three swap boundaries hold with
automated tests rather than convention. The challenge is that "depends only on
interfaces" has two distinct failure modes that no single check catches:

1. **Source-level intent.** A developer writes `from gamebook.storage.json_storage
   import JSONStorage` inside `combate`. This may not even execute (it could be a
   `TYPE_CHECKING`-guarded line) but it still encodes a forbidden coupling and
   will mislead the next reader.
2. **Runtime transitive load.** A module looks clean at the top but *drags in* a
   concrete impl through a chain of imports, so at run time the supposedly
   decoupled layer actually has the concrete backend resident in `sys.modules`.

`combate` makes this concrete: it references `storage.interfaces.StorageBackend`
**only** under `if TYPE_CHECKING:`, so at run time it imports *no* storage module
at all — a `TYPE_CHECKING` import is invisible to a runtime-only check but very
visible (and must be inspected) at the source level.

## Decision

Audit the golden rule with **two complementary layers**, not one:

- **Static (ast).** `test_dependencies.py` parses each `gamebook` source file with
  `ast` and walks every `Import` / `ImportFrom` node — *including* those under
  `if TYPE_CHECKING:` — resolving relative imports to absolute dotted names. It
  never executes the code. This enforces the per-layer allow/forbid rules at the
  level of *what the source says*, catching a concrete leak even when smuggled
  under a typing guard.
- **Runtime (fresh subprocess).** `test_isolation.py` imports each module in a
  clean interpreter (`subprocess` + `sys.executable`) and inspects which
  `gamebook.*` modules landed in `sys.modules`. This is the strongest proof a
  module does not transitively load a forbidden concrete impl, and it reflects
  *only* what the target pulls in (not whatever the test session already imported).

```python
# static: sees TYPE_CHECKING imports, never executes
imported = _audit.gamebook_imports(path)          # ast walk

# runtime: clean process, real sys.modules footprint
footprint = _audit.runtime_gamebook_modules("gamebook.combate.implementation")
```

Per the binding **Audit rule** in CONTRACTS §1, the runtime check asserts only the
*absence* of storage concretes / `mcp` for `combate` (it must NOT require
`storage.interfaces` to be present, since `TYPE_CHECKING` keeps it out of
`sys.modules`), while the ast check still catches any concrete leak.

## Alternatives considered

### Alternative A: importlib/runtime check only

**Why not chosen**:
- A `TYPE_CHECKING`-guarded concrete import is invisible at run time, so a
  forbidden coupling expressed only in typing imports would pass silently.
- It proves what *loaded*, not what the source *intends* — the source is what the
  next developer reads and copies.

### Alternative B: static ast check only

**Why not chosen**:
- It cannot prove the absence of a *transitive* runtime leak through a deep import
  chain; a module could be clean at the top yet drag in a concrete impl indirectly.

### Alternative C: in-process runtime check (import in the test process)

**Why not chosen**:
- The test session has already imported half the package, polluting `sys.modules`;
  a fresh subprocess is required to attribute the footprint to the target alone.

## Consequences

### Accepted

- A concrete-impl leak is caught whether it is expressed in source (ast) or only
  manifests at run time (subprocess), with clear, loud failure messages naming the
  offending module and import.
- The audit is fast (ast parse + one short subprocess per module) and has no
  third-party dependency.

### Trade-offs

- Two layers mean two places to update if the layering rules change.
- The subprocess layer assumes the test interpreter can import `gamebook` (true
  under the editable install / `uv run`).

### Conditions that invalidate this decision

This decision should be **revisited** if:

1. A dependency-linting tool (e.g. import-linter) is adopted that covers both
   source-level and runtime concerns adequately.
2. The package stops using `TYPE_CHECKING` to express interface seams, removing
   the gap that motivates the static layer.

### Migration path when needed

Replace `_audit.py`'s ast/subprocess helpers with the linter's contract config,
keep the same per-layer allow/forbid rules, and delete the bespoke tests.

## References

- CONTRACTS §1 — Module layering and the binding Audit rule.
- ADR-005 — Determinism via injected `RandomSource` Protocol (the interface seams
  this audit guards).
