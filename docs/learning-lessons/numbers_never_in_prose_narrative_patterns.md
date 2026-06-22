# Narrative patterns for a "numbers-never-in-prose" Game Master

**Context:** Discovered while authoring the `game-master` SKILL for the Phase-1 gamebook
harness, encoding the hard design rule that the AI never invents numbers or rolls dice in
prose.
**Date:** 2026-06-21
**Future intent:** The narrative-quality bar for the master and any future harness (Phase 2).

---

## Mental Model: two parallel channels — fiction vs. machinery

The master runs two channels at once and must never let them bleed:

```
 FICTION (what the player reads)          MACHINERY (how it's true)
 ──────────────────────────────          ────────────────────────────
 2–4 paragraphs, 2nd person       <—→     roll_dice / test_luck
 numbered choices + free text     <—→     update_character_sheet (state)
 "the blade bites deep"           <—→     resolve_combat_round (the damage)
 "you remember the old map"       <—→     register_event / World flags (memory)
```

Every number the player "sees" in the fiction must be the *output* of a tool call, never a
value the narrator picked. If you're about to type "you take 3 damage" with no tool result,
stop and call the tool.

| Pattern | Rule | Why |
|---|---|---|
| Turn shape | 2–4 paragraphs, 2nd person, end with numbered choices | consistent, playable rhythm |
| Free text | always accept off-list actions if reasonable | agency without losing structure |
| Numbers | every roll/stat/damage via MCP tool | the engine is the single source of truth |
| Durable facts | promote to `register_event` / World flags | prose is forgettable across compaction |
| Tone hygiene | never mention MCP/tools/flags inside the fiction | machinery breaks immersion |

---

## Examples for the gamebook engine

### 1. A trap

Fiction: "The ledge gives way beneath you." Machinery: `test_luck` (which already spends 1
luck) → on failure `update_character_sheet({"stamina": {"current": <new>}})`. The narrator
describes the fall; the engine decides whether/how hard.

### 2. Resuming a session

The master reads `read_summary` + `read_world` + `read_events` before narrating, and recaps
from *recorded* facts — never re-rolls attributes or contradicts the record.

**Responsibility split:**
- Narrator: prose, choices, tone, promoting facts.
- Engine (MCP): all numbers, all persisted state.

---

## Relation to ADRs and next steps

- **ADR-001** — combat delegation (fight numbers come from the sub-agent's tool calls).
- **ADR-002** — compaction strategy (why durable facts must leave prose).
- Next step: QA should spot-check a session for any narrated number lacking a tool call.
