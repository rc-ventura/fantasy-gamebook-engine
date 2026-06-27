# Implementation Plan: Persistence Foundation (PostgresStorage)

**Branch**: `002-persistence-foundation` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-persistence-foundation/spec.md` (decomposition slice
of epic `001-web-platform-migration`).

## Summary

Swap the engine's storage backend from per-file JSON to PostgreSQL behind the existing
`StorageBackend` interface — **swap boundary #1** — with no engine behavior change. Implement
`PostgresStorage` (one transaction per state change, domain round-trip), add the Alembic migration
for the engine tables scoped to a minimal `campaign` row, and extend the storage contract suite to
run **through the consumer** (mcp/combat) against `JSONStorage`, in-memory, and `PostgresStorage`
(ADR-009), including an induced mid-write-failure no-corruption case. No web/UI/auth: shippable via
the Phase-1 MCP path with `DATABASE_URL` + `GAMEBOOK_CAMPAIGN_ID`.

This is the first feature in the epic's dependency chain (`002` → `003` → `004`). The shared design
artifacts (technology decisions, data model, Postgres mapping) live in the epic and are referenced,
not duplicated.

## Technical Context

**Language/Version**: Python 3.12 (existing engine).

**Primary Dependencies**:
- *Existing, unchanged*: `fastmcp`, `pydantic` v2, `uv`.
- *New (storage only)*: `sqlalchemy` 2.x Core + `asyncpg` (Postgres access behind `StorageBackend`),
  `alembic` (schema migrations). Web deps (`fastapi`, `pydantic-ai`, `opentelemetry-*`) are added in
  features `003`/`004`, not here.

**Storage**: PostgreSQL via a new `PostgresStorage(StorageBackend)`. `JSONStorage` and the in-memory
test backend remain for dev/test.

**Testing**: `pytest`; the existing plugability audit stays a merge gate and is confirmed against the
new module.

**Target Platform**: Linux server / local dev with Postgres; the engine remains runnable on stdio
via the Phase-1 MCP path.

**Project Type**: library (engine) — no web surface in this feature.

**Performance Goals**: N/A for this slice (concurrency/load targets belong to `004`); a single
campaign's writes commit in one transaction.

**Constraints**: numbers-never-in-prose is unaffected (no narrator here); atomic, non-corrupting
writes unconditionally (Principle V); modules depend only on `StorageBackend` (Principle II);
`docs/CONTRACTS.md` is the single source of truth for the new mapping (Principle III).

**Scale/Scope**: one durable backend behind an existing interface; minimal `campaign` scoping row
(account ownership deferred to `004`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Evaluated against `.specify/memory/constitution.md` v1.0.0:

| Principle | Status | How this plan complies |
|-----------|--------|------------------------|
| **I. Numbers Never in Prose** | PASS | No narrator in this feature; the engine's MCP tool contract is unchanged, so numbers remain engine-authoritative. |
| **II. Dependency on Interfaces Only** | PASS | This feature *is* the swap-boundary #1 proof: `PostgresStorage` sits behind `StorageBackend`; `mcp`/`combat` keep depending on the interface; the in-memory backend still works for tests. No module imports a concrete impl. |
| **III. CONTRACTS.md is the Single Source of Truth** | ACTION | The Postgres mapping (table/column layout, transaction semantics) MUST be folded into `docs/CONTRACTS.md` as it is implemented. No engine tool-contract change is permitted. |
| **IV. Determinism and Isolated Testing** | PASS | `rules`/`combat` stay pure and seed-deterministic; the plugability audit remains a merge gate and is confirmed to cover `storage/postgres.py`; the storage contract suite runs through the consumer across three backends. |
| **V. Domain Invariants and Atomic Persistence** | PASS | Invariants stay in `domain`; `PostgresStorage` writes inside one transaction per state change (all-or-nothing) and round-trips the domain schema. |

**Verdict**: No violations requiring Complexity Tracking justification. The only obligation is the
Principle III action item — fold the Postgres mapping into `docs/CONTRACTS.md`.

## Project Structure

### Documentation (this feature)

```text
specs/002-persistence-foundation/
├── spec.md
├── plan.md              # This file
├── tasks.md
└── checklists/
    └── requirements.md
```

Shared design artifacts live in the epic and are referenced (not duplicated):

- Technology decisions: [../001-web-platform-migration/research.md](../001-web-platform-migration/research.md) §1
- Data model + Postgres mapping: [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §A/§B (engine rows)
- Validation guide: [../001-web-platform-migration/quickstart.md](../001-web-platform-migration/quickstart.md) (storage sections)

### Source Code (repository root)

```text
src/gamebook/                 # EXISTING engine — behavior unchanged
├── domain/                   # unchanged
├── rules/                    # unchanged
├── combat/                   # unchanged
├── mcp/                      # unchanged
└── storage/
    ├── base.py               # StorageBackend interface — unchanged
    ├── json.py               # JSONStorage — unchanged
    ├── in_memory.py          # in-memory test backend — unchanged
    └── postgres.py           # NEW: PostgresStorage(StorageBackend) (swap boundary #1)

alembic/                      # NEW: migration framework wired to DATABASE_URL
└── versions/                 # NEW: engine tables + minimal campaign (account/session_lease deferred)

tests/
├── server/                   # storage + MCP — extended to run the contract suite vs PostgresStorage through the consumer
└── qa/                       # plugability audit — confirmed green with storage/postgres.py
```

**Structure Decision**: Keep `src/gamebook/` as the untouched engine, adding only
`storage/postgres.py` behind the existing interface. Add `alembic/` for migrations. No
`src/gamebook_web/`, no `frontend/` — those come in `003`/`004`. The dependency arrow still points
only at the `StorageBackend` interface (Principle II).

## Complexity Tracking

> No Constitution Check violations — this section is intentionally empty.

The single tracked obligation is documentation, not complexity: fold the Postgres mapping into
`docs/CONTRACTS.md` (Principle III).
