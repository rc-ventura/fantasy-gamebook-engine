# 02 — Module `domain` (data contracts)

## Responsibility
Define the **shared data models** used across modules. This is the "common language":
any module that exchanges data uses these contracts. No logic, only structure + validation.

## Exposed interface (contract)

```
Attribute  = { initial: int, current: int }   # invariant: 0 <= current <= initial

CharacterSheet = {
    name: str,
    skill: Attribute, stamina: Attribute, luck: Attribute,
    inventory: str[], gold: int, provisions: int,
    conditions: str[], alive: bool
}

World = {
    current_location: str, visited_locations: str[],
    known_npcs: { name: str, state: str }[],
    flags: { [key: str]: bool }, turn: int
}

Event = { turn: int, type: str, data: object, timestamp: str }

Combat = {
    combat_id: str,
    enemies: { name, skill, stamina }[],
    round: int, flee_allowed: bool, ended: bool,
    winner?: "hero" | "enemy"
}

ArchiveRecord = {   # graveyard / hall of fame
    name, turns, outcome: "death" | "victory",
    location, cause?, final_inventory: str[]
}
```

## Dependencies
None. This is the base of the pyramid.

## Pluggability
Not pluggable, but **versionable**: schema changes must be backwards-compatible or include
a migration. The `CharacterSheet` schema was designed to map almost 1:1 to a Postgres table.

## Definition of done
- Invariant validation (e.g. `current <= initial`) is centralized here.
- Round-trip serialization: object → JSON → identical object.
