# Feature Specification: Accounts, Hardening & Observability

**Feature Branch**: `004-accounts-hardening-obs`

**Created**: 2026-06-27

**Status**: Draft

**Epic**: `001-web-platform-migration` — third slice of the decomposed epic. Depends on
`002-persistence-foundation` and `003-web-backend-mvp`. The browser SPA is a separate feature,
`005-professional-spa`, which consumes `003`'s documented API; sign-up/sign-in UI belongs to `005`.
See [../001-web-platform-migration/spec.md](../001-web-platform-migration/spec.md) for the umbrella
vision and shared design artifacts (research, data model, contracts, quickstart).

**Input**: Decomposition slice of the Web Platform Migration epic. Scope: the **accounts,
production-hardening, and observability** that sit behind the browser experience — real
authentication (replacing `003`'s dev auth stub), account ownership and per-account isolation at
scale, session-lease concurrency control, save/resume that follows a player across devices, privacy
(export/erasure) endpoints, atomic-write hardening under concurrency, graceful degradation, ended-run
guarding, and operator observability. The documented API from `003` is extended, not rebuilt; US4
(documented API) is already delivered in `003`. No browser/UI in this feature — `004` is backend only.

## Overview

Take the playable web backend from `003` (which runs on the durable `PostgresStorage` from `002`,
behind a dev auth stub scoping play to one development account) and harden it into a
production-grade, multi-account, observable service. Replace the dev auth stub with real
authentication from a dedicated service: validate bearer tokens, resolve the account from the token
subject, and scope every read and write to that account. Add account ownership and the session lease
that enforces a single active play session per campaign, gate state-changing routes on the lease, and
add save/resume so a player's progress follows them across sessions and devices. Add privacy
endpoints that export and cascade-delete a player's game data. Harden the atomic-write boundary in
`PostgresStorage` for the concurrency and multi-account setting, prove isolation with no
cross-account leakage, and degrade gracefully when the authentication service is unavailable. Guard
against acting on an ended run and honor recorded facts when adventure content has changed. Finally,
instrument the service with operational telemetry and per-request traces so operators can observe
health, error rate, latency, and basic play metrics, and locate a failing turn without exposing
internal failure as corrupted game state to the player.

This is the **accounts, hardening & observability slice** of the epic and the third feature in its
dependency chain (`002` → `003` → `004` // `005`). The engine rules, domain model, and MCP tool
contract stay behavior-unchanged; `004` adds ownership, concurrency control, integrity guarantees,
and observability *around* them. The browser SPA (`005`) consumes `003`'s documented API and the
account/session/privacy endpoints added here; the sign-up/sign-in UI is explicitly `005`'s concern —
`004` delivers the backend auth, accounts, hardening, and observability it depends on.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Account, sign-in, and progress that follows me (Priority: P1)

A player is authenticated by a dedicated service separate from the engine, and their character,
world state, events, and history are durably saved to that account. They can close the browser,
return later or from another device, sign in, and resume exactly where they left off. They can see
only their own campaigns and history, never another player's, and can export or permanently delete
their data.

**Why this priority**: A web product needs real identity and durable, per-user persistence to be more
than a demo. Saved progress tied to an account — resumable across devices, isolated per player, and
privacy-controllable — is what makes the experience real and shareable. It is the smallest slice that
turns `003`'s single-account MVP into a multi-account product.

**Independent Test**: Using the documented API with a real authenticated token, create an account
(via first authenticated access), play several turns, end the session, re-authenticate on a different
session/device, and confirm the campaign resumes at the exact recorded point with all stats and
inventory intact — while a second account's data is never visible and a concurrent second session on
the same campaign is read-only until takeover.

**Acceptance Scenarios**:

1. **Given** a new visitor's first authenticated request, **When** the token is validated, **Then** an
   account is created from the token subject and they can start their own private campaign.
2. **Given** a returning player, **When** they sign in, **Then** they see only their own campaigns and
   history, never another player's.
3. **Given** a signed-in player mid-campaign, **When** the session ends unexpectedly, **Then** no
   committed progress is lost and the next sign-in resumes from the last consistent state.
4. **Given** an unauthenticated request for a player's game data, **When** it is made, **Then** it is
   rejected.
5. **Given** two browser tabs/devices open the same campaign, **When** the second opens it, **Then**
   it is read-only until it explicitly takes over, at which point the first becomes read-only — so
   concurrent edits cannot corrupt or silently overwrite state.
6. **Given** a player who requests their data, **When** they export it, **Then** they receive their
   complete game data portably; and **When** they delete their account, **Then** all their campaigns
   and engine rows are removed.

---

### User Story 2 - A reliable, production-grade service (Priority: P2)

Players experience a service that stays available, handles many concurrent campaigns, and never
corrupts a save — even under failure. Operators can trust that a crash mid-turn does not lose or
mangle a player's progress, that concurrent campaigns stay isolated with no cross-account leakage,
that invalid data never reaches the player, and that the service degrades safely when a dependency is
unavailable.

**Why this priority**: Production readiness — durable persistence, data integrity under concurrency,
graceful failure handling, and ended-run guarding — is what separates a hosted product from the
backend prototype. It protects the P1 experience once real, concurrent players depend on it.

**Independent Test**: Run the system under concurrent simulated accounts, inject a mid-write failure
during a state change, and confirm no save is corrupted and the affected campaign resumes at the last
consistent state; confirm concurrent campaigns stay isolated with no cross-account leakage; confirm
the service degrades safely when the authentication service is down; and confirm acting on an ended
run is rejected.

**Acceptance Scenarios**:

1. **Given** many concurrent campaigns across many accounts, **When** they play simultaneously,
   **Then** each player's state remains isolated and consistent with no cross-account leakage.
2. **Given** a process failure during a state change under concurrency, **When** the system recovers,
   **Then** the save is either fully applied or not applied — never partially written.
3. **Given** the authentication service is unavailable, **When** already-signed-in players continue,
   **Then** they remain read-only until their token expires with no data loss; and **When** new
   sign-ins are attempted, **Then** they are rejected with a clear, safe outcome.
4. **Given** a run that has reached an end-state, **When** a further action is attempted, **Then** it
   is rejected and the finished run cannot be continued.
5. **Given** a campaign whose adventure content has changed since it was last played, **When** it is
   resumed, **Then** recorded facts are still honored and the resume does not contradict them.

---

### User Story 3 - Operators can observe and operate the system (Priority: P3)

Operators can see the health of the running system: request volume, error rates, latency, and basic
play metrics, plus traces/logs that let them diagnose a failing campaign without inspecting raw data
by hand.

**Why this priority**: Observability is required to run the service responsibly in production, but it
supports the experience rather than being the experience itself.

**Independent Test**: Trigger a representative error and a slow operation, then confirm both surface
in the operator's monitoring (logs/metrics/traces) with enough context to locate the cause — and that
a failing turn is traced without exposing internal failure as corrupted game state to the player.

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
- A player abandons a turn mid-combat (closes the tab) — the fight must resume in a consistent state;
  the session lease keeps the prior session writable until it expires or is taken over.
- Authentication service is temporarily unavailable — already-signed-in players continue read-only
  until their token expires, and new sign-ins get a clear, safe outcome rather than data loss.
- A player triggers an end-state (death/victory) and then attempts another action — the system
  prevents continuing a finished run.
- A request for another account's campaign data — it is rejected as not owned by the caller, with no
  leakage of the other account's state.

## Requirements *(mandatory)*

### Functional Requirements

**Identity & accounts**

- **FR-001**: Authentication MUST be provided by a dedicated service separate from the game engine,
  replacing `003`'s development auth stub, so identity concerns stay decoupled from gameplay (epic
  FR-007).
- **FR-002**: The system MUST validate every bearer token (signature, audience, expiry) and resolve
  the authenticated account from the token's subject; the engine MUST NOT store credentials (epic
  FR-010).
