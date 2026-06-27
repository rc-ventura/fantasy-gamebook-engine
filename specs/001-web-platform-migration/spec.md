# Feature Specification: Web Platform Migration

**Feature Branch**: `001-web-platform-migration`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "Following the project roadmap, the terminal experience already works
perfectly. Now it is time to migrate to a web system: authentication as a separate service, add
persistence, a separate professional UI, a new harness (deep agents), validate schemas with
Pydantic, build a production-ready system, build observability, and expose the application as an API."

## Overview

The solo-play gamebook engine currently runs as a terminal experience (Claude Code as the
narrator over an MCP server, JSON file storage, adventure encoded as a skill). This feature is the
Phase-2 migration: take that same engine — unchanged at its core — and make it a production-ready
web product that anyone can play in a browser with their own account, while exposing the engine as
a documented API for programmatic use. The defining rule of the product is preserved end to end:
**the narrator never invents numbers; all dice, luck tests, combat math, and state changes remain
engine-authoritative.**

## Clarifications

### Session 2026-06-26

- Q: What happens to the existing terminal / Claude Code harness once the web app ships? → A: Kept
  for development and testing only; the new web agent harness is the sole production narrator.
- Q: When the same campaign is opened in two tabs/devices at once, how should conflicting writes be
  handled? → A: Single active play session per campaign; additional sessions are read-only until they
  explicitly take over.
- Q: What privacy/compliance posture must the production system meet for player account data? → A:
  Deferred to planning (`/speckit-plan`); no spec-level commitment yet.
- Q: What availability/uptime target should the production service commit to? → A: Best-effort at
  initial launch; no formal uptime SLA.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Play the gamebook in a web browser (Priority: P1)

A player opens the web application, starts a new adventure (or resumes one in progress), reads the
narration in a polished interface, and advances the story by selecting a numbered choice or typing
free text. Combat, luck tests, and stat changes resolve through the engine and are reflected on
screen. The player never sees a number the engine did not produce.

**Why this priority**: This is the heart of the product. Without the core play loop rendered in a
real web UI, nothing else matters. It is the minimum viable slice that delivers a playable web game.

**Independent Test**: Load the web app as a guest or seeded player, play from the opening scene
through at least one exploration turn and one combat encounter to a clean end-state (victory or
death), and confirm every number shown traces back to an engine action (no narrator-invented values).

**Acceptance Scenarios**:

1. **Given** a player with no character, **When** they open the app, **Then** they are offered to
   create a character and begin the adventure's opening scene.
2. **Given** a player with a living character, **When** they open the app, **Then** the story
   resumes from the exact recorded point with no restart, re-roll, or contradiction of recorded facts.
3. **Given** the player is presented a scene, **When** they select a numbered choice, **Then** the
   next scene is rendered and any dice/luck/stat effects are computed by the engine and shown.
4. **Given** the player enters combat, **When** rounds resolve, **Then** outcomes are computed by the
   engine, optional luck tests are offered, and the fight ends in a result the narrator describes.
5. **Given** the player reaches a death or victory end-state, **When** it occurs, **Then** the app
   shows the appropriate ending and the run is archived.

---

### User Story 2 - Account, sign-in, and progress that follows me (Priority: P1)

A player creates an account (or signs in) through a dedicated authentication service, and their
character, world state, events, and history are durably saved to that account. They can close the
browser, return later or from another device, sign in, and resume exactly where they left off.

**Why this priority**: A web product needs identity and durable, per-user persistence to be more
than a demo. Saved progress tied to an account is what makes the experience real and shareable.

**Independent Test**: Create an account, play several turns, sign out, sign back in on a different
session/device, and confirm the campaign resumes at the exact recorded point with all stats and
inventory intact.

**Acceptance Scenarios**:

1. **Given** a new visitor, **When** they sign up via the authentication service, **Then** an
   account is created and they can start their own private campaign.
2. **Given** a returning player, **When** they sign in, **Then** they see only their own
   character(s) and history, never another player's.
3. **Given** a signed-in player mid-campaign, **When** the session ends unexpectedly, **Then** no
   committed progress is lost and the next sign-in resumes from the last consistent state.
