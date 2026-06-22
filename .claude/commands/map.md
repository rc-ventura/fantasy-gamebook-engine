---
description: Show the map — current location and visited locations from real MCP world state.
---

# /mapa  (map)

Print where the hero is and where they've been, from **real world state**. Read-out only —
it must reflect the MCP World exactly, never a narrated guess. Changes nothing.

Steps:

1. Call `read_world`.
2. Format clearly from the returned World:

```
═══ Map — Grey Mountain ═══
You are here: <current_location, or "(unknown)">
Visited:
  - <visited_locations[0]>
  - <visited_locations[1]>
  (or "(none yet)")
```

3. Optionally, if `known_npcs` is non-empty, you may add a short "Known faces" line from that
   list — but only from real state.
4. Do not advance the story or change any state. Return the player to the current turn.
