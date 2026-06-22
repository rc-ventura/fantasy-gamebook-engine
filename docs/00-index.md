# 00 — Index and Module Map

Modular decomposition of the AI-driven gamebook system. Each module has its own spec,
exposes a **contract (interface)**, and depends **only on interfaces** of other modules —
never on concrete implementations. That is what makes everything pluggable.

## Modules

| # | Module | Responsibility | Pluggable? |
|---|--------|----------------|-----------|
| 01 | `rules` | Pure rules engine (dice, luck, combat math) | — (stable) |
| 02 | `domain` | Data contracts (CharacterSheet, World, Event, Combat) | — (stable) |
| 03 | `storage` | Persistence behind an abstract interface | ✅ JSON ↔ Postgres |
| 04 | `combat` | Combat lifecycle (state + rounds) | — |
| 05 | `mcp` | MCP server: exposes tools to the harness | — (stable contract) |
| 06 | `adventure-module` | Pluggable static lore (zones, NPCs, victory) | ✅ Ignarok ↔ others |
| 07 | `harness` | The narrator/master that consumes the MCP | ✅ Claude Code ↔ PydanticAI |
| 08 | `commands` | System commands (/hero, /backpack, …) | ✅ add new ones |

## Dependency graph (arrows point only at interfaces)

```
07 harness ───────► 05 mcp ◄──────── 08 commands
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   01 rules      04 combat     03 storage (interface)
        │             │             ▲
        └──────►──────┘             │ implements
                  │                 │
                  ▼                 │
            02 domain ◄─────────────┘  (shared data contracts)

06 adventure-module ──(lore consumed by)──► 07 harness
```

Golden rule of modularity: arrows point only at **interfaces**. `mcp` knows the
`StorageBackend` *interface*, not the JSON implementation. `harness` knows the MCP
*tool contract*, not the code behind it.

## The 3 swap boundaries that matter
1. **`StorageBackend`** (module 03) — swap persistence without touching anything else.
2. **`AdventureModule`** (module 06) — swap the adventure without touching the engine.
3. **Harness** (module 07) — swap the narrator (terminal → web) reusing the same MCP.

## Template for each spec
Responsibility · Exposed interface (contract) · Dependencies · Pluggability ·
Definition of done.
