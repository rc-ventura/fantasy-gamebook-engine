---
description: Show the hero's character sheet (skill/stamina/luck, gold, provisions, inventory, conditions) from real MCP state. Works even during combat.
---

# /hero

Print the hero's full character sheet from **real engine state**. This is a read-out, not a
story turn — it must reflect exactly what the MCP returns, **never** a narrated or remembered
value. Available at any time, **including during combat**.

Steps:

1. Call `read_character_sheet`.
2. If there is no character (or `alive: false`), say so plainly and offer to start a new
   adventure — do not fabricate a sheet.
3. Otherwise format the result clearly (values straight from the tool):

```
═══ <name> ═══
SKILL     <skill.current>/<skill.initial>
STAMINA   <stamina.current>/<stamina.initial>
LUCK      <luck.current>/<luck.initial>
Gold      <gold>
Provisions <provisions>
Inventory <comma-separated inventory, or "(empty)">
Conditions <comma-separated conditions, or "(none)">
```

4. Do not change any state. After printing, return the player to the current turn / combat
   round without advancing the story.
