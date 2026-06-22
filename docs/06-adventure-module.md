# 06 — Module `adventure-module` (pluggable content) ⭐

## Responsibility
Contain the **static lore** of an adventure: the structure the master uses to improvise.
This is swap boundary #2: swapping adventures = swapping this artifact, without touching
the engine. In Phase 1 it is a `SKILL.md`; in Phase 2, a data record / module file.

## Exposed interface (contract `AdventureModule`)

```
AdventureModule = {
    metadata: { name, description, tone },
    opening: str,                       # initial situation / hook
    zones: [{
        id, name, description, atmosphere,
        difficulty: int                 # enemy difficulty scale
    }],
    bestiary: [{
        name, skill, stamina, behavior, drops?: str[]
    }],
    victory_condition: { description, flag: str },   # flag set in World on victory
    special_rules?: str[]               # e.g. traps, bribes
}
```

The master (harness) reads this contract and **generates** the content of each scene
within it. The engine (`mcp`) has no knowledge of the adventure module — only the
character sheet / world / events.

## Dependencies
None in code. Conceptually references enemy types (compatible with `combat`).

## Pluggability ⭐
- **Debut module:** `Ignarok` — Grey Mountain, archmage Malachar, 5–7 progressive zones,
  victory = defeat Malachar and escape. **Original** content (inspired by the classic,
  without names/puzzles/text from the original book — copyright concerns).
- New modules = new files with the same contract. Same engine, infinite adventures.

## Definition of done
- The master can run a complete adventure (opening → zones → victory) using only this artifact.
- Bestiary enemies plug directly into `start_combat`.
- Victory condition is a verifiable flag in `World`.
