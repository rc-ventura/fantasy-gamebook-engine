# Feature Specification: Persistence Foundation (PostgresStorage)

**Feature Branch**: `002-persistence-foundation`

**Created**: 2026-06-27

**Status**: Draft

**Epic**: `001-web-platform-migration` — this is the first slice of the decomposed epic. See
[../001-web-platform-migration/spec.md](../001-web-platform-migration/spec.md) for the umbrella
vision and the shared design artifacts (research, data model, contracts, quickstart).

**Input**: Decomposition slice of the Web Platform Migration epic. Scope: swap the engine's storage
backend from per-file JSON to PostgreSQL **behind the existing `StorageBackend` interface** — swap
boundary #1 — with no engine behavior change, durable atomic writes, and the storage contract suite
proven **through the consumer**. No web/UI/auth in this feature; it is shippable on its own via the
Phase-1 MCP path with `DATABASE_URL` + `GAMEBOOK_CAMPAIGN_ID`.

## Overview

The engine today persists one file per entity in `estado/` (`JSONStorage`). This feature replaces
that with a production-grade datastore — PostgreSQL — implemented as a new `PostgresStorage` that
satisfies the **same `StorageBackend` interface** the engine already depends on. No other module
changes: `rules`, `combat`, `domain`, and `mcp` are untouched in behavior. Postgres transactions
give the Principle V atomicity guarantee for free (the relational analogue of temp-file + rename),
and the existing in-memory and JSON backends remain for dev/test. The proof is the existing storage
contract suite, now run **through the consumer** (mcp/combat) against all three backends
(ADR-009), including an induced mid-write-failure no-corruption case.

This is the foundation of the epic's dependency chain (`002` → `003` → `004`): it gives the web
layer a durable backend to build on without coupling to it. Account ownership, session leases, the
web API, harness, and UI are explicitly out of scope here.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The engine runs on durable storage with no behavior change (Priority: P1)

The gamebook engine is run against PostgreSQL instead of JSON files. Every play action — character
creation, exploration, luck tests, combat, end-states — behaves identically and survives a process
restart, because the new backend sits behind the same interface the engine already uses.

**Why this priority**: This is swap boundary #1 in isolation. Without a durable, behavior-identical
backend, no later web feature can be trusted. It is the smallest slice that proves the architecture's
central promise: swap a backend without touching the engine.

**Independent Test**: Run the existing storage + MCP suite through the consumer against
`JSONStorage`, the in-memory backend, **and** `PostgresStorage`, and confirm identical outcomes
(ADR-009). Then run the engine via the Phase-1 MCP path with `DATABASE_URL` +
`GAMEBOOK_CAMPAIGN_ID`, play several turns, restart the process, and confirm the campaign resumes at
the exact recorded state.

**Acceptance Scenarios**:

1. **Given** the engine configured with a Postgres `DATABASE_URL` and a `GAMEBOOK_CAMPAIGN_ID`,
   **When** it plays a full loop (create → explore → combat → end-state), **Then** every outcome is
   identical to the same loop run against `JSONStorage`.
2. **Given** a campaign persisted to Postgres, **When** the process is restarted and the same
   campaign is reopened, **Then** character, world, events, and combat state resume with no loss or
   contradiction.
3. **Given** the storage contract suite, **When** it is run through the consumer (mcp/combat) against
   all three backends, **Then** it passes for all three with no engine change.

---

### User Story 2 - A save survives a mid-write failure uncorrupted (Priority: P2)

An operator kills the process (or the DB connection drops) in the middle of a state-changing write.
On recovery, the affected campaign's save is either fully applied or not applied at all — never
partially written — and play resumes from the last consistent state.

**Why this priority**: Unconditional, non-corrupting writes (Principle V) are what separate a hosted
product from the prototype. It protects the P1 experience once real players depend on it.

**Independent Test**: Induce a failure mid-transaction during a state change and confirm the save is
not partially applied; the campaign resumes at the last consistent state (epic SC-004, single-write
case).

**Acceptance Scenarios**:

1. **Given** a state-changing operation in progress, **When** a failure occurs mid-write, **Then**
   the transaction rolls back fully — no partial save reaches storage.
2. **Given** such a failed write, **When** the campaign is reopened, **Then** it resumes at the last
   consistent state with no corruption.
3. **Given** any persisted entity, **When** it is read back, **Then** it round-trips identically
   (object → DB → object), with domain invariants intact.

---

### User Story 3 - The engine stays plugable with the new backend (Priority: P2)

Adding a Postgres backend does not break the project's golden rule: modules depend only on
interfaces, never on concrete implementations. No module reaches past `StorageBackend`.

