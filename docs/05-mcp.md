# 05 — Module `mcp` (server / tool contract)

## Responsibility
Expose the rules engine + state as **MCP tools** consumable by any harness. It is the
facade the narrator (AI) uses. Contains no game rules of its own — only orchestrates
`rules`, `combat`, and `storage`. This is what enforces "the AI never rolls dice in prose."

## Exposed interface (MCP tool contract)

```
# Dice / luck
roll_dice(notation) -> { rolls, total }
test_luck() -> { roll, success, luck_after }

# Character sheet
create_character(name) -> CharacterSheet
read_character_sheet() -> CharacterSheet
update_character_sheet(changes) -> CharacterSheet   # enforces invariants via domain

# World / events
read_world() -> World
update_world(changes) -> World
register_event(type, data) -> None
read_events() -> Event[]
read_summary() -> str
update_summary(text) -> None

# Combat (delegates to module 04)
start_combat(enemies, flee_allowed) -> Combat
resolve_combat_round(combat_id, use_luck) -> RoundOutcome
flee_combat(combat_id) -> FleeResult
end_combat(combat_id) -> FinalResult

# End-of-game / session
archive_character(destination) -> None
save_progress(slot?) / load_progress(slot?)
```

## Dependencies (interfaces only)
- `rules` (01), `combat` (04), `storage` (03 — implementation injected at startup), `domain` (02).

## Pluggability
The **tool contract is stable**: it is swap boundary #3 seen from the other side. Any
harness (Claude Code now, PydanticAI later) speaks the same MCP without changes. The
`storage` implementation is injected at server startup (JSON or Postgres).

## Definition of done
- Server starts and lists all tools.
- Each tool validates input and never leaves state inconsistent.
- Swapping `JSONStorage` for another implementation requires no tool changes.
