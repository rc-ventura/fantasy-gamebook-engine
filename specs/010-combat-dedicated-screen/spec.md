# Feature Specification: Combat Dedicated Screen

**Feature Branch**: `feat/010-combat-dedicated-screen`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "crie a spec 010 -> sistema de combate, existe algumas ADRS que ja foram documentadas para isso. Precisamos de uma tela especial de combate e com narrações por turno. A narração não precisa ser uma chamada a LLM pode ser determinístico inicialmente.. só precisa ter um único Narrate no final do resultado."

---

## Background

The current dispatcher (spec 009) resolves an **entire combat in a single turn**: the
`CombatRound` node loops through all rounds internally, with zero player interaction
during the fight. The player never sees a mid-fight state — they receive a finished
combat log all at once.

This spec introduces **interactive, round-by-round combat**: a dedicated frontend screen
where the player sees each round's result and consciously decides to continue, test luck,
or flee. Deterministic text templates describe each intermediate round (no LLM call per
round); a **single LLM narration** runs once at the end of the full fight, summarizing
the battle atmospherically.

**ADRs already in place**:

- [ADR-001](../../docs/adrs/ADR-001-combat-sub-agent-delegation-pattern.md) — Phase-1
  combat delegation (superseded by ADR-033; historical context for the `FinalResult` shape).
- [ADR-006](../../docs/adrs/ADR-006-combat-luck-tally-ephemeral-not-persisted.md) — Luck
  tally is ephemeral (in-memory per `combat_id`); survives in-fight restarts with zero cost.
- [ADR-028](../../docs/adrs/ADR-028-combat-terminal-state-unification.md) — Terminal-state
  check runs once after the narrator returns; a future combat endpoint MUST use the same
  helper.
- [ADR-033](../../docs/adrs/ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md) —
  Deterministic dispatcher: `CombatRound` is already a graph node that calls the MCP combat
  tools; this spec changes its multiplicity from N-per-turn to 1-per-turn.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Round-by-Round Combat Screen (Priority: P1)

The player is in combat. Instead of seeing a wall of text summarizing a completed fight,
they see a dedicated combat screen that shows the current enemy's name and stamina, the
hero's stamina and luck, and the outcome of the most recent round. After each round they
choose: **Continue fighting**, **Test Luck** (if luck > 0), or **Flee** (if allowed).

**Why this priority**: This is the core missing interaction. Without it, combat is
invisible and the player has no agency during a fight — the fundamental premise of the
gamebook (player decisions matter) is violated.

**Independent Test**: Can be fully tested by starting a combat encounter, advancing one
round, and verifying the combat screen renders with correct enemy and hero stats plus
player action buttons. Delivers playable, visible combat.

**Acceptance Scenarios**:

1. **Given** an active combat session, **When** the player views the combat screen, **Then**
   the enemy name and current stamina, the hero's current stamina and luck, and the round
   number are displayed correctly from engine state.

2. **Given** a just-resolved round, **When** the result is shown, **Then** a deterministic
   summary (e.g. "You strike the Troll for 2 damage. The Troll hits you for 1 damage.") is
   displayed — no LLM call, no wait.

3. **Given** the player is shown round results, **When** luck > 0 and the player chooses
   "Test Luck", **Then** a luck test is run via the engine and the round result is adjusted
   accordingly, the player's luck decrements by 1.

4. **Given** flee is allowed, **When** the player chooses "Flee", **Then** the hero takes
   2 stamina damage, combat ends, and the game returns to the narrative screen.

5. **Given** combat just ended (hero won or hero died), **When** the engine reports
   `ended=true`, **Then** no further round actions are available and the game transitions to
   the final narration screen.

---

### User Story 2 — Single LLM Narration at Combat End (Priority: P2)

When combat concludes (victory, death, or flee), a single LLM narration call summarizes
the entire fight atmospherically. The player sees a rich narrative scene that recaps the
battle outcome, with the hero's final state reflected accurately (no invented numbers).

