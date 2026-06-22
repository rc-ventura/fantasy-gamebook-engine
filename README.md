# Fantasy Gamebook Engine

A solo-play **livro-jogo** (Fighting Fantasy–style gamebook) engine where an AI acts as the
game master and narrator. The whole design turns on one hard rule:

> **The AI never invents numbers or rolls dice in prose.** All randomness, state, and combat
> math go through an MCP server. The AI only narrates and offers choices.

Everything numeric — dice, attribute generation, luck tests, combat rounds, persistence — is
owned by a deterministic Python engine and exposed to the narrator as **MCP tools**. The
narrator (Phase 1: Claude Code) reads real state, calls tools, and writes the story around the
results.

**Status:** Phase-1 MVP — implemented and green. Python engine under `src/gamebook/`, an MCP
server exposing **18 tools**, **158 passing tests** at **96% coverage** across `tests/engine`,
`tests/server`, and `tests/qa`. The narrator harness lives as Claude Code skills and commands
under `.claude/`.

---

## Why it's built this way

The system decomposes into 8 modules, and the **golden rule of the design** is that
dependency arrows point only at *interfaces/contracts*, never at concrete implementations.
That discipline is what makes three things swappable without touching the rest:

1. **Storage** — `JSONStorage` today, `PostgresStorage` tomorrow. Injected at server startup.
2. **Adventure** — swap the lore module without touching the engine. Today a `SKILL.md`.
3. **Harness** — swap who narrates (terminal → web) while reusing the same MCP tool contract.

```
07 harness ───────► 05 mcp ◄──────── 08 comandos
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   01 regras     04 combate     03 storage (interface)
        │             │             ▲
        └──────►──────┘             │ implements
                  │                 │
                  ▼                 │
            02 dominio ◄────────────┘   (shared data contracts)

06 modulo-aventura ──(lore consumed by)──► 07 harness
```

| #  | Module            | Responsibility                                                                 | Pluggable?              |
|----|-------------------|--------------------------------------------------------------------------------|-------------------------|
| 01 | `regras`          | Pure rules engine — dice, attributes, luck test, one combat round. No I/O, RNG injected. | — (stable)        |
| 02 | `dominio`         | Shared data contracts + invariant validation. Depends on nothing.              | — (stable)              |
| 03 | `storage`         | Persistence behind the `StorageBackend` interface.                             | ✅ JSON ↔ Postgres      |
| 04 | `combate`         | Combat lifecycle (start → rounds → flee → end).                                 | —                       |
| 05 | `mcp`             | MCP server exposing tools to the harness. No game rules of its own.            | — (stable contract)     |
| 06 | `modulo-aventura` | Pluggable static lore (zones, bestiary, victory). Debut: **Ignarok**.          | ✅ Ignarok ↔ others     |
| 07 | `harness`         | The narrator/master that talks to the player and calls the MCP.                | ✅ Claude Code ↔ agent  |
| 08 | `comandos`        | System commands (`/stats`, `/mochila`, `/mapa`, `/salvar`).                     | ✅ add new ones         |

## Project layout

```
src/gamebook/
  dominio/      # data contracts: CharacterSheet, World, Event, Combat, ArchiveRecord
  regras/       # pure rules engine (interfaces + implementation), injectable RNG
  storage/      # StorageBackend interface + JSONStorage + in-memory impl
  combate/      # combat lifecycle (interfaces + implementation)
  mcp/          # FastMCP server over stdio — orchestrates the modules
docs/
  00-indice.md … 08-comandos.md   # Portuguese specs (requirements)
  CONTRACTS.md                    # authoritative English code contract
  adrs/                           # architecture decision records
  learning-lessons/               # captured gotchas
.claude/
  skills/       # game-master, combat-sub-agent, ignarok (the Phase-1 harness)
  commands/     # /stats, /mochila, /mapa, /salvar
tests/
  engine/  server/  qa/
```

## Requirements