**Why this priority**: The plugability audit is a merge gate (Principle IV). The new `postgres.py`
module must live behind the interface like every other backend, or the architecture erodes.

**Independent Test**: Run the plugability audit (`tests/qa/test_dependencies.py`,
`tests/qa/test_isolation.py`) extended to cover the new storage module, and confirm no module imports
a concrete storage implementation.

**Acceptance Scenarios**:

1. **Given** the new `PostgresStorage`, **When** the plugability audit runs, **Then** `mcp` and
   `combat` depend on the `StorageBackend` interface, not on `PostgresStorage` or `JSONStorage`.
2. **Given** the in-memory test backend, **When** the full engine suite runs, **Then** it still
   passes — proving the engine never depended on the concrete backend.

---

### Edge Cases

- The DB connection drops mid-transaction — the write rolls back; the next operation opens a fresh
  connection and succeeds.
- A `GAMEBOOK_CAMPAIGN_ID` is supplied for a campaign with no row yet — the engine behaves as on a
  fresh start (no existing state), consistent with the JSON path on an empty `estado/`.
- A migration is applied to a non-empty database — Alembic migrations are additive and safe to apply
  in order; existing data is preserved.
- A domain object with maximum field lengths is stored and read back — round-trips without loss
  (Principle V).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a `PostgresStorage` implementation of the existing
  `StorageBackend` interface, scoped to a campaign, with **no change to any other engine module**.
- **FR-002**: The migration MUST reuse the existing engine rules, domain model, and tool contract
  unchanged in behavior; swapping storage MUST NOT change game outcomes (epic FR-018).
- **FR-003**: The system MUST durably persist each campaign's `CharacterSheet`, `World`, `Event`,
  `Combat`, and `ArchiveRecord` to PostgreSQL so progress survives process restarts (epic FR-011).
- **FR-004**: State writes MUST be atomic — one transaction per state change, all-or-nothing — so a
  failure mid-write MUST NOT corrupt a save (epic FR-012, Principle V).
- **FR-005**: Domain invariants MUST be enforced on every state change, and stored data MUST
  round-trip without loss (epic FR-013).
- **FR-006**: The storage contract MUST be provable **through the consumer** (mcp/combat) across
  `JSONStorage`, the in-memory backend, and `PostgresStorage` (ADR-009).
- **FR-007**: The engine's plugability audit MUST stay green with the new storage module; no module
  may import a concrete storage implementation (Principle IV, merge gate).
- **FR-008**: The Postgres schema mapping MUST be folded into `docs/CONTRACTS.md` (Principle III),
  since it is a new cross-module contract.

### Key Entities *(include if feature involves data)*

- **Engine domain entities** (unchanged): `CharacterSheet`, `World`, `Event`, `Combat`,
  `ArchiveRecord` — authoritative in `docs/CONTRACTS.md` §2; shapes per
  [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §A.
- **Campaign (minimal)**: the scoping unit for engine tables (`id`, `status`, `created_at`).
  Account ownership is added in feature `004`; here it is a bare scoping row so `PostgresStorage`
  can be exercised in isolation.
- **Postgres mapping**: engine tables scoped to `campaign_id`, one transaction per state change —
  per [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §B
  (engine rows only; `account`/`session_lease` are deferred to `004`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The storage contract suite passes **through the consumer** for `JSONStorage`, the
  in-memory backend, and `PostgresStorage` with identical results.
- **SC-002**: Zero save corruption under an induced mid-write failure (single-write case; epic
  SC-004).
- **SC-003**: 100% of persisted domain objects round-trip identically (object → DB → object), with
  invariants intact.
- **SC-004**: The plugability audit is green; no engine module imports a concrete storage impl.

## Assumptions

- **Scope boundary**: account ownership, session leases, the web API, the new harness, and the UI are
  OUT of scope (features `003` and `004`). `PostgresStorage` is scoped to a `campaign_id` supplied at
  construction — the Phase-2 MCP path (`DATABASE_URL` + `GAMEBOOK_CAMPAIGN_ID`).
- **Migrations are additive**: Alembic creates the engine tables + a minimal `campaign` row here;
  feature `004` adds `account`, `campaign.account_id`, and `session_lease` in later migrations.
- **Technology** is decided in the epic's
  [research.md §1](../001-web-platform-migration/research.md): PostgreSQL + SQLAlchemy 2.x Core +
  `asyncpg` + Alembic, behind `StorageBackend`.
- **No terminal-save migration**: production starts from clean per-campaign data; importing existing
  JSON saves is not required (epic assumption).
- **Best-effort availability, unconditional integrity**: a relaxed availability target never permits
  a corrupted save (epic clarification).
