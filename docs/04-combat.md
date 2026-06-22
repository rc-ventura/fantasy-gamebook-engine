# 04 — Module `combat` (lifecycle)

## Responsibility
Orchestrate the **combat sub-loop**: open a fight, resolve rounds (using the `rules` engine),
apply damage to the character sheet and enemies, persist state, and conclude with a result.
This is the "fight mode" separated from the narrative.

## Exposed interface (contract)

```
start_combat(enemies: {name, skill, stamina}[], flee_allowed: bool) -> Combat
    # creates combat_id, persists initial state

resolve_round(combat_id, use_luck: bool) -> {
    hero_attack, enemy_attack, hit_by,
    damage_applied, hero_stamina, enemy_stamina,
    luck_used?: { roll, success },
    ended: bool, winner?: "hero" | "enemy"
}
    # reads sheet + combat, calls rules.resolve_round (+ luck modifier if use_luck),
    # updates stamina values, persists. Hero reaching 0 -> marks defeat.

flee(combat_id) -> { damage_taken: 2, hero_stamina, ended: true }
    # only if flee_allowed

end_combat(combat_id) -> FinalResult {
    winner, hero_final_stamina, luck_spent, rounds, drops?: str[]
}
    # victory: saves stamina to sheet; defeat: sheet.alive = false
```

## Dependencies (interfaces only)
- `rules` (01) for round math.
- `storage` (03) for reading/writing `Combat` and `CharacterSheet`.
- `domain` (02) for types.

## Pluggability
Not pluggable in itself, but isolates combat so it can be invoked by any harness —
including as a sub-agent in Claude Code (receives context, runs, returns `FinalResult`).

## Note on player interaction
The "test luck or not" decision each round comes from the **harness** (which talks to the
player). This module is stateless with respect to the UI: it receives `use_luck` already
decided and returns the result.

## Definition of done
- An active combat survives a restart (state persisted by `combat_id`).
- Death in combat correctly propagates `alive: false`.
- Testable with in-memory `storage` and `rules` with a fixed seed.
