---
description: Open the backpack — list inventory, gold and provisions from real MCP state, and let the player use/consume an item (a real state change via MCP).
argument-hint: [item to use, optional]
---

# /mochila  (backpack)

Show inventory in detail and let the player **use** an item. Reading is a pure read-out;
using an item is the one allowed explicit state change (it must go through MCP, never prose).

Steps:

1. Call `read_character_sheet`. If no living character, say so and stop.
2. List the carried goods from real state:

```
═══ Backpack ═══
Gold        <gold>
Provisions  <provisions>
Inventory:
  - <item 1>
  - <item 2>
  (or "(empty)")
```

3. **Using an item** (if the player named one in `$ARGUMENTS`, or asks after seeing the list):
   - Confirm the item is actually in `inventory` / that they have provisions. If not, say so.
   - Apply the effect as a **real state change** via `update_character_sheet`, respecting the
     patch semantics and invariants:
     - **Eat provisions (heal):** read current `provisions` and `stamina`; decrement
       `provisions` by 1 and raise `stamina.current` by the item's heal amount, **capped at
       `stamina.initial`** (never over-heal — exceeding `initial` is rejected and leaves state
       unchanged, so compute the cap yourself). Write
       `{"provisions": <new>, "stamina": {"current": <capped>}}`.
     - **Consume/spend an item:** read `inventory`, remove the used item, write the full new
       list (inventory is replaced, not appended). Apply any other effect with the matching
       field (e.g. a condition cleared → new `conditions` list).
   - Narrate the effect briefly, then show the updated relevant values.
4. If no item is being used, this is read-only — change nothing. Return the player to the
   current turn afterward.