- **FR-003**: The system MUST ensure a player can access only their own campaigns, characters, and
  history; all game-data and engine operations MUST require authentication and be scoped to the
  authenticated account (epic FR-009/010).
- **FR-004**: The system MUST persist accounts and campaign ownership — each campaign and its history
  MUST be associated with the owning account (epic FR-008).

**Concurrency & sessions**

- **FR-005**: The system MUST enforce a single active play session per campaign via a session lease.
  A second session opening the same campaign MUST be read-only until it explicitly takes over, at
  which point the previous session MUST become read-only — so concurrent writes cannot corrupt or
  silently overwrite state (epic FR-025).
- **FR-006**: State-changing routes MUST require holding the campaign's current session lease;
  stale-lease writes (token mismatch or expiry) MUST be rejected with a consistent error (epic
  FR-025).

**Durable persistence, save/resume & privacy**

- **FR-007**: The system MUST durably persist each player's character, world state, events, and
  archive so progress survives across sessions and devices (epic FR-011; backed by the store from
  `002`).
- **FR-008**: The system MUST support saving a checkpoint of progress and resuming a living campaign
  from its exact recorded point with no restart, re-roll, or contradiction of recorded facts (epic
  FR-003/011).
- **FR-009**: The system MUST support account data export (portable) and account deletion with a
  cascade from the account to all owned campaigns and their engine rows (epic research §8, data-model
  §E).

