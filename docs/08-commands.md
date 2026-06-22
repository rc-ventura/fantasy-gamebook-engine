# 08 — Module `commands` (system commands)

## Responsibility
Player actions **outside the narrative flow**: check character sheet, inventory, map, save.
They read (and sometimes write) state via MCP and print a formatted result, without altering
the story. The digital equivalent of the Adventure Sheet in a gamebook.

## Exposed interface (contract)
Each command: `trigger -> read/write MCP -> print formatted -> return to flow`.

```
/hero      -> read_character_sheet -> prints Skill/Stamina/Luck (current/initial),
                                      provisions, gold, inventory, conditions.
                                      available even during combat.
/backpack  -> read_character_sheet -> details inventory; allows using an item (update_character_sheet).
/map       -> read_world           -> visited_locations + current_location.
/save      -> save_progress(name)  -> confirms checkpoint.
```

## Dependencies (interface only)
- MCP tool contract from `mcp` (05), primarily the read tools.

## Pluggability
- **Adding a command** = register a new trigger following the same pattern; does not touch
  rules or narrative.
- In Phase 2, these become UI components (character panel, inventory modal) over the same
  data — the "command" becomes a button.

## Definition of done
- `/hero` always reflects real MCP state (never a narrated value).
- Commands do not alter the narrative or the turn (except using an item, which is an explicit state change).
- Uniform pattern: easy to add `/map`, `/journal`, etc.
