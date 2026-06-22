# 01 — Module `rules` (pure engine)

## Responsibility
Resolve all game math in a **deterministic, pure** way: dice rolling, attribute generation,
luck tests, and combat round resolution. No I/O, no state, no knowledge of AI or storage.
This is the piece that travels **intact** to Phase 2.

## Exposed interface (contract)
Pure functions; the random source is **injectable** (for deterministic tests).

```
roll_dice(notation: str, rng) -> { rolls: int[], total: int }
    # notation: "NdM", "NdM+K", "NdM-K"  (e.g. "2d6+6")

generate_attributes(rng) -> {
    skill:   { initial, current },   # 1d6+6
    stamina: { initial, current },   # 2d6+12
    luck:    { initial, current },   # 1d6+6
}

test_luck(current_luck: int, rng) -> {
    roll: int, success: bool, luck_after: int   # luck_after = current_luck - 1
}

resolve_round(hero_skill: int, enemy_skill: int, rng) -> {
    hero_attack:  int, enemy_attack: int,
    hit_by: "hero" | "enemy" | "tie",
    base_damage: int   # 2 to the loser; 0 on a tie
}

apply_luck_modifier(hit_by, base_damage, luck_success: bool) -> final_damage: int
    # won+lucky -> 4 ; won+unlucky -> 1
    # lost+lucky -> 1 ; lost+unlucky -> 3
```

## Dependencies
- Only types from module 02 (`domain`) — ideally not even that (can return plain dicts).
- **No** dependency on storage, MCP, or AI.

## Pluggability
Not pluggable (it is the stable core). But the **injectable rng** allows swapping the
randomness source (e.g. fixed seed in tests, cryptographic RNG in production).

## Definition of done
- 100% testable in isolation, without AI and without disk.
- With a fixed seed, results are reproducible.
- Tests cover: invalid notation parsing, attribute ranges, luck always decrements by 1,
  tie produces no damage, and all 4 luck modifier cases.