**Integrity, isolation & graceful degradation**

- **FR-010**: State writes MUST be atomic — all-or-nothing per state change — so a failure mid-write
  MUST NOT corrupt a save; the change is either fully applied or not applied (epic FR-012, Principle
  V — hardened for the concurrency/multi-account setting beyond `002`'s single-write case).
- **FR-011**: Under many concurrent campaigns across many accounts, each player's state MUST remain
  isolated and consistent with no cross-account leakage (epic SC-005, FR-009).
- **FR-012**: The system MUST degrade gracefully when the authentication service is unavailable:
  already-signed-in players continue read-only until their token expires, and new sign-ins are
  rejected with a clear, safe outcome rather than data loss (epic FR-024).
- **FR-013**: The system MUST reject acting on an ended run and MUST honor recorded facts when
  adventure content has changed since the player last played, so the resume never contradicts them
  (epic Edge Cases).

**Observability**

- **FR-014**: The system MUST emit operational telemetry — at minimum health, error rate, latency,
  and basic play metrics — observable by operators (epic FR-022).
- **FR-015**: The system MUST produce diagnostic logs/traces sufficient to locate the cause of a
  failed player turn without exposing internal failure as corrupted game state to the player (epic
  FR-023).

**Contract & architecture preservation**

- **FR-016**: The account, session-lease, privacy, and observability contracts MUST be folded into
  `docs/CONTRACTS.md` (Principle III).
- **FR-017**: The system MUST stay plugable: the web layer continues to depend only on the MCP + HTTP
  API contracts, and the authentication integration MUST sit behind the same auth seam `003`
  stubbed, so swapping it in does not touch the play loop (Principle II).
- **FR-018**: The migration MUST reuse the existing engine rules, domain model, and tool contract
  unchanged in behavior (epic FR-018); adding accounts, sessions, hardening, and observability MUST
  NOT change game outcomes.

### Key Entities *(include if feature involves data)*

- **Account / Player Identity**: a registered user (owner of campaigns), distinct from the in-game
  character. The separate auth service owns credentials/profile; the engine stores only an opaque
  subject + minimal metadata (PII minimization). Created on first authenticated access; deletable via
  `DELETE /me`, which cascades. Per
  [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §C.1.
- **Campaign**: one playthrough = one CharacterSheet + World + Events + (transient) Combat +
  Archive. The unit of ownership (one account → many campaigns) and of the single-active-session
  rule. States `active` → `ended`. Per
  [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §C.2;
  account ownership is added here (the `account_id` link deferred from `002`).
- **Session Lease**: which session currently holds write rights for a campaign; only the holder may
  issue state-changing operations; a second opener is read-only until an explicit take-over
  atomically reassigns the lease and demotes the prior holder. Per
  [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §C.3.
- **Engine domain entities** (unchanged): `CharacterSheet`, `World`, `Event`, `Combat`,
  `ArchiveRecord` — durable via `PostgresStorage` from `002`; now scoped to an owning account.
- **Ownership & isolation rules**: every engine read/write is scoped to the authenticated account;
  erasure cascades account → campaigns → all engine rows + session lease; export returns the
  account's game data portably. Per
  [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §E.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A returning player can sign in and resume their exact campaign state in under 30
  seconds, with 100% of stats, inventory, and recorded facts intact (epic SC-002).
- **SC-002**: A player resumes on a different device/session with 100% of their state intact, while a
  concurrent second session on the same campaign is read-only until takeover (epic SC-002, FR-025).
- **SC-003**: 100% of unauthenticated or cross-account requests for a player's game data are
  rejected with no leakage (epic FR-009/010).
- **SC-004**: Zero save corruption under induced mid-write failures across a defined concurrency
  stress test; every affected campaign resumes at the last consistent state (epic SC-004, extended to
  concurrency).
- **SC-005**: The system sustains the defined concurrent-campaign load (target: at least 1,000
  concurrent active campaigns) without data loss or cross-account leakage (epic SC-005).
- **SC-006**: When the authentication service is unavailable, already-signed-in players continue
  read-only with no data loss and new sign-ins receive a clear, safe outcome (epic FR-024).
- **SC-007**: Acting on an ended run is rejected 100% of the time, and recorded facts are honored on
  resume after adventure content changes (epic Edge Cases).
- **SC-008**: Operators can detect and locate the cause of an induced failure using only telemetry
  and logs/traces, within a defined response time (epic SC-009).
- **SC-009**: Account deletion removes 100% of the account's game data (campaigns + engine rows);
  export returns the account's complete game data portably (research §8).

## Assumptions

- **Depends on `002` and `003`**: the durable `PostgresStorage` backend (`002`) and the playable web
  backend with documented API + dev auth stub + narrator + `Scene` (`003`) exist and are merged. This
  feature swaps the auth stub for real authentication and hardens/pads the existing backend; it does
  not rebuild storage, the narrator, or the play-loop API.
- **No browser/UI here**: the SPA is a separate feature, `005-professional-spa`, which consumes
  `003`'s documented API and the account/session/privacy endpoints added here. Sign-up/sign-in UI is
  explicitly `005`'s concern — `004` delivers the **backend** auth, accounts, hardening, and
  observability that `005`'s UI depends on. The dependency chain is `002` → `003` → `004` // `005`.
- **US4 already delivered**: the documented, authenticated API as a first-class surface is delivered
  in `003`; `004` extends it with account/session/privacy endpoints rather than re-establishing it.
- **Technology** is decided in the epic's
  [research.md](../001-web-platform-migration/research.md): a dedicated, separately-deployable
  OIDC/OAuth2 provider issuing JWT access tokens, with JWKS-based validation and `sub` → account
  resolution (§3); a single active session per campaign via a short-lived session lease (§6);
  vendor-neutral OpenTelemetry instrumentation exported via OTLP to an operator-chosen backend (§7);
  a GDPR-aligned export + erasure baseline with cascading deletion (§8). The durable store and atomic
  transactions come from `002` (research §1). Named technologies appear only here, not in the
  Functional Requirements or Success Criteria.
- **Engine + MCP tool contract unchanged**: the harness still consumes the engine via `MCPToolset`
  over the existing FastMCP server; adding accounts, sessions, hardening, and observability does not
  change game outcomes or the tool contract (Principle III).
- **Auth seam preserved**: the OIDC integration sits behind the same auth seam `003` stubbed, so the
  play loop is untouched by the swap (Principle II).
- **Best-effort availability, unconditional integrity**: no formal uptime SLA at this slice; a relaxed
  availability target never permits a corrupted save (epic clarification). Graceful degradation is in
  scope; formal high-availability is not.
- **Adventure content**: the debut adventure module continues to provide the lore; no new adventure
  content is required beyond what already exists.
