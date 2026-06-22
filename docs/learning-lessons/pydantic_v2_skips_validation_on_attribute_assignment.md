# pydantic v2 skips validation on attribute assignment by default

**Context:** Discovered while implementing `combate/implementation.py` for the
gamebook engine, where each round subtracts damage from `CharacterSheet.stamina`
and `Attribute` carries the invariant `0 <= current <= initial`.
**Date:** 2026-06-21
**Future intent:** Apply this rule wherever engine code mutates a validated model.

---

## Mental Model: validators run on *construction*, not on *assignment*

By default a pydantic v2 model has `model_config["validate_assignment"] = False`.
Validators (`@field_validator`, `@model_validator`) run when the object is
**built** (`Model(...)`, `model_validate(...)`), **not** when you later assign to a
field. So an invariant you carefully enforced at construction is silently
bypassed by in-place mutation:

```python
attr = Attribute(initial=10, current=10)   # validated ✓
attr.current = -5                           # NO validation — invariant breached, no error
attr.current = 999                          # NO validation — current > initial, still silent
```

| Operation | Runs validators? |
|-----------|------------------|
| `Attribute(initial=10, current=-5)` | ✅ raises `ValidationError` |
| `Model.model_validate({...})` | ✅ |
| `attr.current = -5` (default config) | ❌ silently accepted |
| `attr.current = -5` (with `validate_assignment=True`) | ✅ raises |

---

## Fix used in this repo: reconstruct the `Attribute`

Combat applies damage by building a **new** `Attribute`, so the invariant is
re-checked (and the value is clamped at 0 first, since stamina cannot go negative):

```python
sheet.stamina = Attribute(
    initial=sheet.stamina.initial,
    current=max(0, sheet.stamina.current - damage),
)
```

Reconstruction (rather than enabling `validate_assignment`) was chosen because:
- the engine already treats storage reads as fresh deep copies, so building new
  value objects is cheap and side-effect-free;
- it keeps the clamp-then-validate logic explicit at each mutation site;
- it avoids a global config flag whose cost applies to *every* assignment.

The alternative — `model_config = ConfigDict(validate_assignment=True)` on
`Attribute` — also works and would turn the bad assignment into a raised error;
reach for it if direct field mutation becomes common.

---

## Relation to ADRs and next steps

- Reinforces **CONTRACTS §2**: "invariant enforcement lives in `dominio`." That
  guarantee only holds at construction time, so callers must mutate by
  re-construction (or opt into `validate_assignment`).
- Next step: if a future module starts mutating sheets field-by-field, prefer
  enabling `validate_assignment=True` on `Attribute` over scattering manual clamps.
