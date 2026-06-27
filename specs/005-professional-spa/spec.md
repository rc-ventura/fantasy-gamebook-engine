# Feature Specification: Professional SPA (Browser Frontend)

**Feature Branch**: `005-professional-spa`

**Created**: 2026-06-27

**Status**: Draft

**Epic**: `001-web-platform-migration` — a decomposition slice of the epic. It depends on
`003-web-backend-mvp` (which delivers the documented HTTP API + OpenAPI contract this SPA
consumes) and can be developed in parallel against `003`'s frozen OpenAPI contract using a
mock/API client. Real sign-up/sign-in UI lands here only after `004-accounts-hardening-obs`
ships real OIDC; until then the SPA uses `003`'s dev auth stub. See
[../001-web-platform-migration/spec.md](../001-web-platform-migration/spec.md) for the
umbrella vision and the shared design artifacts (research, data model, contracts, quickstart).

**Input**: Decomposition slice of the Web Platform Migration epic. Scope: the professional
single-page web application that is one client of the documented HTTP API from `003`. It
consumes `003`'s frozen OpenAPI contract via a typed client, renders the full play loop from
real engine state (never fabricated values), and provides the account sign-in / resume /
single-active-session UX in the browser. No backend, no storage, no engine changes here —
this feature is the UI only.

## Overview

Take the documented, playable HTTP API delivered by `003` and give it a **distinct,
professional front-end**: a single-page web application that is just another consumer of that
API — no privileged hidden path (epic FR-017). The SPA renders the full gamebook loop —
opening → exploration → combat → end-state — in a polished interface: narration plus numbered
choices and free-text input, a character sheet, inventory/backpack, map, and combat panel,
each reflecting **real engine state** returned by the API. The defining rule of the product is
preserved at the UI boundary: **the player never sees a number the engine did not produce** —
the front-end invents nothing, rolls nothing, and fabricates no stat (epic FR-020/021).

The SPA holds no durable state of its own; all game state is read from and written through the
API (Principle V). It can be developed and tested against `003`'s frozen OpenAPI contract
using a mock, **in parallel with `004`** — the dependency chain is `002 → 003 → 004 // 005`.
The real sign-up/sign-in flow against the OIDC provider is gated on `004`; until then the SPA
uses `003`'s dev auth stub, with the auth seam designed so the real provider swaps in without
touching the play loop. Resume-across-devices and the single-active-session
read-only-until-takeover UX are exercisable against `003`'s API.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Play the gamebook in a web browser (Priority: P1)

A player opens the web application, starts a new adventure (or resumes one in progress), reads
the narration in a polished interface, and advances the story by selecting a numbered choice or
typing free text. Combat, luck tests, and stat changes resolve through the engine and are
reflected on screen. The player never sees a number the engine did not produce.

**Why this priority**: This is the heart of the product from the player's seat. Without the
core play loop rendered in a real web UI, nothing else matters. It is the minimum viable slice
that delivers a playable web game, and it can be built and validated against `003`'s frozen
OpenAPI contract with a mock before the backend is live.

**Independent Test**: Load the web app (against a mock or the live API from `003`), play from
the opening scene through at least one exploration turn and one combat encounter to a clean
end-state (victory or death), and confirm every number shown traces back to an engine result —
no UI-fabricated values (epic US1 / SC-003).

**Acceptance Scenarios**:

1. **Given** a player with no character, **When** they open the app, **Then** they are offered
   to create a character and begin the adventure's opening scene.
2. **Given** a player with a living character, **When** they open the app, **Then** the story
   resumes from the exact recorded point with no restart, re-roll, or contradiction of recorded
   facts.
3. **Given** the player is presented a scene, **When** they select a numbered choice or submit
   free text, **Then** the next scene is rendered and any dice/luck/stat effects shown come
   from the engine.
4. **Given** the player enters combat, **When** rounds resolve, **Then** the combat panel shows
   engine-computed outcomes, optional luck tests are offered, and the fight ends in a narrated
   result.
5. **Given** the player reaches a death or victory end-state, **When** it occurs, **Then** the
   app shows the appropriate ending, the run is archived, and further actions are prevented.

---

### User Story 2 - Account sign-in and progress that follows me in the UI (Priority: P2)

A player signs in (or signs up) through the authentication service, and their character, world
state, events, and history follow them: they can close the browser, return later or from
another device, sign in, and resume exactly where they left off. A second tab or device that
opens the same campaign is read-only until it explicitly takes over, so concurrent edits cannot
silently overwrite state.

**Why this priority**: Identity and durable, per-account progress are what make the experience
real and shareable — but they depend on the auth service being real. Until `004` ships real
OIDC, the SPA uses `003`'s dev auth stub, so the full sign-in/resume UX lands here as a P2 once
`004` is available; the resume-across-devices and single-active-session UI behaviors are
exercisable against the API from `003`.