**Why this priority**: Without a closing narration, combat resolution feels mechanical.
The LLM narration is what ties the dice rolls back into the story — but it should fire
exactly once, at the end, not per round.

**Independent Test**: Can be tested by completing a combat (mock all intermediate rounds),
verifying one and only one LLM call is made, and asserting the `Scene` output reflects
the combat log passed to the narrator.

**Acceptance Scenarios**:

1. **Given** combat ends with a hero victory, **When** the final narration runs, **Then**
   the narrator receives the full `TurnOutcome` (all rounds, final hero stamina, whether
   luck was used) and produces a `Scene` without inventing any number not already in that
   outcome.

2. **Given** combat ends with hero death (`stamina ≤ 0`), **When** the final narration
   runs, **Then** the `Scene` has `terminal=true`, `choices` is empty, and the terminal
   state check archives the campaign.

3. **Given** combat ends via flee, **When** the narration runs, **Then** the flee cost
   (2 stamina) is already reflected in engine state, and the narrator only describes the
   escape — never re-applies the damage.

4. **Given** any combat outcome, **Then** the number of LLM calls for that combat is
   exactly 1 (the single closing `Narrate`).

---

### User Story 3 — Combat State Survives Page Refresh (Priority: P3)

If the player refreshes the browser mid-fight, the combat screen is restored from
engine state: `combat_id`, current round, enemy stamina, and hero stats are all
re-read from the MCP server. The fight can continue without data loss.

**Why this priority**: Round-by-round combat implies multiple HTTP requests over time.
The player must not lose a fight because of a network hiccup or browser reload.

**Independent Test**: Start a combat, simulate page reload (discard client state,
re-fetch from API), verify combat screen shows correct in-progress state.

**Acceptance Scenarios**:

1. **Given** an in-progress combat (round 3 of N), **When** the client discards all
   local state and re-loads the game, **Then** the combat screen shows the correct
   current round, enemy stamina, and hero stats from engine persistence.

2. **Given** a mid-fight reload, **When** the player continues, **Then** the next round
   resolves correctly (no rounds are duplicated or skipped).

---

### Edge Cases

- What happens when the player's stamina reaches 0 mid-fight (hero dies in a round)?
  The round result shows the death state; the combat is ended by the engine; the terminal
  narration fires; no further round actions are shown.
- What happens if the player attempts to "Test Luck" but luck is 0?
  The action is disabled; the UI does not allow it; the engine would reject it anyway.
- What happens if flee is attempted when `flee_allowed=false`?
  The action is disabled; the UI does not render the flee button.
- What happens if two browser tabs are open for the same campaign during a fight?
  The session lease (ADR-031/032) prevents a second tab from making engine calls; the
  second tab sees a conflict error and must reload to re-acquire the lease.
- What if combat ends between rounds (e.g. victory condition met by a world flag)?
  The terminal-state check (ADR-028) runs after the closing narration and archives the
  campaign; the UI transitions to the terminal screen.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When a turn result indicates active combat (a `combat_id` is returned in
  the scene context), the system MUST navigate the player to a dedicated combat screen
  instead of the standard narrative view.

- **FR-002**: The combat screen MUST display the current round number, the enemy name
  and current stamina for each enemy, the hero's current stamina and luck, and
  whether flee is allowed.

- **FR-003**: The system MUST expose a per-round action endpoint that accepts one of
  three player actions: **continue** (resolve next round normally), **test\_luck**
  (resolve next round with luck test), or **flee** (attempt escape).

- **FR-004**: Per-round intermediate results MUST be described using deterministic text
  templates (no LLM call). Templates MUST cover: hero wins round, hero loses round, tie,
  luck test success/failure modifier, and flee attempt.

- **FR-005**: The system MUST resolve one combat round per player action request — never
  more. If the player has not acted, the round does not advance.