- Python **3.13** (`.python-version`), `requires-python >= 3.12`
- [`uv`](https://docs.astral.sh/uv/) for dependency management and running

## Quickstart

```bash
# Run the full test suite
uv run pytest -q

# Scope it
uv run pytest tests/engine -q     # pure rules (seeded RNG, in-memory storage)
uv run pytest tests/server -q     # storage + MCP server
uv run pytest tests/qa -q         # plugability / isolation / e2e

# The golden-rule plugability audit (catches any module reaching past an interface)
uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q

# Start the MCP server over stdio (exits cleanly on EOF)
uv run python -m gamebook.mcp.server
```

The server is registered for Claude Code in `.mcp.json`, so the narrator skills can call it
directly.

## MCP tools (18)

The authoritative contract is `docs/CONTRACTS.md` §6. Grouped by purpose:

| Group       | Tools                                                                                   |
|-------------|-----------------------------------------------------------------------------------------|
| Dice & luck | `roll_dice`, `test_luck`                                                                 |
| Character   | `create_character`, `read_character_sheet`, `update_character_sheet`, `archive_character`|
| World       | `read_world`, `update_world`                                                             |
| Chronicle   | `register_event`, `read_events`, `read_summary`, `update_summary`                        |
| Combat      | `start_combat`, `resolve_combat_round`, `flee_combat`, `end_combat`                      |
| Saves       | `save_progress`, `load_progress`                                                         |

## Game rules (reference)

- **Attributes:** `skill` = 1d6+6, `stamina` = 2d6+12, `luck` = 1d6+6 — each tracks `initial`/`current`.
- **Luck test:** success if roll ≤ current luck; luck always decrements by exactly 1 afterward.
- **Combat round:** each side's attack strength (FA) = `skill` + 2d6; higher FA hits for base
  damage 2, a tie deals 0.
- **Luck on a hit:** won+lucky → 4, won+unlucky → 1, lost+lucky → 1, lost+unlucky → 3.
- **Death / flee:** hero at 0 stamina → `alive: false`; fleeing costs 2 stamina and only if allowed.

`regras` and `combate` are tested in full isolation with a seeded RNG and in-memory storage —
deterministic, no disk, no AI.

## Playing a session (Phase-1 harness)

When you sit down to **play** rather than develop, Claude Code becomes the Game Master.

**Session-opening rule:** before narrating anything, the master reads real engine state via
MCP (`read_character_sheet`, `read_world`, `read_events`, `read_summary`). No living character
→ it offers `create_character` and starts the adventure's opening. A living character → it
resumes from the exact recorded point (never restarts, re-rolls, or contradicts recorded
facts). Every number and state change routes through MCP tools.

- **Skills** (`.claude/skills/`): `game-master` (narrator), `combat-sub-agent` (runs one
  fight), `ignarok` (the debut adventure — swap this file to swap adventures).
- **Commands** (`.claude/commands/`): `/stats`, `/mochila`, `/mapa`, `/salvar` — read-outs and
  checkpoints that reflect real MCP state and don't advance the story.

## Documentation

- **`docs/00-indice.md`** — start here; maps every module. The PT specs (`00…08`) are the
  *requirements*.
- **`docs/CONTRACTS.md`** — the authoritative English code contract (cross-module interfaces,
  domain schema §2, MCP tool contract §6). When code and a spec disagree, CONTRACTS.md governs.
- **`docs/adrs/`** — architecture decision records (ADR-001 … ADR-010).
- **`docs/learning-lessons/`** — captured gotchas worth not relearning.
- **`CLAUDE.md`** — guidance for Claude Code working in this repo.

## Roadmap

- **Phase 1 (current):** Claude Code as harness, `JSONStorage`, adventure as `SKILL.md`.
- **Phase 2:** a PydanticAI/FastAPI harness with structured `Cena` output for a web frontend,
  plus `PostgresStorage` — reusing the *same* MCP tool contract and adventure module unchanged.
  That reuse is the entire point of the architecture.