**Independent Test**: Sign in, play several turns, sign out, sign in on a different
session/device, and confirm the campaign resumes at the exact recorded point with all stats and
inventory intact. Open the same campaign in a second tab and confirm it is read-only until
takeover (epic US2 / SC-002).

**Acceptance Scenarios**:

1. **Given** a new visitor, **When** they sign up via the authentication flow, **Then** an
   account is created and they can start their own private campaign *(gated on `004`'s real
   OIDC; dev auth stub until then)*.
2. **Given** a returning player, **When** they sign in, **Then** they see only their own
   campaign(s) and history, never another player's.
3. **Given** a signed-in player mid-campaign, **When** they sign out on device A and sign in on
   device B, **Then** the campaign resumes at the exact recorded point with stats, inventory,
   and recorded facts intact.
4. **Given** the same campaign open in two tabs/devices, **When** the second session opens it,
   **Then** it is read-only until it explicitly takes over, at which point the first becomes
   read-only — concurrent writes cannot corrupt or silently overwrite state (epic FR-025).

---

### User Story 3 - A polished, professional UI (Priority: P2)

The player-facing experience is a distinct, professional front-end that renders narration,
numbered choices, free-text input, character sheet, inventory/backpack, map, and combat state —
all from real engine state — with clear loading, empty, and error states so the app never shows
a broken or unexplained screen.

**Why this priority**: A polished, trustworthy UI is what separates a hosted product from a
prototype, and it is the spec's explicit requirement (epic FR-020/021). It supports the P1 play
loop rather than being the loop itself.

**Independent Test**: Exercise each panel (scene, character sheet, inventory, map, combat) and
the loading/empty/error states; confirm every value shown reflects real engine state and no
fabricated values appear.

**Acceptance Scenarios**:

1. **Given** any panel (character sheet, inventory, map, combat), **When** it is rendered,
   **Then** every value shown reflects real engine state, never a value fabricated by the
   front-end.
2. **Given** a slow or in-flight operation, **When** the UI waits for a response, **Then** a
   clear loading state is shown, never a frozen or unexplained screen.
3. **Given** an empty state (no character yet, empty inventory, no map data), **When** it is
   rendered, **Then** a clear, helpful empty state is shown rather than a blank or broken
   layout.
4. **Given** an error from the API (e.g. auth unavailable, run ended, not session holder),
   **When** it occurs, **Then** a clear, safe error state is shown to the player rather than
   corrupted game state.

---

### Edge Cases

- A player resumes a campaign whose adventure content has changed since they last played —
  recorded facts are honored and the UI shows the resumed state without contradiction.
- Two browser tabs or devices open the same campaign at once — the second is read-only until it
  takes over; the UI reflects the read-only/active status clearly so concurrent edits cannot
  silently overwrite state (epic FR-025).
- A player abandons a turn mid-combat (closes the tab) — on return the fight resumes in a
  consistent state.
- The authentication service is temporarily unavailable — signed-in players get a clear, safe
  outcome (read-only until token expiry / a clear failure message) rather than data loss or a
  broken screen (epic FR-024).
- A turn reaches an end-state and the player attempts another action — the UI prevents
  continuing a finished run and shows the ending.
- The API returns an unexpected error mid-turn — a safe error state is shown and the player's
  last consistent state is preserved on reload.

## Requirements *(mandatory)*

### Functional Requirements

**Core play loop (in the browser)**

- **FR-001**: The system MUST let a player play the full gamebook loop — start/resume, explore,
  make choices, resolve combat, reach end-states — through a web interface that consumes the
  documented API from `003` (epic FR-001).
- **FR-002**: The UI MUST NOT invent numbers or roll dice; all randomness, luck tests, combat
  math, and state changes MUST be produced by the engine via the API and reflected in the UI
  (epic FR-002, Principle I).
- **FR-003**: On opening the app, the UI MUST load the player's real game state from the API
  before rendering, and MUST resume a living campaign from its exact recorded point (epic
  FR-003).
- **FR-004**: The UI MUST present each turn as narration plus a set of selectable numbered
  choices, and MUST accept free-text player input in addition to the offered choices (epic
  FR-004).
- **FR-005**: The UI MUST surface combat encounters with optional luck tests and a clear final
  outcome narrated to the player (epic FR-005).
- **FR-006**: The UI MUST handle death and victory end-states, showing the appropriate ending
  and preventing further actions on a finished run (epic FR-006).

**Panels & professional UI**

- **FR-007**: The UI MUST render a character sheet, inventory/backpack, map, and combat panel,
  each reflecting real engine state (epic FR-020).
