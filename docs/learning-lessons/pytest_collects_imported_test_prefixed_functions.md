# pytest collects any `test_`-prefixed callable imported into a test module

**Context:** Discovered while writing `tests/engine/test_regras.py` for the gamebook
engine. The rules API exposes a public function `test_luck(current_luck, rng)`
(named after the Fighting Fantasy "test your luck" action). Importing it into the
test module made the suite error out before any assertion ran.
**Date:** 2026-06-21
**Future intent:** Watch for this whenever a production identifier legitimately
starts with `test_`.

---

## Mental Model: pytest collection looks at the test module's *namespace*

pytest's default collection rule (`python_functions = test_*`) matches **any
callable bound to a `test_*` name in a collected module** — not just functions
*defined* there. An `import` binds the name into the module namespace, so:

```python
from gamebook.regras.implementation import test_luck   # binds name "test_luck"
```

makes pytest treat `test_luck` as a test. It then inspects the signature, sees a
parameter `current_luck`, and tries to resolve it as a **fixture**:

```
ERROR at setup of test_luck
fixture 'current_luck' not found
```

| Symbol | Where defined | Collected by pytest? | Why |
|--------|---------------|----------------------|-----|
| `def test_x(): ...` in a test file | test module | ✅ | name matches `test_*` |
| `from app import test_luck` | imported into test module | ✅ (the trap) | name in module namespace matches `test_*` |
| `from app import test_luck as run_luck` | imported, aliased | ❌ | bound name no longer matches `test_*` |
| `import app; app.test_luck` | attribute access | ❌ | name `app` does not match |

---

## Fix used in this repo

Alias the import so the bound name does not start with `test_`:

```python
# Aliased on import: a name starting with ``test_`` would otherwise be collected
# by pytest as a test function (and fail looking for a ``current_luck`` fixture).
from gamebook.regras.implementation import test_luck as run_luck_test
```

Other viable fixes (not used here):
- Import the module and call via attribute: `from gamebook.regras import implementation as rules; rules.test_luck(...)`.
- Mark the symbol non-collectable: `test_luck.__test__ = False` (pytest honours
  `__test__ = False`). Intrusive on production code — avoid.

---

## Relation to ADRs and next steps

- The public name `test_luck` is fixed by **CONTRACTS §3** (it mirrors the PT
  `testar_sorte` rule), so renaming the production function is not an option — the
  test side must adapt.
- Next step: keep the alias convention for any future `test_*` production symbol;
  prefer module-qualified calls in tests when several such names appear.
