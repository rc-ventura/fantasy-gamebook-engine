# Feature Specification: Web Backend MVP

**Feature Branch**: `003-web-backend-mvp`

**Created**: 2026-06-27

**Status**: Draft

**Epic**: `001-web-platform-migration` — second slice of the decomposed epic. Depends on
`002-persistence-foundation`. The browser UI is a separate feature, `005-professional-spa`, which
consumes this feature's documented API. See
[../001-web-platform-migration/spec.md](../001-web-platform-migration/spec.md) for the umbrella
vision and shared design artifacts.

**Input**: Decomposition slice of the Web Platform Migration epic. Scope: the **web backend** behind
the browser experience — a new agent-based narrator emitting a Pydantic-validated `Scene`, a FastAPI
HTTP API consuming the engine via the **unchanged MCP tool contract**, and the **documented,
authenticated API as a first-class, independently-usable surface** — with **every number
engine-authoritative**. Uses a dev/local auth stub and the durable Postgres backend from `002`; real
OIDC auth, accounts, session leases, production hardening, and observability are deferred to `004`.
The browser SPA is deferred to `005` and consumes this feature's API.

## Overview

Take the durable engine (now on Postgres from `002`) and put a **playable web backend** in front of
it: a new harness (PydanticAI, behind a `NarratorBackend` port) emits a structured `Scene` validated
by Pydantic v2 before it can reach storage or the UI; its `effects[]` reference engine operations, so
it is structurally prevented from fabricating numbers (Principle I). A FastAPI app exposes the full
play loop as a **documented, authenticated HTTP API** (OpenAPI auto-generated) that both the future
browser UI (`005`) and external clients consume — no privileged hidden path (FR-017). The MVP proof
is the **play loop driven entirely through the documented API** with a `FakeNarrator` (no browser,
no LLM required), plus the real PydanticAI narrator for live play.

