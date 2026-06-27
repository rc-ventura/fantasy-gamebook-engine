<!--
SYNC IMPACT REPORT
==================
Version change: (template/unratified) → 1.0.0
Bump rationale: Initial ratification — first concrete constitution replacing the
  unfilled template placeholders.

Modified principles: none (initial adoption)
Added principles:
  - I. Numbers Never in Prose (NON-NEGOTIABLE)
  - II. Dependency on Interfaces Only (The Golden Rule)
  - III. CONTRACTS.md is the Single Source of Truth
  - IV. Determinism and Isolated Testing
  - V. Domain Invariants and Atomic Persistence
Added sections:
  - Additional Constraints
  - Development Workflow
  - Governance

Templates reviewed for consistency:
  - .specify/templates/plan-template.md ✅ no change (Constitution Check gate already
    references the constitution file generically)
  - .specify/templates/spec-template.md ✅ no change (generic; no principle conflict)
  - .specify/templates/tasks-template.md ✅ no change (generic; tests already optional/
    principle-aligned)
  - .specify/extensions/agent-context/commands/speckit.agent-context.update.md ✅ no change

Deferred TODOs: none
-->

# Fantasy Gamebook Engine Constitution

## Core Principles

### I. Numbers Never in Prose (NON-NEGOTIABLE)

The AI narrator MUST NOT invent numbers or roll dice in prose. All randomness, state, and
combat math MUST go through MCP tools (`roll_dice`, `test_luck`, `update_character_sheet`,
`register_event`, and the combat tools). The harness only narrates and offers choices.
System commands such as `/hero`, `/backpack`, `/map`, and `/save` MUST reflect real MCP
state, never a narrated value.

**Rationale**: This is the rule that shapes the entire design. A solo gamebook is only
trustworthy if every number is engine-authoritative and reproducible; the moment the
narrator improvises a roll, state and story diverge and the engine becomes decoration.

### II. Dependency on Interfaces Only (The Golden Rule)

Dependency arrows MUST point only at contracts/interfaces, never at concrete
implementations. This preserves the three swap boundaries:

- `StorageBackend` — `JSONStorage` ↔ `PostgresStorage`
- `AdventureModule` — `SKILL.md` ↔ data record
- harness — Claude Code ↔ PydanticAI

`mcp` and `combat` MUST depend on the `StorageBackend` interface, never on `JSONStorage`.
An in-memory storage implementation MUST keep working for tests as proof that no module
reaches past the interface.

**Rationale**: The swap boundaries are the reason the architecture exists — Phase 2
(Postgres, web harness, data-driven adventures) reuses the same MCP contract unchanged.
Coupling to a concrete implementation silently destroys that.

### III. CONTRACTS.md is the Single Source of Truth

Every cross-module interface, the domain-model schema (`docs/CONTRACTS.md` §2), and the MCP
tool contract (§6) live in `docs/CONTRACTS.md`. Code MUST conform to the contract. Any
deviation MUST be a deliberate, documented update to `CONTRACTS.md` made in the same change —
never silent drift.

**Rationale**: A single authoritative English contract keeps the spec docs, the engine, and
the harness aligned. When code and contract disagree, the contract wins or is amended on
purpose; otherwise the system has no trustworthy description of itself.

### IV. Determinism and Isolated Testing

`rules` MUST be pure and the RNG MUST be injected. `rules` and `combat` MUST be testable in
full isolation — fixed-seed RNG, in-memory storage, no disk, no AI — and produce reproducible
results. The plugability audit (`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`)
MUST pass: no module may reach past an interface.

**Rationale**: Determinism makes failures reproducible and combat math verifiable, and the
audit mechanically enforces Principle II rather than trusting discipline alone.

### V. Domain Invariants and Atomic Persistence

Invariants (e.g. `0 <= current <= initial` for an `Attribute`) MUST live in `domain`, and
serialization MUST round-trip exactly (object → JSON → identical object). Every
`StorageBackend` implementation MUST write atomically (temp file + rename) and MUST NOT
corrupt state if the process dies mid-write.

**Rationale**: The domain is the base of the pyramid; centralizing invariants there keeps
every consumer honest. A gamebook persists a player's progress, so a half-written save is a
lost campaign — atomicity is non-negotiable.

## Additional Constraints

- **Dependencies**: managed via `uv`. Do not add dependencies without updating
  `docs/CONTRACTS.md` accordingly.
- **Language**: all identifiers — package names, types, fields, and MCP tools — MUST be in
  English per the mapping in `docs/CONTRACTS.md` §0.
- **MCP transport**: the MCP server uses the FastMCP high-level API over stdio.
- **Decision records**: technical decisions are recorded as ADRs (`docs/adrs/`) and
  Learning Lessons (`docs/learning-lessons/`), and indexed in `CLAUDE.md`.

## Development Workflow

- **Plugability gate (mandatory)**: the plugability audit
  (`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py`) MUST pass before merge.
- **Test suite**: the full suite (`uv run pytest -q`) MUST stay green before merge.
- **SDD review pipeline**: before merge, run `/sdd-qa` and `/sdd-security` in parallel,
  then `/sdd-tech` as the dispatching final review.
- **Contract-first changes**: when a change touches a cross-module interface, the MCP tool
  contract, or the domain schema, update `docs/CONTRACTS.md` in the same change (Principle III).

## Governance

This constitution supersedes other practices where they conflict. All pull requests and
reviews MUST verify compliance with the five core principles; any unavoidable violation MUST
be justified in the plan's Complexity Tracking section, with the simpler rejected alternative
named.

**Amendment procedure**: amendments are proposed as a change to this file, reviewed through
the standard SDD review pipeline, and recorded via the Sync Impact Report at the top of this
document. Amendments that change engine contracts MUST also update `docs/CONTRACTS.md`.

**Versioning policy** (semantic versioning of this document):

- **MAJOR**: backward-incompatible governance changes — removing or redefining a principle.
- **MINOR**: adding a new principle or section, or materially expanding guidance.
- **PATCH**: clarifications, wording, and non-semantic refinements.

**Compliance review**: the plugability audit and full test suite are the automated
compliance gates; the SDD review pipeline is the human/agent compliance gate. Runtime
development guidance lives in `CLAUDE.md` and `docs/CONTRACTS.md`.

**Version**: 1.0.0 | **Ratified**: 2026-06-26 | **Last Amended**: 2026-06-26
