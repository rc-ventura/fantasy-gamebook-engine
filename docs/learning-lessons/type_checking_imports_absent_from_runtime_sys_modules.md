# A `TYPE_CHECKING` import is absent from runtime `sys.modules` — isolation checks must assert *absence*, not *presence*

**Context:** Discovered while writing the QA plugability audit
(`tests/qa/test_isolation.py`) that proves `combate` depends on storage only via
its interface (swap boundary #1). `combate/implementation.py` references
`StorageBackend` under `if TYPE_CHECKING:`.
**Date:** 2026-06-21
**Future intent:** Apply whenever asserting a module's runtime decoupling by
inspecting `sys.modules`.

---

## Mental Model: `TYPE_CHECKING` imports never run, so they never load

`from __future__ import annotations` turns annotations into strings, and
`if TYPE_CHECKING:` is `False` at run time. So an interface imported *only* for
typing is **never executed** and therefore **never appears in `sys.modules`**:

```python
# combate/implementation.py
if TYPE_CHECKING:
    from gamebook.storage.interfaces import StorageBackend   # typing only

def __init__(self, storage: "StorageBackend", rng: "RandomSource") -> None: ...
```

This is even *better* than importing the interface: at run time `combate` pulls in
**no storage module at all** — not the concrete impls and not even the interface.

| View | Sees the `TYPE_CHECKING` import? |
|------|----------------------------------|
| `ast` parse of the source | ✅ yes (the node is in the tree) |
| `import combate; sys.modules` | ❌ no (the guard was `False`) |

Verified footprint of a fresh `import gamebook.combate.implementation`:

```
gamebook, gamebook.combate, gamebook.combate.implementation,
gamebook.combate.interfaces, gamebook.dominio, gamebook.dominio.models,
gamebook.regras, gamebook.regras.implementation, gamebook.regras.interfaces
# note: NO gamebook.storage.* at all
```

---

## The trap and the fix

**Naïve (wrong) isolation assertion:** "`combate` should import the storage
*interface* but not the concretes" →

```python
assert "gamebook.storage.interfaces" in footprint   # ❌ FAILS — it's TYPE_CHECKING
```

This fails on a perfectly clean module and would push someone to "fix" it by
adding a real runtime import of the interface — *weakening* the decoupling.

**Correct assertion:** check only the **absence** of the forbidden modules:

```python
for concrete in ("gamebook.storage.json_storage", "gamebook.storage.in_memory"):
    assert concrete not in footprint
assert not any(m.startswith("gamebook.mcp") for m in footprint)
# stronger corollary the guard buys us: no storage module loads at all
assert not any(m.startswith("gamebook.storage") for m in footprint)
```

The **static ast audit** (`test_dependencies.py`) is the layer that *does* see the
typing import and confirms it targets `storage.interfaces` (never a concrete) — so
the two layers split the work: ast checks intent, runtime checks the footprint.

---

## Relation to ADRs and next steps

- This is the binding caveat in **CONTRACTS §1 (Audit rule)** and the reason
  **ADR-008** uses two audit layers instead of one runtime check.
- Next step: any new module that exposes an interface seam via `TYPE_CHECKING`
  must be isolation-tested by *absence of concretes*, never *presence of the
  interface*.