- **FR-006**: When combat ends (`ended=true`), the system MUST make exactly one LLM
  narration call with the full combat log (`TurnOutcome`) and return a complete `Scene`.

- **FR-007**: The single closing narration MUST respect the "Numbers Never in Prose"
  principle (Constitution §I): all numbers in the `Scene` narrative MUST be sourced
  from the `TurnOutcome` passed by the dispatcher, never invented by the narrator.

- **FR-008**: The terminal-state check (ADR-028) MUST run after the closing narration
  and MUST use the existing shared helper — it MUST NOT be reimplemented inline.

- **FR-009**: In-progress combat state (combat\_id, round number, enemy stamina, hero
  stats) MUST be re-fetchable from the engine at any point so a page reload can
  restore the combat screen without data loss.

- **FR-010**: When `flee_allowed=false`, the flee action MUST be absent from the combat
  screen and rejected by the backend if sent directly.

- **FR-011**: When the hero's luck is 0, the "Test Luck" action MUST be disabled on the
  frontend and rejected by the backend if sent directly.

### Key Entities

- **CombatRound action**: one of `continue | test_luck | flee` — the player's choice
  for the next round; carries no game numbers (the engine computes all outcomes).

- **RoundResult**: the deterministic, per-round outcome shown to the player before the
  closing narration: round number, hero\_damage, enemy\_damage, hero\_won\_round, luck
  modifier used (if any), ended flag, and any flee outcome.

- **CombatSummary**: the aggregated result handed to the closing `Narrate`: all rounds
  (as a `checks` log), final hero state, final enemy state, whether the hero won,
  luck tests used — identical in shape to the existing `TurnOutcome`.

- **Combat screen state** (client-side): current `combat_id`, enemy list with live
  staminas, current hero stamina and luck, round history (deterministic texts), and
  available actions — derived entirely from engine state on each round response.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A player can start, interact with, and complete an entire combat encounter
  without the page freezing or requiring a full reload between rounds.

- **SC-002**: Each combat round result appears within 500 ms of the player submitting
  their action (deterministic path — no LLM call).

- **SC-003**: The single closing LLM narration fires at most once per combat, regardless
  of the number of rounds fought.

- **SC-004**: A player who refreshes the browser mid-fight can resume without losing any
  round history or engine state.

- **SC-005**: 100 % of test cases where `flee_allowed=false` or `luck=0` result in the
  corresponding action being blocked at both the UI and backend levels.

- **SC-006**: The terminal-state check (death/victory) fires correctly after every
  combat that ends in a death or victory, and the campaign is archived exactly once.

- **SC-007**: The narrator never produces a stamina, luck, or damage number in the
  closing `Scene` that was not present in the `TurnOutcome` passed to it (verified by
  the existing fabricated-number detection, ADR-019).

---

## Assumptions

- The existing `combat_id`, `start_combat`, `resolve_combat_round`, `end_combat`, and
  `flee_combat` MCP tools (spec 009 / CONTRACTS.md §6) remain unchanged — this spec
  changes how the harness *calls* them (one at a time, player-paced), not what they do.
- The `CombatRound` graph node in spec 009 is refactored to execute **one round per
  run** instead of looping internally; the loop moves to the frontend interaction cycle.
- Deterministic round templates live in `templates.yaml` (or a new `combat-templates.yaml`)
  and are rendered by the backend — the frontend receives pre-rendered text, not raw numbers.
- The session lease (ADR-031/032) is already enforced; multi-tab conflicts during combat
  are handled by the existing lease mechanism without changes.
- "Test Luck" costs 1 luck regardless of the round result (ADR-006 ephemeral tally is
  still the right model for the summary; durability of `luck_spent` is out of scope).
- The adventure module's `flee_allowed` and `victory_condition` flags are read from the
  existing `backbone.yaml` structure — no adventure module schema changes are required.
- Mobile / responsive design for the combat screen is a separate polish concern; this
  spec targets desktop-first layout.
