---
description: Save the game — create a checkpoint of current progress via MCP and confirm it.
argument-hint: [slot name, optional]
---

# /save

Checkpoint the current progress through MCP and confirm. This does not change the story —
it persists a save slot.

Steps:

1. Take the slot name from `$ARGUMENTS` if the player gave one; otherwise pass none (the
   engine uses its default slot).
2. Call `save_progress(slot=<name or none>)`.
3. On the returned `{ok: true, slot}`, confirm plainly:

```
✔ Progress saved — checkpoint "<slot>".
```

4. If the call does not return `ok`, tell the player the save failed and do not pretend it
   succeeded.
5. Return the player to the current turn. (To restore a checkpoint later, the engine's
   `load_progress` is used at session start by the Game Master.)
