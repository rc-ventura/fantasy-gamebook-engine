# Feature Specification: Narrator Tool-Use Refactor

**Feature Branch**: `007-narrator-tool-use-refactor`

**Created**: 2026-06-30

**Status**: Draft

**Depends on**: `006-cycle1-remediation` (must be merged first — security fixes must land before this architectural change)

**Architecture decision**: [ADR-029](../../docs/adrs/ADR-029-narrator-as-tool-use-agent-eliminate-effects.md)

**Input**: "cria a spec 007 com o trabalho a ser feito da adr 29"

---

## Overview

The web narrator currently emits a list of deferred engine operations (`effects[]`) that the
API layer executes *after* the narrative has already been written. This means the narrator writes
prose without knowing what the engine actually computed — it cannot say "you take 3 damage" because
it never saw the 3. The terminal narrator (Phase 1) never had this problem: it called engine tools
directly during generation and narrated with real results.

This slice eliminates the deferred-execution pattern and makes the web narrator behave identically
to the terminal narrator: call engine tools, see real results, narrate real numbers, return a scene.

**Governing constraint (Principle I — NON-NEGOTIABLE)**: The narrator MUST NOT invent numbers or
roll dice in prose. Every numeric value MUST come from a real engine tool call. This slice restores
that guarantee by design rather than relying on post-hoc heuristic detection.

---

## User Scenarios & Testing

### User Story 1 — Player receives accurate combat narrative (Priority: P1)

A player takes a turn that involves combat. After the turn, the narrative they receive accurately
describes what the engine computed: how many rounds were fought, who landed hits, how much
stamina was lost, and who won. The numbers in the prose match the hero's actual current stats.

**Why this priority**: This is the core defect. Today the narrator writes "you strike the goblin
hard" without knowing if the hit landed — the engine resolves it after the narrative is fixed.
This violates Principle I and misleads the player. Everything else in this slice follows from
fixing this.

**Independent Test**: Run a full turn that triggers combat. Assert that the narrative contains
numbers consistent with the hero's stamina change and combat outcome recorded in the engine state.
The numbers in prose must not contradict the real engine state.

**Acceptance Scenarios**:

1. **Given** a hero encounters an enemy, **When** the player takes a combat turn, **Then** the
   narrator's prose describes the combat outcome (winner, approximate stamina loss) using values
   that match the engine's `FinalResult` — no invented numbers.
2. **Given** the narrator completes a combat turn, **When** the hero's stamina is checked via
   `/hero`, **Then** the stamina shown matches what the narrative described (within the damage
   range the engine allows).
3. **Given** a narrator retry (invalid scene on first attempt), **When** the scene is retried,
   **Then** the retry accounts for engine state already updated by the first attempt — no
   double-applying damage.

---

### User Story 2 — Player takes a non-combat turn with real rolled numbers (Priority: P1)

A player takes a turn that involves a dice roll or luck test (e.g., crossing a trap, finding
treasure). The narrative correctly names the rolled value and the resulting outcome. The player
can verify the outcome by checking their character sheet.

**Why this priority**: Same priority as combat — Principle I applies to every number, not just
combat numbers. A trap that deals "4 damage" must match the stamina change the engine recorded.

**Independent Test**: Run a turn that triggers a dice roll or luck test. Assert (a) the turn
response has no `effects_applied` field, and (b) the character state reflects the outcome
described in the narrative.

**Acceptance Scenarios**:

1. **Given** a scene that includes a luck test, **When** the player takes the turn, **Then**
   the narrative describes the luck outcome (success/failure) and the luck decrement is visible
   in the hero's character sheet.
2. **Given** a scene that includes a dice roll for random damage, **When** the turn completes,
   **Then** the stamina change recorded in the engine equals the damage amount implied by the
   narrative.
3. **Given** a player checks the turn response format, **When** they inspect `TurnResponse`,
   **Then** there is no `effects_applied` field — all state changes happened during the turn,
   not after.

---

### User Story 3 — Combat resolves as a single turn, not a multi-request flow (Priority: P2)

A player enters a combat encounter. The entire fight — from first round to final outcome — is
resolved in a single turn request and described in one narrative. The player does not need to
call separate endpoints to advance each round.

**Why this priority**: The current `POST /combat/round` endpoint is a workaround for the
deferred-execution problem. Once the narrator resolves combat directly during generation, this
endpoint becomes redundant. Removing it simplifies the API surface.

**Independent Test**: Send a single `POST /turn` request that triggers combat. Assert the response
narrative describes a complete combat (start → rounds → outcome). Assert that `POST /combat/round`
returns 404.

**Acceptance Scenarios**:

1. **Given** a hero faces an enemy, **When** the player takes a single turn with "fight" as
   the choice, **Then** the full combat resolves and the narrative describes the outcome.
2. **Given** the player wants to flee before combat starts, **When** they choose "flee" before
   the turn resolves combat, **Then** the narrator calls `flee_combat` and the narrative
   describes the escape (with real stamina cost).
3. **Given** a request to `POST /combat/round`, **Then** the endpoint no longer exists (404).
4. **Given** a request to `POST /combat/flee`, **Then** the endpoint no longer exists (404).

**Trade-off (documented)**: Per-round luck tests and mid-combat fleeing (available in Phase 1
terminal) are not supported in this design. The player decides pre-combat whether to fight or
flee. This is a deliberate simplification — see ADR-029 Condition 2 for the upgrade path.

---

### User Story 4 — Developer: codebase is simpler after removing the deferred-execution scaffolding (Priority: P2)

A developer reading the narrator code sees a straightforward tool-use loop: narrator reads
state, calls engine tools, narrates results, returns scene. No `effects[]`, no mapping tables,
no post-hoc validator, no separate combat subagent module.

**Why this priority**: The scaffolding (`EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect`,
`_apply_scene_effects`, `_scene_contains_fabricated_numbers`, `combat_subagent.py`) adds
cognitive overhead and maintenance surface with no benefit once the narrator calls tools
directly. Removing it makes the architecture match the documented design (ADR-029).

**Independent Test**: After the slice lands, verify that the following no longer exist:
`scene.py:EFFECT_TO_MCP_TOOL`, `scene.py:Effect`, `agent.py:_scene_contains_fabricated_numbers`,
`play.py:_apply_scene_effects`, `harness/combat_subagent.py`, `api/combat.py`.

**Acceptance Scenarios**:

1. **Given** `src/gamebook_web/harness/scene.py`, **Then** it contains only `Scene` (narrative
   + choices) and `Choice` — no `Effect`, `EffectType`, or `EFFECT_TO_MCP_TOOL`.
2. **Given** `src/gamebook_web/api/play.py`, **Then** `take_turn` contains no
   `_apply_scene_effects` call and no `effects_applied` in `TurnResponse`.
3. **Given** `src/gamebook_web/harness/agent.py`, **Then** it contains no
   `_scene_contains_fabricated_numbers` and no `_RESULT_KEYS`.
4. **Given** `uv run pytest -q`, **Then** all tests pass with the simplified codebase.

---

### User Story 5 — Developer: contract and frontend types stay in sync (Priority: P3)

The `CONTRACTS.md §10` Scene contract and the frontend `TurnResponse` TypeScript type are updated
to reflect the simplified schema. Downstream consumers (frontend, tests, documentation) do not
reference removed fields.

**Why this priority**: Contract drift is a governance finding. Once `effects_applied` is removed
from the API response, the contract and frontend types must be updated in the same change
(Principle III).

**Independent Test**: Grep for `effects_applied` and `effects: list[Effect]` across
`docs/CONTRACTS.md`, `frontend/src/`, and test files — zero hits after the slice.

**Acceptance Scenarios**:

1. **Given** `docs/CONTRACTS.md §10`, **Then** it describes `Scene` as `{ narrative: str,
   choices: list[Choice] }` with no `effects` field.
2. **Given** `TurnResponse` in the frontend TypeScript types, **Then** it has no
   `effects_applied` field.
3. **Given** `tests/` directory, **Then** no test asserts `effects_applied` in a
   `TurnResponse`.

---

### Edge Cases

- **Narrator starts combat but fails to finish it** (calls `start_combat`, then produces an
  invalid scene before calling `end_combat`): the engine holds partial combat state. The retry
  must not start a second combat on top of the first. The narrator must detect the active combat
  and continue it, not restart it.
- **Delta-based mutations under retry** (`update_character_sheet` with delta-based changes):
  if the tool applies `{stamina_delta: -2}` and `ModelRetry` fires, the second attempt would
  apply -2 again. **Pre-condition audit**: `update_character_sheet` mutation semantics
  (`src/gamebook/mcp/server.py`) must be confirmed as set-based before Phase 2 of migration
  starts. If delta-based, the system prompt must enforce read-before-write.
- **Test suite references to removed APIs**: `FakeNarrator` default scenes carry `effects[]`.
  Every test asserting `TurnResponse.effects_applied` must be rewritten or removed as part of
  this slice.
- **Frontend rendering of removed field**: if the frontend renders `effects_applied` in any
  component (debug panel, etc.), that component must be updated or removed.

---

## Requirements

### Functional Requirements