4. **Given** an unauthenticated request for a player's game data, **When** it is made, **Then** it
   is rejected.

---

### User Story 3 - A reliable, production-grade service (Priority: P2)

Players experience a service that stays available, handles many concurrent campaigns, and never
corrupts a save — even under failure. Operators can trust that a crash mid-turn does not lose or
mangle a player's progress, and that invalid data never reaches the player.

**Why this priority**: Production readiness — durable persistence, data integrity, and graceful
failure handling — is what separates a hosted product from the terminal prototype. It protects the
P1 experiences once real players depend on them.

**Independent Test**: Run the system under concurrent simulated players, inject a mid-write failure
during a state change, and confirm no save is corrupted and the affected campaign resumes at the
last consistent state; confirm malformed engine/narrator exchanges are rejected rather than persisted.

**Acceptance Scenarios**:

1. **Given** many concurrent campaigns, **When** they play simultaneously, **Then** each player's
   state remains isolated and consistent.
2. **Given** a process failure during a state change, **When** the system recovers, **Then** the
   save is either fully applied or not applied — never partially written.
3. **Given** a narration step that would produce structurally invalid data, **When** it is
   validated, **Then** it is rejected before it can reach storage or the player.
4. **Given** a domain invariant (e.g. current attribute within its bounds), **When** any update is
   attempted, **Then** violations are prevented.

---

### User Story 4 - Programmatic access via a documented API (Priority: P3)

A developer (or an alternative front-end / automation) drives the gamebook engine through a
documented, authenticated API: read game state, take a turn, resolve combat, and manage saves —
the same capabilities the web UI uses — without going through the browser.

**Why this priority**: Exposing the engine as an API is an explicit goal and the foundation that
lets the professional UI (and future clients) be just one consumer. Valuable, but the web UI play
loop and accounts come first.

**Independent Test**: Using only the documented API with valid credentials, create a character,
advance the story, resolve a combat, and read back consistent state — with no browser involved.

**Acceptance Scenarios**:

1. **Given** valid credentials, **When** a client calls the documented API, **Then** it can perform
   the full play loop (read state, take turn, resolve combat, save/resume).
2. **Given** the API, **When** a developer consults its documentation, **Then** every operation,
   its inputs, and its outputs are described.
3. **Given** an API call with missing or invalid credentials, **When** it is made, **Then** it is
   rejected consistently with the web app's auth rules.

---

### User Story 5 - Operators can observe and operate the system (Priority: P3)

Operators can see the health of the running system: request volume, error rates, latency, and basic
play metrics, plus traces/logs that let them diagnose a failing campaign without inspecting raw data
by hand.

**Why this priority**: Observability is required to run the service responsibly in production, but it
supports the experience rather than being the experience itself.

**Independent Test**: Trigger a representative error and a slow operation, then confirm both surface
in the operator's monitoring (logs/metrics/traces) with enough context to locate the cause.

**Acceptance Scenarios**:

1. **Given** the service is running, **When** an operator checks monitoring, **Then** health, error
   rate, and latency are visible.
2. **Given** an error occurs during a player's turn, **When** the operator investigates, **Then**
   they can trace the failing request without exposing it to the player as a broken state.

---

### Edge Cases

- A player resumes a campaign whose adventure content has changed since they last played — recorded
  facts must still be honored and the resume must not contradict them.
- Two browser tabs or devices open the same campaign at once — the system enforces a single active
  play session per campaign; additional sessions are read-only until they explicitly take over, so
  concurrent edits cannot corrupt or silently overwrite state.
- A player abandons a turn mid-combat (closes the tab) — the fight must resume in a consistent state.
- Authentication service is temporarily unavailable — players already signed in and unauthenticated
  visitors each get a clear, safe outcome rather than data loss.
- A narration step proposes an impossible effect (e.g. a stat outside its allowed range) — it is
  rejected and surfaced safely, never persisted.
- A player triggers an end-state (death/victory) and then attempts another action — the system
  prevents continuing a finished run.

## Requirements *(mandatory)*

