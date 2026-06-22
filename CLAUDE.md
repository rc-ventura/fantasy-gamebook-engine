# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: Phase-1 MVP implemented

The engine is built and green: a Python package under `src/gamebook/` (modules `dominio`, `regras`, `storage`, `combate`, `mcp`), an MCP server exposing 18 tools, and **158 passing tests** (96% coverage) across `tests/engine`, `tests/server`, `tests/qa`. The Phase-1 harness (Game Master) lives as Claude Code skills/commands under `.claude/`.

**Two sources of truth, two languages.** The Portuguese specs in `docs/00-indice.md … docs/08-comandos.md` are the *requirements* (read `00-indice.md` first — it maps every module). `docs/CONTRACTS.md` is their **authoritative English code contract**: every cross-module interface, the domain-model schema (§2), and the MCP tool contract (§6). When changing code, CONTRACTS.md governs — if you must deviate, update it deliberately, don't drift.

Each spec follows the template: **Responsabilidade · Interface exposta · Dependências · Plugabilidade · Critérios de pronto** ("Critérios de pronto" = acceptance criteria = definition of done).

Note: the project directory name has a **trailing space** (`fantasy-gamebook-engine `). Quote paths in shell commands.

## Build / test / run

Everything goes through `uv` (deps already installed — don't `uv add` without updating CONTRACTS.md):
- `uv run pytest -q` — full suite. Scope it: `uv run pytest tests/engine -q` (pure rules), `tests/server` (storage + MCP), `tests/qa` (plugability/isolation/e2e).
- `uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q` — the golden-rule plugability audit (catches any module reaching past an interface).
- `uv run python -m gamebook.mcp.server` — start the MCP server over stdio (registered for Claude Code in `.mcp.json`; exits cleanly on EOF).
- `regras`/`combate` tests use a seeded RNG and in-memory storage: deterministic, no disk, no AI.

## What this is

An engine for a solo-play **livro-jogo** (Fighting Fantasy–style gamebook) where an AI acts as the game master/narrator. The hard rule that shapes the whole design: **the AI never invents numbers or rolls dice in prose** — all randomness, state, and combat math go through an MCP server. The AI only narrates and offers choices.

## Architecture: modules depend only on interfaces

The system decomposes into 8 modules (00 is the index). The **golden rule of the design**: dependency arrows point only at *interfaces/contracts*, never at concrete implementations. This is what makes the three swap points below possible.

| # | Module | Responsibility |
|---|--------|----------------|
| 01 | `regras` | Pure rules engine — dice, attribute generation, luck test, one combat round. No I/O, no state. RNG is injected. |
| 02 | `dominio` | Shared data contracts (`CharacterSheet`, `World`, `Event`, `Combat`, `ArchiveRecord`) + invariant validation. Base of the pyramid; depends on nothing. |
| 03 | `storage` | Persistence behind the `StorageBackend` interface. **Swap point #1.** |
| 04 | `combate` | Combat lifecycle (start → resolve rounds → flee → end). Stateless re: UI. Depends on `regras`, `storage`, `dominio` interfaces. |
| 05 | `mcp` | MCP server exposing tools to the harness. Orchestrates `regras`/`combate`/`storage`; contains no game rules of its own. **Stable tool contract.** |
| 06 | `modulo-aventura` | Pluggable static lore (zones, bestiary, victory condition). **Swap point #2.** Debut module: `Ignarok`. |
| 07 | `harness` | The narrator/master that talks to the player and calls the MCP. **Swap point #3.** |
| 08 | `comandos` | System commands (`/stats`, `/mochila`, `/mapa`, `/salvar`) that read/write state via MCP and print, without altering the story. |

Dependency direction: `harness` (07) and `comandos` (08) → `mcp` (05) → {`regras` (01), `combate` (04), `storage` interface (03)} → `dominio` (02). `modulo-aventura` (06) is consumed by the harness as lore, not by the engine.

### The three swap boundaries (the point of the whole architecture)
1. **`StorageBackend`** (03) — Phase 1 `JSONStorage` (one file per entity in `estado/`, atomic write = temp file + rename) ↔ Phase 2 `PostgresStorage`. The concrete impl is **injected at MCP server startup**; no other module changes.
2. **`ModuloAventura`** (06) — swap the adventure without touching the engine. Phase 1 = a `SKILL.md`; Phase 2 = a data record.
3. **Harness** (07) — Phase 1 = Claude Code (MCP + skills) ↔ Phase 2 = PydanticAI/FastAPI agent with structured `Cena` output for a web frontend. Same MCP, same adventure module.

When adding or changing code, preserve these boundaries: e.g. `mcp` and `combate` must depend on the `StorageBackend` *interface*, never on `JSONStorage`. Prove it by making the in-memory storage impl work for tests.

## Conventions

- **Language**: the **specs** (`docs/00..08`) are Portuguese, but **all code is English** — package names stay Portuguese (`dominio`, `regras`, `combate`, `storage`, `mcp`) while types, fields, and MCP tools are English (`CharacterSheet`, `World`, `roll_dice`, `test_luck`, `skill`/`stamina`/`luck`). Use the PT→EN mapping in `docs/CONTRACTS.md` §0; keep new identifiers consistent with it.
- **Determinism**: `regras` is pure and the RNG is injectable so tests can use a fixed seed for reproducible results. Test `regras` and `combate` in full isolation (in-memory storage, seeded RNG) — no disk, no AI.
- **State changes only via MCP**: the harness routes every numeric/state mutation through MCP tools (`roll_dice`, `test_luck`, `update_character_sheet`, `register_event`, combat tools …). `/stats` etc. must reflect real MCP state, never a narrated value.
- **Invariants** live in `dominio` (e.g. `0 <= current <= initial` for an `Attribute`); serialization must round-trip (object → JSON → identical object).
- **Atomic, consistent storage**: every `StorageBackend` impl must not corrupt state if the process dies mid-write.

## Game rules (from `01-regras.md`, for reference when implementing)

- Attributes: `habilidade` = 1d6+6, `energia` = 2d6+12, `sorte` = 1d6+6 (each tracks `inicial`/`atual`).
- Luck test (`testar_sorte`): success if roll ≤ current luck; luck always decrements by exactly 1 afterward.
- Combat round: each side's attack strength (FA) = `habilidade` + 2d6; higher FA hits for base damage 2, tie = 0 damage.
- Luck modifier on a hit: won+lucky → 4, won+unlucky → 1, lost+lucky → 1, lost+unlucky → 3.
- Combat: hero reaching 0 energy → `vivo: false`; flee (`escapar`) costs 2 damage and only if `fuga_permitida`.

## Phases

- **Phase 1** (current target): Claude Code as harness consuming an MCP server, `JSONStorage`, adventure as `SKILL.md`. Sub-components per `07-harness.md`: a master `SKILL.md`, a combat sub-agent `SKILL.md`, and session-opening rules in `CLAUDE.md`.
- **Phase 2**: PydanticAI/FastAPI harness with structured output + `PostgresStorage`, reusing the same MCP tool contract and adventure module unchanged — that reuse is the entire point of the architecture.

## Phase-1 harness: running a play session (Game Master)

The Phase-1 harness lives as Claude Code skills and commands under `.claude/`. When a user
sits down to **play** (not to develop the engine), Claude Code acts as the Game Master.

**Session-opening rule (do this before narrating anything):** at the start of any play
session, the Game Master reads **real engine state via MCP first** — `read_character_sheet`,
`read_world`, `read_events`, `read_summary` — and only then narrates. No living character →
offer `create_character` and start the adventure's opening. A living character → **resume
from the exact recorded point** (never restart, never re-roll, never contradict recorded
facts). All numbers, rolls, and state changes go through MCP tools — **the master never rolls
dice or invents numbers in prose.**

**Skills (`.claude/skills/`):**
- `game-master/SKILL.md` — the narrator/master: tone, turn format (2–4 paragraphs, 2nd
  person, numbered choices, free text accepted), session-opening sequence, context
  compaction (`update_summary` ~every 6 turns or on zone change; hard facts →
  `register_event`/World flags), combat delegation, and death/victory end-states.
- `combat-sub-agent/SKILL.md` — runs one fight via the combat MCP tools
  (`start_combat` → `resolve_combat_round`/`flee_combat` → `end_combat`), asks the player
  whether to test luck each round, and returns a `FinalResult` to the master.
- `ignarok/SKILL.md` — the debut adventure module (static lore: opening, 6 zones of the Grey
  Mountain, bestiary that plugs into `start_combat`, victory flag `malachar_defeated`, and
  special rules for traps/bribes/healing). Swap this file to swap adventures.

**Commands (`.claude/commands/`):** `/stats`, `/mochila`, `/mapa`, `/salvar` — system
read-outs/checkpoints that reflect **real MCP state** (never narrated values) and do not
advance the story (except `/mochila` using an item, an explicit state change via
`update_character_sheet`).

The authoritative MCP tool contract these reference is `docs/CONTRACTS.md` §6.

## ADRs — Technical Decisions

> Folder: `./docs/adrs/`

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](./docs/adrs/ADR-001-combat-sub-agent-delegation-pattern.md) | Combat sub-agent delegation pattern | Accepted | 2026-06-21 |
| [ADR-002](./docs/adrs/ADR-002-context-compaction-strategy.md) | Context-compaction strategy for the narrator | Accepted | 2026-06-21 |
| [ADR-003](./docs/adrs/ADR-003-adventure-module-as-skill-format.md) | Adventure module encoded as a SKILL.md (swap boundary #2) | Accepted | 2026-06-21 |
| [ADR-004](./docs/adrs/ADR-004-slash-command-design-pattern.md) | Slash-command design pattern (system commands) | Accepted | 2026-06-21 |
| [ADR-005](./docs/adrs/ADR-005-determinism-via-injected-randomsource-protocol.md) | Determinism via an injected RandomSource Protocol | Accepted | 2026-06-21 |
| [ADR-006](./docs/adrs/ADR-006-combat-luck-tally-ephemeral-not-persisted.md) | Combat luck tally is ephemeral, not persisted in Combat state | Accepted | 2026-06-21 |
| [ADR-007](./docs/adrs/ADR-007-mcp-server-fastmcp-stdio.md) | MCP server uses the FastMCP high-level API over stdio transport | Accepted | 2026-06-21 |
| [ADR-008](./docs/adrs/ADR-008-two-layer-plugability-audit.md) | Two-layer plugability audit (static ast + fresh-subprocess runtime isolation) | Accepted | 2026-06-21 |
| [ADR-009](./docs/adrs/ADR-009-swap-boundary-tests-through-the-consumer.md) | Prove swap boundary #1 through the consumer, across three backends incl. an independent mock | Accepted | 2026-06-21 |
| [ADR-010](./docs/adrs/ADR-010-world-write-path-through-mcp.md) | World-write path through MCP — add `update_world` as the 18th tool (resolves §6/§2/§4 inconsistency) | Accepted | 2026-06-21 |

## Learning Lessons

> Folder: `./docs/learning-lessons/`

- [Narrative patterns for a "numbers-never-in-prose" Game Master](./docs/learning-lessons/numbers_never_in_prose_narrative_patterns.md) — 2026-06-21
- [SKILL.md & slash-command formatting constraints](./docs/learning-lessons/skill_and_command_formatting_constraints.md) — 2026-06-21
- [pytest collects any `test_`-prefixed callable imported into a test module](./docs/learning-lessons/pytest_collects_imported_test_prefixed_functions.md) — 2026-06-21
- [pydantic v2 skips validation on attribute assignment by default](./docs/learning-lessons/pydantic_v2_skips_validation_on_attribute_assignment.md) — 2026-06-21
- [FastMCP tool return-serialization & invocation gotchas](./docs/learning-lessons/fastmcp_tool_return_serialization_gotchas.md) — 2026-06-21
- [A `TYPE_CHECKING` import is absent from runtime `sys.modules` — isolation checks must assert absence, not presence](./docs/learning-lessons/type_checking_imports_absent_from_runtime_sys_modules.md) — 2026-06-21
