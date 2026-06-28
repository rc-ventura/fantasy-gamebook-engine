# ADR-016: Mock mode via a client-side fixture layer (VITE_USE_MOCK=true)

**Status**: Accepted | **Date**: 2026-06-27 | **Branch**: `feat/005-spa`

## Context

Slice 005 (the SPA) depends on slice 003 (the FastAPI backend) for all game state. Slice 003 was not yet live during development of 005. The task list requires the full play loop to be testable without a running backend (Principle IV — deterministic, isolated testing).

Options considered:
1. **MSW (Mock Service Worker)**: intercepts fetch at the network level, full HTTP fidelity
2. **Per-test mock functions**: `vi.mock()` in tests — isolated but requires wiring in every test
3. **Client-side fixture layer** (chosen): a `src/api/mock.ts` module with deterministic fixture responses, activated by `VITE_USE_MOCK=true`
4. **JSON fixture files**: static files read by tests

## Decision

A dedicated `src/api/mock.ts` module implements all API functions as deterministic fixtures. The `src/api/client.ts` module checks `import.meta.env.VITE_USE_MOCK` at the top of each function and dispatches to mock handlers when true.

**Mock state machine**: the mock tracks play progression through a `MockStage` type (`no_character | opening | exploring | in_combat | ended`) stored in `sessionStorage`. This gives the mock "memory" across component re-renders without persisting across browser sessions.

**Numbers-never-fabricated in mock**: mock fixtures contain realistic engine values (skill 10, stamina 20, attack strengths from skill + 2d6 logic) that represent what the real engine would produce. The audit tests (`tests/unit/audit/no-fabricated-values.test.ts`) verify that all mock values are within the engine's valid ranges.

## Consequences

**Positive**:
- Full play loop is exercisable without a backend (T002, SC-004)
- Vitest unit tests run in full isolation — no network, no server
- Playwright E2E tests work immediately (before slice 003 ships)
- Mock values are pre-audited to be engine-realistic (not random fabrications)
- The seam (`VITE_USE_MOCK`) makes it trivially easy to switch to the real backend

**Negative**:
- The mock must be kept in sync with the real API contract (minor maintenance overhead)
- Mock state machine is simplistic; it doesn't model all possible game states
- When slice 003 ships, integration tests should be added targeting the real backend

## When to retire

The mock layer is **not retired** after 003 ships — it remains as a development tool and test fixture. Integration tests (`tests/e2e/`) will add coverage against the live 003 API alongside the mock-mode tests.