### Functional Requirements

**Core play loop (web)**

- **FR-001**: The system MUST let a player play the full gamebook loop — start/resume, explore,
  make choices, resolve combat, reach end-states — through a web interface.
- **FR-002**: The narrator MUST NOT invent numbers or roll dice in prose; all randomness, luck
  tests, combat math, and state changes MUST be produced by the engine and reflected in the UI.
- **FR-003**: On opening a session, the system MUST load the player's real game state before
  narrating, and MUST resume a living campaign from its exact recorded point (no restart, no re-roll,
  no contradiction of recorded facts).
- **FR-004**: The system MUST present each turn as narration plus a set of selectable choices, and
  MUST accept free-text player input in addition to the offered choices.
- **FR-005**: The system MUST surface combat encounters with optional luck tests and a clear final
  outcome narrated to the player.
- **FR-006**: The system MUST handle death and victory end-states, archiving the run appropriately.

**Identity & accounts**

- **FR-007**: Authentication MUST be provided by a dedicated service separate from the game engine,
  so that identity concerns are decoupled from gameplay.
- **FR-008**: Players MUST be able to sign up and sign in, and the system MUST associate each
  campaign and its history with the owning account.
- **FR-009**: The system MUST ensure a player can access only their own campaigns, characters, and
  history.
- **FR-010**: All game-data and engine operations MUST require authentication; unauthenticated
  requests MUST be rejected.

**Durable persistence & integrity**

- **FR-011**: The system MUST durably persist each player's character, world state, events, and
  archive so progress survives across sessions and devices.
- **FR-012**: State writes MUST be atomic and consistent — a failure mid-write MUST NOT corrupt a
  save; the change is either fully applied or not applied.
- **FR-013**: Domain invariants MUST be enforced on every state change (e.g. a current attribute
  stays within its defined bounds), and stored data MUST round-trip without loss.
- **FR-014**: Data exchanged between the narrator and the engine MUST be schema-validated, so that
  structurally invalid data is rejected before reaching storage or the player.

**Concurrency & sessions**

- **FR-025**: The system MUST enforce a single active play session per campaign. When a second
  session opens the same campaign, it MUST be read-only until it explicitly takes over the campaign,
  at which point the previous session MUST become read-only — so concurrent writes to one campaign
  cannot corrupt or silently overwrite state.

**API exposure**

- **FR-015**: The system MUST expose the engine's capabilities (read state, take a turn, resolve
  combat, save/resume, manage characters) as a documented, authenticated API.
- **FR-016**: The API MUST be documented such that a developer can discover every operation, its
  inputs, and its outputs without reading the source.
- **FR-017**: The web UI MUST be a consumer of the same API surface (no privileged hidden path),
  so the UI and external clients share one consistent contract.

**Engine & contract preservation**

- **FR-018**: The migration MUST reuse the existing engine rules, domain model, and tool contract
  unchanged in behavior; swapping storage, harness, or front-end MUST NOT change game outcomes.
- **FR-019**: The adventure content MUST remain swappable without changing the engine, preserving
  the project's existing swap boundaries.

**Professional UI**

- **FR-020**: The player-facing UI MUST be a distinct, professional front-end (separate from the
  engine) that renders narration, choices, character sheet, inventory, map, and combat state.
- **FR-021**: All values shown in the UI (stats, gold, inventory, dice/luck/combat outcomes) MUST
  reflect real engine state, never values fabricated by the front-end or narrator.

**Observability & production readiness**

- **FR-022**: The system MUST emit operational telemetry — at minimum health, error rate, latency,
  and basic play metrics — observable by operators.
- **FR-023**: The system MUST produce diagnostic logs/traces sufficient to locate the cause of a
  failed player turn without exposing internal failure as corrupted game state to the player.
- **FR-024**: The system MUST degrade gracefully when a dependency (e.g. the authentication service)
  is unavailable, giving players a clear, safe outcome rather than data loss.

### Key Entities *(include if feature involves data)*

- **Account / Player Identity**: A registered user managed by the separate authentication service;
  owns campaigns and is the unit of access control. Distinct from the in-game character.
