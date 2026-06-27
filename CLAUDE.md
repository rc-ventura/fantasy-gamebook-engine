# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: Phase-1 MVP implemented

The engine is built and green: a Python package under `src/gamebook/` (modules `domain`, `rules`, `storage`, `combat`, `mcp`), an MCP server exposing 18 tools, and **158 passing tests** (96% coverage) across `tests/engine`, `tests/server`, `tests/qa`. The Phase-1 harness (Game Master) lives as Claude Code skills/commands under `.claude/`.

**Single source of truth.** All specs in `docs/00-index.md … docs/08-commands.md` are the *requirements* (read `00-index.md` first — it maps every module). `docs/CONTRACTS.md` is their **authoritative English code contract**: every cross-module interface, the domain-model schema (§2), and the MCP tool contract (§6). When changing code, CONTRACTS.md governs — if you must deviate, update it deliberately, don't drift.

Each spec follows the template: **Responsibility · Exposed interface · Dependencies · Pluggability · Definition of done**.

Note: the project directory name has a **trailing space** (`fantasy-gamebook-engine `). Quote paths in shell commands.

## Build / test / run

Everything goes through `uv` (deps already installed — don't `uv add` without updating CONTRACTS.md):
- `uv run pytest -q` — full suite. Scope it: `uv run pytest tests/engine -q` (pure rules), `tests/server` (storage + MCP), `tests/qa` (plugability/isolation/e2e).
- `uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q` — the golden-rule plugability audit (catches any module reaching past an interface).
- `uv run python -m gamebook.mcp.server` — start the MCP server over stdio (registered for Claude Code in `.mcp.json`; exits cleanly on EOF).
- `rules`/`combat` tests use a seeded RNG and in-memory storage: deterministic, no disk, no AI.

### Phase-2 web service
- `DATABASE_URL=postgresql+asyncpg://... uv run alembic upgrade head` — run the initial DB migration.
- `DATABASE_URL=... uv run uvicorn gamebook_web.api.app:app --reload` — start the FastAPI service (hot-reload).
- `docker compose up` — start Postgres + OIDC provider + OTLP collector locally (see `docker-compose.yml`).
- `DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/server/test_postgres_storage.py -v` — live Postgres contract tests.
- `uv run python -m gamebook.mcp.server` — Phase-1 path (JSONStorage, no Postgres).
- `DATABASE_URL=... GAMEBOOK_CAMPAIGN_ID=<uuid> uv run python -m gamebook.mcp.server` — Phase-2 path (PostgresStorage, scoped to campaign).

## What this is

An engine for a solo-play **gamebook** (Fighting Fantasy–style) where an AI acts as the game master/narrator. The hard rule that shapes the whole design: **the AI never invents numbers or rolls dice in prose** — all randomness, state, and combat math go through an MCP server. The AI only narrates and offers choices.

## Architecture: modules depend only on interfaces

The system decomposes into 8 modules (00 is the index). The **golden rule of the design**: dependency arrows point only at *interfaces/contracts*, never at concrete implementations. This is what makes the three swap points below possible.

| # | Module | Responsibility |
|---|--------|----------------|
| 01 | `rules` | Pure rules engine — dice, attribute generation, luck test, one combat round. No I/O, no state. RNG is injected. |
| 02 | `domain` | Shared data contracts (`CharacterSheet`, `World`, `Event`, `Combat`, `ArchiveRecord`) + invariant validation. Base of the pyramid; depends on nothing. |
| 03 | `storage` | Persistence behind the `StorageBackend` interface. **Swap point #1.** |
| 04 | `combat` | Combat lifecycle (start → resolve rounds → flee → end). Stateless re: UI. Depends on `rules`, `storage`, `domain` interfaces. |
| 05 | `mcp` | MCP server exposing tools to the harness. Orchestrates `rules`/`combat`/`storage`; contains no game rules of its own. **Stable tool contract.** |
| 06 | `adventure-module` | Pluggable static lore (zones, bestiary, victory condition). **Swap point #2.** Debut module: `Ignarok`. |
| 07 | `harness` | The narrator/master that talks to the player and calls the MCP. **Swap point #3.** |
| 08 | `commands` | System commands (`/hero`, `/backpack`, `/map`, `/save`) that read/write state via MCP and print, without altering the story. |

Dependency direction: `harness` (07) and `commands` (08) → `mcp` (05) → {`rules` (01), `combat` (04), `storage` interface (03)} → `domain` (02). `adventure-module` (06) is consumed by the harness as lore, not by the engine.

### The three swap boundaries (the point of the whole architecture)
1. **`StorageBackend`** (03) — Phase 1 `JSONStorage` (one file per entity in `estado/`, atomic write = temp file + rename) ↔ Phase 2 `PostgresStorage`. The concrete impl is **injected at MCP server startup**; no other module changes.
2. **`AdventureModule`** (06) — swap the adventure without touching the engine. Phase 1 = a `SKILL.md`; Phase 2 = a data record.
3. **Harness** (07) — Phase 1 = Claude Code (MCP + skills) ↔ Phase 2 = PydanticAI/FastAPI agent with structured `Scene` output for a web frontend. Same MCP, same adventure module.

When adding or changing code, preserve these boundaries: e.g. `mcp` and `combat` must depend on the `StorageBackend` *interface*, never on `JSONStorage`. Prove it by making the in-memory storage impl work for tests.

## Conventions

- **Language**: everything is English — package names (`domain`, `rules`, `combat`, `storage`, `mcp`), types, fields, and MCP tools (`CharacterSheet`, `World`, `roll_dice`, `test_luck`, `skill`/`stamina`/`luck`). Use the identifier mapping in `docs/CONTRACTS.md` §0; keep new identifiers consistent with it.
- **Determinism**: `rules` is pure and the RNG is injectable so tests can use a fixed seed for reproducible results. Test `rules` and `combat` in full isolation (in-memory storage, seeded RNG) — no disk, no AI.
- **State changes only via MCP**: the harness routes every numeric/state mutation through MCP tools (`roll_dice`, `test_luck`, `update_character_sheet`, `register_event`, combat tools …). `/hero` etc. must reflect real MCP state, never a narrated value.
- **Invariants** live in `domain` (e.g. `0 <= current <= initial` for an `Attribute`); serialization must round-trip (object → JSON → identical object).
- **Atomic, consistent storage**: every `StorageBackend` impl must not corrupt state if the process dies mid-write.

## Game rules (from `01-rules.md`, for reference when implementing)

- Attributes: `skill` = 1d6+6, `stamina` = 2d6+12, `luck` = 1d6+6 (each tracks `initial`/`current`).
- Luck test (`test_luck`): success if roll ≤ current luck; luck always decrements by exactly 1 afterward.
- Combat round: each side's attack strength = `skill` + 2d6; higher AS hits for base damage 2, tie = 0 damage.
- Luck modifier on a hit: won+lucky → 4, won+unlucky → 1, lost+lucky → 1, lost+unlucky → 3.
- Combat: hero reaching 0 stamina → `alive: false`; flee costs 2 damage and only if `flee_allowed`.

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

**Commands (`.claude/commands/`):** `/hero`, `/backpack`, `/map`, `/save` — system
read-outs/checkpoints that reflect **real MCP state** (never narrated values) and do not
advance the story (except `/backpack` using an item, an explicit state change via
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
| [ADR-011](./docs/adrs/ADR-011-phase2-harness-pydanticai-narrator-backend.md) | Phase-2 production harness — PydanticAI core, model/provider-agnostic, behind a NarratorBackend port | Accepted | 2026-06-26 |
| [ADR-012](./docs/adrs/ADR-012-react-vite-typescript-spa-toolchain.md) | React + Vite + TypeScript toolchain for `frontend/` SPA | Accepted | 2026-06-27 |
| [ADR-013](./docs/adrs/ADR-013-async-alembic-env-database-url.md) | Async Alembic env.py pattern with asyncpg and DATABASE_URL | Accepted | 2026-06-27 |
| [ADR-014](./docs/adrs/ADR-014-vite-env-import-meta-types.md) | `import.meta.env` types via `src/vite-env.d.ts` (not tsconfig types array) | Accepted | 2026-06-27 |
| [ADR-015](./docs/adrs/ADR-015-mock-mode-client-side-fixture-layer.md) | Mock mode via a client-side fixture layer (VITE_USE_MOCK=true) | Accepted | 2026-06-27 |

## Learning Lessons

> Folder: `./docs/learning-lessons/`

- [Narrative patterns for a "numbers-never-in-prose" Game Master](./docs/learning-lessons/numbers_never_in_prose_narrative_patterns.md) — 2026-06-21
- [SKILL.md & slash-command formatting constraints](./docs/learning-lessons/skill_and_command_formatting_constraints.md) — 2026-06-21
- [pytest collects any `test_`-prefixed callable imported into a test module](./docs/learning-lessons/pytest_collects_imported_test_prefixed_functions.md) — 2026-06-21
- [pydantic v2 skips validation on attribute assignment by default](./docs/learning-lessons/pydantic_v2_skips_validation_on_attribute_assignment.md) — 2026-06-21
- [FastMCP tool return-serialization & invocation gotchas](./docs/learning-lessons/fastmcp_tool_return_serialization_gotchas.md) — 2026-06-21
- [A `TYPE_CHECKING` import is absent from runtime `sys.modules` — isolation checks must assert absence, not presence](./docs/learning-lessons/type_checking_imports_absent_from_runtime_sys_modules.md) — 2026-06-21
- [Vite config (`vite.config.ts`) requires `@types/node` as an explicit devDependency](./docs/learning-lessons/vite_config_needs_types_node.md) — 2026-06-27
- [JSX string attributes do NOT process JavaScript escape sequences (`\n` is literal)](./docs/learning-lessons/jsx-string-attributes-dont-process-escape-sequences.md) — 2026-06-27

<!-- SPECKIT START -->
**Active feature**: `002-persistence-foundation` (first slice of the decomposed
`001-web-platform-migration` epic). The epic was decomposed into a dependency-ordered chain of
independently-shippable features; see the Decomposition section in
`specs/001-web-platform-migration/spec.md`:
- `002-persistence-foundation` ← active (PostgresStorage behind `StorageBackend`, swap boundary #1)
- `003-web-backend-mvp` (FastAPI + MCP host + PydanticAI narrator + `Scene` + documented API
  playable via script; depends on `002`)
- `004-accounts-hardening-obs` (real OIDC + accounts + session lease + resume + privacy +
  production hardening + OpenTelemetry; depends on `002`, `003`)
- `005-professional-spa` (React/Vite SPA consuming `003`'s documented API; depends on `003`,
  sign-in UI also `004`; can develop in parallel with `004` against `003`'s frozen OpenAPI)

Dependency chain: `002` → `003` → `004` // `005`.

**Active feature artifacts** (`specs/002-persistence-foundation/`):
- Spec: `specs/002-persistence-foundation/spec.md`
- Plan: `specs/002-persistence-foundation/plan.md`
- Tasks: `specs/002-persistence-foundation/tasks.md`

**Shared epic design artifacts** (authoritative for every slice; referenced, not duplicated):
- Research (tech decisions): `specs/001-web-platform-migration/research.md`
- Data model: `specs/001-web-platform-migration/data-model.md`
- Contracts: `specs/001-web-platform-migration/contracts/` (`http-api.md`, `scene.md`)
- Quickstart (validation): `specs/001-web-platform-migration/quickstart.md`

Stack across the epic: FastAPI + Postgres (`PostgresStorage` behind `StorageBackend`), a new
agent-based narrator on `claude-opus-4-8` emitting a Pydantic-validated `Scene`, a separate OIDC
auth service, a React/Vite SPA, and OpenTelemetry. The MCP tool contract and the engine
(`src/gamebook/`) stay behavior-unchanged. Constitution: `.specify/memory/constitution.md` (v1.0.0).
<!-- SPECKIT END -->