- **FR-008**: All values shown in the UI (stats, gold, inventory, dice/luck/combat outcomes)
  MUST reflect real engine state, never values fabricated by the front-end (epic FR-021).
- **FR-009**: The UI MUST provide clear loading, empty, and error states so the player never
  sees a frozen, blank, or unexplained screen.

**Account, resume & sessions (UI behavior)**

- **FR-010**: The UI MUST provide a sign-up / sign-in flow against the authentication provider;
  until real OIDC is available it MUST use `003`'s dev auth stub, with the seam designed so the
  real provider swaps in without touching the play loop (epic FR-008).
- **FR-011**: The UI MUST associate play with the signed-in account and show only the player's
  own campaign(s) and history (epic FR-009).
- **FR-012**: The UI MUST support resume across devices — sign out on one, sign in on another,
  state intact (epic US2 / SC-002).
- **FR-013**: The UI MUST enforce the single-active-session UX: a second tab/device opening the
  same campaign is read-only until it explicitly takes over, at which point the prior session
  becomes read-only (epic FR-025).

**Contract & resilience**

- **FR-014**: The UI MUST consume only the documented HTTP API contract from `003` — no
  privileged or hidden path (epic FR-017).
- **FR-015**: The UI MUST degrade gracefully when a dependency (e.g. the authentication service)
  is unavailable, showing a clear, safe outcome rather than data loss (epic FR-024).

### Key Entities *(include if feature involves data)*

- **Scene**: the structured unit the narrator produces for a turn — narration, choices, effects
  — that the UI renders; per
  [../001-web-platform-migration/contracts/scene.md](../001-web-platform-migration/contracts/scene.md).
- **Engine domain entities** (displayed, not owned by the UI): `CharacterSheet`, `World`,
  `Event`, `Combat`, `ArchiveRecord` — shapes per
  [../001-web-platform-migration/data-model.md](../001-web-platform-migration/data-model.md) §A;
  all durable via `003`/`002`.
- **Campaign**: the unit of play and of the single-active-session rule; the UI lists, opens, and
  resumes campaigns.
- **Session Lease**: the write-right the UI acquires/refreshes/takes over to drive a campaign;
  read-only until held (epic FR-025).
- **Account / Player Identity**: the signed-in user that owns campaigns; the UI shows only the
  player's own data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new player can go from landing on the app to making their first in-game choice
  in under 3 minutes, including account creation (epic SC-001).
- **SC-002**: A returning player can sign in and resume their exact campaign state in under 30
  seconds, with 100% of stats, inventory, and recorded facts intact (epic SC-002).
- **SC-003**: 100% of numbers shown to players originate from the engine — zero UI-fabricated
  values — verified across a representative browser play-through audit (epic SC-003).
- **SC-004**: The full play loop (opening → exploration → combat → end-state) is playable end to
  end in the browser against the documented API, with every number tracing to an engine result
  (epic US1).
- **SC-005**: The UI presents clear loading, empty, and error states for every async operation
  and API error; no frozen/blank/unexplained screen is reachable in a representative audit.

## Assumptions

- **Depends on `003`**: the documented HTTP API + frozen OpenAPI contract exist; this feature
  consumes them. It can be developed in parallel against `003`'s frozen OpenAPI using a
  mock/API client, before the backend is live.
- **Parallel with `004`**: this feature can develop against `003`'s frozen OpenAPI in parallel
  with `004` (accounts hardening). The dependency chain is `002 → 003 → 004 // 005`.
- **Sign-in UI gated on `004`**: the real sign-up/sign-in UI flow against the OIDC provider
  lands here only after `004` ships real OIDC. Until then the SPA uses `003`'s dev auth stub;
  the auth seam is designed so the real provider swaps in without touching the play loop.
  Resume-across-devices and single-active-session UI behaviors are exercisable against `003`'s
  API.
- **Technology** is decided in the epic's
  [research.md §5](../001-web-platform-migration/research.md): a separate React + Vite +
  TypeScript SPA under `frontend/`, consuming the HTTP API via a typed client generated from the
  OpenAPI schema; tests via vitest (unit) + Playwright (E2E). Specific tech is a frontend-team
  call per research.md §5.
- **No persistence in the UI**: the SPA holds no durable game state; all state is read from and
  written through the API (Principle V). The UI adds no new cross-module contract (Principle
  III).
- **Engine + API contract unchanged**: the UI consumes the documented API; it does not touch the
  engine, storage, or the MCP tool contract.
- **Browser targets**: modern evergreen web browsers; no legacy browser support is assumed.
- **Availability best-effort**: inherited from the epic; the UI degrades gracefully on API/auth
  unavailability rather than corrupting the player's view.