This is the **backend MVP slice** of the epic and the second feature in its dependency chain
(`002` → `003` → `004` // `005`). Real authentication, per-account isolation at scale, session
leases, resume-across-devices, hardening, and observability come in `004`; the browser UI comes in
`005`. Here a dev auth stub scopes play to a single development account/campaign so the API is
exercisable end to end.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The play loop is drivable end to end through the documented API (Priority: P1)

A developer (or an automated client) drives the full gamebook loop — start/resume, explore, make
choices, resolve combat, reach end-states — entirely through the documented HTTP API, with every
roll, luck test, and stat change produced by the engine and reflected in the responses. No browser is
involved.

**Why this priority**: This is the backend heart of the product. The documented, playable API is the
contract the browser UI (`005`) and external clients will both consume; proving it works end to end
with a deterministic `FakeNarrator` is the smallest slice that validates the architecture (narrator
behind a port, engine via MCP, numbers engine-authoritative) without depending on an LLM or a UI.

**Independent Test**: Using only the documented API (OpenAPI at `/docs`) with a dev credential and a
deterministic `FakeNarrator`, create a character, advance the story through exploration, resolve a
combat, reach an end-state, and confirm every number in the responses traces to an engine action.

**Acceptance Scenarios**:

1. **Given** the API and no existing campaign, **When** a client creates a campaign and character,
   **Then** the engine rolls the stats (not the client) and the opening scene is returned.
2. **Given** a living campaign, **When** a client reopens it, **Then** the story resumes from the
   exact recorded point with no restart, re-roll, or contradiction of recorded facts.
3. **Given** a scene, **When** the client submits a numbered choice or free text, **Then** the next
   scene is returned and any dice/luck/stat effects are computed by the engine and visible in the
   response.
4. **Given** the client enters combat, **When** rounds resolve (with optional luck tests), **Then**
   outcomes are computed by the engine and the fight ends in a narrated result.
5. **Given** the client reaches a death or victory end-state, **When** it occurs, **Then** the run is
   archived and further turns are rejected.

---

### User Story 2 - The narrator is structurally prevented from inventing numbers (Priority: P1)

The agent-based narrator produces a `Scene` whose `effects[]` reference engine operations only; a
`Scene` carrying a literal number or an impossible effect is rejected before it can reach storage or
the player. This is the Principle I gate enforced at the harness boundary.

**Why this priority**: The defining rule of the product is that numbers are never invented. This
feature is where the narrator enters the system, so the structural gate must exist here — everything
downstream (`004`, `005`) depends on it.

**Independent Test**: Feed the narrator a path that would produce a `Scene` with a literal stat value
or an out-of-range effect; confirm it is rejected (`422 invalid_scene`) and never persisted; confirm
all numbers in accepted scenes trace to MCP tool results.

**Acceptance Scenarios**:

1. **Given** a narrator output carrying a literal stat/dice value, **When** it is validated, **Then**
   it is rejected (`422 invalid_scene`) and never persisted (FR-014).
2. **Given** a valid `Scene`, **When** its `effects[]` are applied, **Then** every numeric outcome
   comes from an MCP tool result, not from the narrator.
3. **Given** the `Scene.effects[]` type set, **When** it is compared to the MCP tool contract, **Then**
   they stay in lockstep (Principle III).

---

### User Story 3 - The web backend depends only on contracts (Priority: P2)

Adding the web backend does not break the project's golden rule: the web layer depends only on the
MCP tool contract and the HTTP API contract, never on concrete storage or engine internals. The
narrator sits behind a `NarratorBackend` port so it is testable without an LLM.

**Why this priority**: The plugability audit is a merge gate (Principle IV). The web layer must live
behind interfaces like every other module, or the architecture erodes — and `005`/`004` build on
this seam.

**Independent Test**: Run the plugability audit extended to cover `src/gamebook_web`; confirm no web
module imports a concrete storage implementation or engine internals, and that the `FakeNarrator`
drives the play loop without an LLM.

**Acceptance Scenarios**:

1. **Given** the web backend, **When** the plugability audit runs, **Then** `src/gamebook_web` depends
   only on the MCP tool contract and the HTTP API contract — no concrete storage or engine-internal
   imports.
2. **Given** the `NarratorBackend` port, **When** the `FakeNarrator` is injected, **Then** the full
   play loop runs deterministically without any LLM call (Principle IV).

---

### Edge Cases

- A narration step proposes an impossible effect (e.g. a stat outside its allowed range, or a literal
  number) — the `Scene` is rejected (`422 invalid_scene`) and never persisted or returned (FR-014).
- A client acts on an already-ended campaign — the system prevents continuing a finished run
  (`409 run_ended`).
- The narrator model returns malformed output — Pydantic validation rejects it before it reaches
  storage or the client; a safe retry/fallback is returned.
- A combat is abandoned mid-fight (the client stops calling rounds) — the combat state remains
  consistent and resumable (lease enforcement is `004`).
- The dev auth stub is configured for a campaign with no row yet — the engine behaves as on a fresh
  start, consistent with the JSON path on an empty `estado/`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose the full gamebook play loop — create/resume campaign, create
  character, take a turn, resolve combat, reach end-states — as a documented HTTP API (epic FR-001 /
  FR-015).
- **FR-002**: The narrator MUST NOT invent numbers or roll dice in prose; all randomness, luck tests,
  combat math, and state changes MUST be produced by the engine and reflected in API responses (epic
  FR-002, Principle I — enforced structurally via `Scene.effects[]` + an output validator).
- **FR-003**: On opening a session, the system MUST load the campaign's real game state before
  narrating, and MUST resume a living campaign from its exact recorded point (epic FR-003; backed by
  the durable store from `002`).
- **FR-004**: The API MUST accept a numbered choice index or free-text input per turn (epic FR-004).
- **FR-005**: The API MUST surface combat with optional luck tests and a clear final outcome (epic
  FR-005).
- **FR-006**: The API MUST handle death and victory end-states, archiving the run and rejecting
  further turns (epic FR-006).
- **FR-007**: The narrator↔engine exchange MUST be schema-validated (Pydantic v2 `Scene`); a
  structurally invalid `Scene` MUST be rejected (`422 invalid_scene`) before reaching storage or the
  client (epic FR-014).
- **FR-008**: The API MUST be documented (OpenAPI) such that a developer can discover every
  operation, input, and output without reading source (epic FR-016); the future UI and external
  clients MUST use this same surface — no privileged hidden path (epic FR-017).
- **FR-009**: The migration MUST reuse the existing engine rules, domain model, and tool contract
  unchanged in behavior; the adventure content MUST remain swappable (epic FR-018/019).
- **FR-010**: The web layer MUST depend only on the MCP tool contract and the HTTP API contract; no
  web module may import a concrete storage implementation or engine internals (Principle II; proven
  by the extended plugability audit).
- **FR-011**: The narrator MUST sit behind a `NarratorBackend` port with a deterministic
  `FakeNarrator`, so the play loop is testable without an LLM (Principle IV).
- **FR-012**: All values in API responses (stats, gold, inventory, dice/luck/combat outcomes) MUST
  reflect real engine state, never values fabricated by the narrator (epic FR-021, applied to the API
  surface).

### Key Entities *(include if feature involves data)*

- **Scene**: the structured unit the narrator produces for a turn — `{ narrative, choices[], effects[] }`
  — validated, not persisted as-is; per
  [../001-web-platform-migration/contracts/scene.md](../001-web-platform-migration/contracts/scene.md).
- **Engine domain entities** (unchanged): `CharacterSheet`, `World`, `Event`, `Combat`,
  `ArchiveRecord` — durable via `PostgresStorage` from `002`.
- **Campaign (minimal)**: the scoping unit; account ownership/session lease are deferred to `004`. A
  dev auth stub supplies a single development account/campaign context.
- **Adventure Module**: the swappable static lore (e.g. Ignarok) consumed by the narrator — unchanged
  (swap boundary #2).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer can complete a full play loop (create → explore → combat → end-state) using
  only the published OpenAPI documentation and a dev credential, with no browser and no source access
  (epic SC-007).
- **SC-002**: 100% of numbers in API responses originate from the engine — zero narrator-fabricated
  values — verified across a representative play-through audit (epic SC-003).
- **SC-003**: 100% of structurally invalid narrator→engine exchanges are rejected before persistence
  (no invalid state ever stored) (epic SC-008).
- **SC-004**: The plugability audit is green; no web module imports a concrete storage impl or engine
  internals; the `FakeNarrator` drives the full loop with no LLM call.
- **SC-005**: The `PydanticNarrator` (PydanticAI Agent, `output_type=Scene`, model
  `anthropic:claude-opus-4-8`) completes one full turn end-to-end — a real LLM call produces a
  `Scene` that passes Pydantic v2 validation, with every number in the response originating from
  an MCP tool result (no narrator-fabricated values). Verified manually against the running API.

## Assumptions

- **Depends on `002`**: the durable `PostgresStorage` backend exists; this feature does not re-build
  storage.
- **No browser UI here**: the SPA is a separate feature, `005-professional-spa`, which consumes this
  feature's documented API against a frozen OpenAPI contract. The MVP of this feature is the
  **playable documented API** (drivable via script with the `FakeNarrator`), not a browser experience.
- **Dev auth stub**: real OIDC, per-account isolation at scale, session leases, resume-across-devices,
  and privacy endpoints are deferred to `004`. The MVP uses a dev/local auth stub scoping play to a
  single development account/campaign so the API is exercisable end to end. The auth seam is designed
  so `004` swaps the stub for real OIDC without touching the play loop.
- **Technology** is decided in the epic's
  [research.md](../001-web-platform-migration/research.md) §2/§4: PydanticAI narrator (model
  `anthropic:claude-opus-4-8`, behind a `NarratorBackend` port) emitting a `Scene`; FastAPI + OpenAPI
  HTTP API. The frontend stack is decided in `005`, not here.
- **Engine + MCP tool contract unchanged**: the harness consumes the engine via `MCPToolset` over the
  existing FastMCP server; `Scene.effects[]` types stay in lockstep with the MCP tool contract
  (Principle III).
- **Adventure content**: the debut adventure module continues to provide the lore; no new adventure
  content is required beyond what already exists.
- **Availability best-effort**: no formal uptime SLA at this slice; integrity guarantees are
  unconditional (inherited from `002`).