- **FR-001**: The narrator MUST call engine MCP tools directly during scene generation and
  incorporate the results into the narrative before returning the scene.
- **FR-002**: The `Scene` model MUST contain only `narrative: str` and `choices: list[Choice]`.
  The `effects` field MUST be removed.
- **FR-003**: `TurnResponse` MUST NOT contain an `effects_applied` field.
- **FR-004**: The turn endpoint (`POST /campaigns/{id}/turn`) MUST NOT execute any engine
  operations after the narrator returns — all state changes happen during narrator generation.
- **FR-005**: Combat MUST resolve inside a single turn request. The explicit combat endpoints
  (`POST /combat/round`, `POST /combat/flee`) MUST be removed.
- **FR-006**: The narrator system prompt MUST instruct direct tool use ("call MCP tools, get
  real results, narrate with real numbers") instead of emitting deferred `effects[]`.
- **FR-007**: `docs/CONTRACTS.md §10` MUST be updated to reflect the simplified `Scene` schema.
- **FR-008**: All tests MUST pass after scaffolding removal (`uv run pytest -q` green).
- **FR-009**: The plugability audit (`tests/qa/test_dependencies.py`,
  `tests/qa/test_isolation.py`) MUST remain green.

### Pre-Condition (blocks FR-001 and FR-004)

- **PC-001**: Audit `src/gamebook/mcp/server.py` to confirm `update_character_sheet` applies
  set-based changes (not delta-based). Document the finding. If delta-based, the narrator system
  prompt must enforce read-before-write before FR-004 can be implemented safely.

### Key Entities

- **Scene** (simplified): `{ narrative: str, choices: list[Choice] }` — the narrator's output
  for one turn. No `effects` field.
- **Choice**: `{ id: str, label: str }` — unchanged.
- **TurnResponse** (simplified): `{ scene: Scene, character?: dict, world?: dict }` — no
  `effects_applied`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: A turn involving a dice roll produces a narrative whose described outcome matches
  the hero's recorded state change — zero discrepancy between prose and engine state across
  any test scenario.
- **SC-002**: A turn involving combat produces a complete combat narrative (all rounds through
  final outcome) in a single HTTP response — no follow-up `POST /combat/round` calls required.
- **SC-003**: The narrator codebase loses at minimum 7 named constructs:
  `EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect`, `_apply_scene_effects`, `_build_tool_args`,
  `_scene_contains_fabricated_numbers`, `_RESULT_KEYS` — all removed, no replacements.
- **SC-004**: Full test suite (`uv run pytest -q`) remains green throughout all migration phases.
- **SC-005**: No reference to `effects_applied` or `effects: list[Effect]` remains in
  `CONTRACTS.md`, frontend types, or tests after the slice is complete.

---

## Assumptions

- Spec 006 (`006-cycle1-remediation`) is merged and all its security/architecture fixes are in
  place before this slice starts. In particular: multi-tenant engine (ADR-018) must be live so
  the narrator calls tools with the correct `campaign_id`.
- `update_character_sheet` uses set-based mutations (absolute values, not deltas). This will be
  confirmed by PC-001 before implementation begins.
- `SkillsCapability` (community package `pydantic-ai-skills`) is **out of scope** for this slice.
  The system prompt change (FR-006) is sufficient to restore the Phase 1 interaction model;
  `SkillsCapability` is an optional future enhancement.
- Per-round combat interactivity (player decides luck test each round) is **out of scope**. The
  player makes a pre-combat decision (fight/flee); luck test behavior during combat is handled
  by the narrator's interpretation of that decision. This is a deliberate regression from
  Phase 1 terminal behavior — acceptable for the initial web port.
- The `FakeNarrator` in tests will be updated to return `Scene(narrative, choices)` with no
  effects. This is a test refactor estimated at 1-2 days.
- The migration is phased (5 phases per ADR-029); each phase is independently mergeable after
  tests pass.

---

## References

- [ADR-029](../../docs/adrs/ADR-029-narrator-as-tool-use-agent-eliminate-effects.md) —
  authoritative architecture decision (root cause, trade-offs, migration phases, alternatives)
- `src/gamebook_web/harness/agent.py` — narrator to refactor
- `src/gamebook_web/harness/scene.py` — Scene model to simplify
- `src/gamebook_web/api/play.py` — turn endpoint to simplify
- `src/gamebook_web/api/combat.py` — router to remove
- `src/gamebook_web/harness/combat_subagent.py` — to remove
- `src/gamebook_web/harness/base.py` — FakeNarrator default scenes to update
- `docs/CONTRACTS.md §10` — Scene contract to update
- `specs/006-cycle1-remediation/spec.md` — predecessor slice (must land first)