- **Character Sheet**: The hero's stats (skill/stamina/luck with initial/current), gold, provisions,
  inventory, and conditions. Engine-authoritative.
- **World State**: Current location, visited locations, and world flags driving progression.
- **Event / History**: The recorded hard facts of a campaign (decisions, outcomes) used to resume
  and to keep narration consistent.
- **Combat**: The transient state of a fight (participants, rounds, outcome) resolved by the engine.
- **Archive Record**: A finished run (death or victory) preserved for the graveyard/hall of fame.
- **Scene**: The structured unit the narrator produces for a turn — narration, available choices,
  and the engine effects to apply — that the UI renders and that is schema-validated.
- **Adventure Module**: The swappable static lore (zones, bestiary, victory condition) consumed by
  the narrator, independent of the engine.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new player can go from landing on the site to making their first in-game choice in
  under 3 minutes, including account creation.
- **SC-002**: A returning player can sign in and resume their exact campaign state in under 30
  seconds, with 100% of stats, inventory, and recorded facts intact.
- **SC-003**: 100% of numbers shown to players originate from the engine — zero narrator- or
  UI-fabricated values — verified across a representative play-through audit.
- **SC-004**: Zero save corruption under induced mid-write failures across a defined stress test;
  every affected campaign resumes at the last consistent state.
- **SC-005**: The system sustains a defined concurrent-campaign load (target: at least 1,000
  concurrent active campaigns) without players experiencing data loss or cross-account leakage.
- **SC-006**: 95% of player turns are reflected in the UI within 2 seconds under normal load.
- **SC-007**: A developer can complete a full play loop using only the published API documentation,
  with no access to source code.
- **SC-008**: 100% of structurally invalid narrator→engine exchanges are rejected before persistence
  (no invalid state ever stored).
- **SC-009**: Operators can detect and locate the cause of an induced failure using only telemetry
  and logs/traces, within a defined response time.

## Assumptions

- **Solo-play preserved**: The web product remains single-player per campaign; no real-time
  multiplayer is in scope. Each campaign belongs to one account.
- **Engine reuse, not rewrite**: The existing rules, domain model, and MCP tool contract are reused
  unchanged; this feature swaps the storage backend, the narrator/harness, and the front-end across
  the project's existing swap boundaries (storage, harness, adventure module).
- **Authentication standard**: Identity uses a standard, widely-supported authentication approach
  (e.g. OAuth2/OIDC-style) provided by a dedicated, separately-deployable service. The specific
  provider/implementation is a planning decision.
- **Public, self-service web app**: Visitors can self-register; the product is a hosted web
  application rather than a private/internal tool. Abuse-prevention basics (rate limiting) are assumed.
- **Persistence backend**: Durable persistence replaces per-file JSON storage with a
  production-grade datastore behind the existing storage interface; the exact technology is a
  planning decision, but the schema maps cleanly to relational tables (per existing design intent).
- **New harness as primary narrator**: A new agent-based harness with structured, schema-validated
  scene output becomes the production narrator for the web app. The terminal/Claude Code harness is
  retained for development and testing only and is not the production play path.
- **Existing terminal saves**: Local development saves from the terminal phase are not required to be
  migrated into the production datastore; production starts from clean per-account data. Import is a
  possible later enhancement, not in scope here.
- **Adventure content**: The debut adventure module continues to provide the lore; no new adventure
  content is required for this migration beyond what already exists.
- **Standard expectations**: Industry-standard data retention, error handling (user-friendly messages
  with safe fallbacks), and security practices apply unless specified otherwise.
- **Privacy/compliance posture deferred**: The formal privacy/compliance posture for account data
  (e.g. data export, account deletion/erasure, PII minimization) is intentionally not committed at
  the spec level and will be decided during planning. Basic security (authenticated access, isolation
  per account) still applies.
- **Availability is best-effort at launch**: The initial production launch carries no formal uptime
  SLA; availability is best-effort. Data-integrity guarantees (atomic, non-corrupting writes) are
  unconditional and independent of this — a relaxed availability target never permits a corrupted save.
