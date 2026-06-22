# 03 — Module `storage` (pluggable persistence) ⭐

## Responsibility
Persist and retrieve all state that survives between sessions, **behind an abstract
interface**. This is swap boundary #1: swapping JSON for Postgres must not affect any
other module.

## Exposed interface (contract) — `StorageBackend`

```
interface StorageBackend:
    # Character
    load_character() -> CharacterSheet | None
    save_character(sheet: CharacterSheet) -> None

    # World
    load_world() -> World
    save_world(world: World) -> None

    # Events / timeline (append-only)
    append_event(event: Event) -> None
    load_events() -> Event[]

    # Narrative summary
    load_summary() -> str
    save_summary(text: str) -> None

    # Active combat
    load_combat(combat_id: str) -> Combat | None
    save_combat(combat: Combat) -> None
    remove_combat(combat_id: str) -> None

    # End-of-game
    archive(record: ArchiveRecord, destination: "graveyard" | "hall_of_fame") -> None

    # Save slots (optional)
    save_slot(name: str) -> None
    load_slot(name: str) -> None
```

Required guarantee from all implementations: **atomic writes** (no state corruption if the
process dies mid-write) and consistent reads.

## Dependencies
- Module 02 (`domain`) for types.

## Pluggability ⭐
- **Phase 1 — `JSONStorage`**: one file per entity in `estado/` (`character.json`,
  `world.json`, `events.json`, `summary.md`, `combat.json`). Atomic write via temp file + rename.
- **Phase 2 — `PostgresStorage`**: same interface, tables in the database. No other module changes.
- Additional implementations possible: SQLite, Redis, in-memory (for tests).

## Definition of done
- `mcp` and `combat` modules depend **only on the interface**, never on `JSONStorage`.
- Swapping the concrete implementation at a single point (dependency injection) changes the entire backend.
- Tests with the in-memory implementation prove the rest works without disk.
