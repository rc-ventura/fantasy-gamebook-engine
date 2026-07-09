# Tasks: Deterministic Turn Dispatcher (Pure Narrator)

**Input**: Design documents from `specs/009-deterministic-turn-dispatcher/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user
stories), [research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [ADR-033](../../docs/adrs/ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md)

**Tests**: Included — this repo's constitution mandates the full test suite + plugability
audit green before merge, and `rules`/`combat` already establish the
deterministic-testing convention this feature must extend, not opt out of.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) so each
is independently implementable and testable. User Story 1 is the MVP checkpoint —
everything else can ship later without weakening it.

**Revision note**: this version incorporates `/speckit-analyze`'s findings (P1, C1–C3,
F1–F2, U1, L1) — see the inline "(analyze fix: ...)" markers below for what changed and
why. `research.md`/`data-model.md`/`contracts/` were updated first; this file reflects
their resolved state, not the original draft.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 / US4, per spec.md's four user stories
- All paths are repo-root-relative

---

## Phase 1: Setup

**Purpose**: Skeleton files for the new modules — no behavior yet.

- [ ] T001 Create `src/gamebook_web/harness/adventure_structure.py` (empty module with the
  file's docstring: AdventureStructure/MechanicalSituationTemplate Pydantic models +
  `backbone.yaml`/`templates.yaml` loader — filled in Phase 2)
- [ ] T002 [P] Create `src/gamebook_web/harness/dispatcher.py` (empty module with the
  file's docstring: the `pydantic_graph.Graph`, its nodes, `IntentClassification`,
  `TurnOutcome`, `DispatchState` — filled in Phases 2–3)
- [ ] T003 [P] Create the `adventure_modules/` top-level directory with an empty
  `templates.yaml` (shared mechanical situation library, filled in T010). **(analyze fix
  F2)**: originally `.claude/skills/_shared/` — moved out of `.claude/skills/` entirely,
  since that directory's contract is "each subdirectory is a Claude Code Skill" (needs
  its own `SKILL.md`), which a bare shared-data directory doesn't satisfy. See
  `research.md`'s resolved file-location decision.

**Checkpoint**: New files exist; nothing wired in yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The MCP contract extension, the adventure-structure data model, and the
narrator's tool removal — every user story depends on all three.

**⚠️ CRITICAL**: Complete this phase before any User Story phase.

- [ ] T004 Add `apply_healing(campaign_id, amount, source)` and
  `apply_damage(campaign_id, amount, source)` tools to `src/gamebook/mcp/server.py` —
  relative deltas on `stamina.current`, clamped via the existing `Attribute` invariant
  (reuse the same bounds-checking path `update_character_sheet` already uses). Reject
  `amount <= 0`. See `contracts/mcp-tool-contract-changes.md` for the exact contract.
- [ ] T005 Update `docs/CONTRACTS.md` §6 with the 2 new tools (20-tool table) in the same
  change as T004 — Constitution Principle III, no silent drift.
- [ ] T006 **(analyze fix C3, new task)** [P] Extend `tests/qa/test_mcp_integration.py`
  (the existing file testing MCP tools directly — not just indirectly through the
  dispatcher) with direct-call tests for `apply_healing`/`apply_damage`: a healing/damage
  delta applies correctly, clamps at `initial`/`0`, and `amount <= 0` is rejected. Without
  this, the two new tools would only ever be exercised indirectly via T024's dispatcher
  integration tests — this repo's Principle IV convention is isolated, direct
  engine-level testing for engine-level changes.
- [ ] T007 [P] In `src/gamebook_web/harness/adventure_structure.py`: define
  `ProbabilisticEncounter`, `AdventureStructure` (`zones`, `key_npcs`, `boss`,
  `victory_condition`, `opening_location`, `probabilistic_encounters`, `narrative_zones`,
  `reviewed_by: str | None`, `reviewed_at: str | None`) as Pydantic `BaseModel`s per
  `data-model.md`. **(analyze fix U1)**: `reviewed_by`/`reviewed_at` are new — FR-011's
  human-review gate, checked by the validator in T038, not merely documented.
- [ ] T008 [P] In `src/gamebook_web/harness/adventure_structure.py`: define `CheckStep`
  (`tool`, `args`, `comparator` — comparator `op` restricted to a closed enum `eq/ne/lt/
  le/gt/ge`, **never** `eval()`/`exec()`), `ParamSpec`, `MechanicalSituationTemplate` per
  `data-model.md`.
- [ ] T009 In `src/gamebook_web/harness/adventure_structure.py`: implement
  `load_adventure_structure(module_dir) -> AdventureStructure` and
  `load_templates(path) -> dict[str, MechanicalSituationTemplate]` — YAML → Pydantic
  validation, raising a clear error on schema violation (feeds the FR-010 validator in
  T038, and fails loudly rather than silently accepting malformed content).
- [ ] T010 Author `adventure_modules/templates.yaml` with `risky_action`,
  `skill_check`, `rest_heal`, `move`, and `combat` template definitions, per
  `contracts/adventure-module-schema.md`'s excerpt (combat's `mandatory_checks` covers
  only `start_combat` — the round-by-round loop is `CombatRound`'s job, not expressible
  as a flat check list). **(analyze fix F2)**: path corrected from
  `.claude/skills/_shared/templates.yaml`.
- [ ] T011 In `src/gamebook_web/harness/dispatcher.py`: define `IntentClassification`
  (`action: str | None`, `confidence: float`, `template: str | None` — no numeric game
  field, per research.md's fabrication-surface argument), `TurnOutcome` (`action`,
  `template`, `checks`, `final_state`), and the `DispatchState` dataclass
  (`campaign_id`, `toolset`, `context`, `adventure`, `classification`, `outcome`) per
  `data-model.md`.
- [ ] T012 In `src/gamebook_web/harness/agent.py`: remove `_NARRATOR_ALLOWED_TOOLS` and
  change the narrator's `agent.run()` call to `toolsets=[]` — the narrator receives zero
  tools, mutating or read-only (research.md's "empty toolset" decision). Update
  `_NUMBERS_NEVER_IN_PROSE_RULE`'s system-prompt text to stop instructing tool calls the
  narrator can no longer make; it now only narrates from prompt content.
- [ ] T013 Update `tests/server/test_narrator_integration.py`'s
  `test_allowlist_excludes_lifecycle_tools` / `test_allowlist_includes_core_play_tools`
  (which assert against the now-removed `_NARRATOR_ALLOWED_TOOLS`) to instead assert the
  narrator's toolset is empty.

**Checkpoint**: MCP contract extended (20 tools) with direct test coverage,
adventure-structure data model exists and loads/validates YAML (including the FR-011
review gate fields), narrator has zero tools. Nothing produces a `Scene` yet — the graph
itself is built in Phase 3.

---

## Phase 3: User Story 1 - A hero's stats can never be corrupted by an invented outcome (Priority: P1) 🎯 MVP

**Goal**: Every stat change traces to an actual computed check, regardless of which AI
model narrates — closing ADR-033's two empirically-reproduced gaps.

**Independent Test**: [quickstart.md](./quickstart.md) — "Story 1" and "Story 1
(extended encounter)", run against at least two different models.

### Implementation for User Story 1

- [ ] T014 [US1] In `dispatcher.py`: implement `ClassifyIntent` node — one
  `pydantic_ai.Agent` call (`Agent(..., name="intent_classifier")` — **(analyze fix
  L1)**: explicit name, not inferred, so Logfire/OTel traces distinguish it from
  `Narrate`), `output_type=IntentClassification`, **no toolset**. Reads the current
  zone's available templates/encounters (from `DispatchState.adventure`, already
  resolved) and the player's free text. Returns `MechanicalDispatch` (confidence above
  threshold and a template matched) or `NarrativeFree` (otherwise — FR-004).
- [ ] T015 [US1] In `dispatcher.py`: implement `MechanicalDispatch` node — zero LLM
  calls. Looks up the classified `template` in the loaded template library, executes its
  `mandatory_checks` via `call_engine()`/`direct_call_tool` (`mcp_host.py`, ADR-021
  pattern — no LLM round-trip), accumulates results into `TurnOutcome`. Returns
  `CombatRound` if `template == "combat"`, else `Narrate`.
- [ ] T016 [US1] In `dispatcher.py`: implement `CombatRound` node — the one cyclic node.
  Calls `resolve_combat_round` via `call_engine()` once per visit; returns `CombatRound`
  (self-edge) while combat is still active, or `Narrate` once it ends (victory, defeat,
  or a successful `flee_combat`) — every round's result appended to `TurnOutcome.checks`
  (FR-012, no round skips the gate).
- [ ] T017 [US1] In `dispatcher.py`: implement `NarrativeFree` node — zero LLM calls,
  zero engine calls, passes straight to `Narrate` with no `TurnOutcome` (the player's
  action carries no mechanical stakes, or confidence was too low to guess — FR-004,
  FR-013).
- [ ] T018 [US1] In `dispatcher.py`: implement `Narrate` node — one `pydantic_ai.Agent`
  call (`Agent(..., name="pure_narrator")` — **(analyze fix L1)**), `output_type=Scene`,
  `toolsets=[]`. Receives `TurnOutcome` (if any) + `NarratorContext` as prompt content
  (not tool access) and returns `End[Scene]`. Reuses the existing `Scene`
  output-validator logic from `agent.py` (structural checks: non-empty narrative,
  choices present on non-terminal scenes).
- [ ] T019 [US1] In `dispatcher.py`: assemble the `pydantic_graph.Graph` wiring
  `ClassifyIntent` → `{MechanicalDispatch, NarrativeFree}` → `{CombatRound, Narrate}` →
  `Narrate` → `End`, per `data-model.md`'s node table.
- [ ] T020 [US1] In `src/gamebook_web/harness/agent.py` (or a new
  `harness/dispatcher_narrator.py`): create a class implementing the `NarratorBackend`
  Protocol (`harness/base.py`) whose `narrate(campaign_id, context)` runs the Phase-3
  graph and returns the resulting `Scene` — this is the new production narrator,
  replacing `PydanticNarrator`'s free-tool-use loop. `FakeNarrator` and
  `NarratorBackend` itself are unchanged (Constitution Principle II).
- [ ] T021 [US1] In `src/gamebook_web/api/app.py`: update `_configure_narrator` to
  construct the new dispatcher-based narrator (T020) instead of `PydanticNarrator` on
  the production path; `FakeNarrator` continues to be used for tests unchanged.
- [ ] T022 [US1] [P] Author `.claude/skills/ignarok/backbone.yaml` for the MVP checkpoint:
  the full `backbone` block (all Ignarok zones, `Malachar`, `victory_condition:
  {flag: malachar_defeated}`, `opening_location`), plus `probabilistic_encounters` for
  `stone_archway` (`archway_guardian`, `probability: 1.0`, `template: combat`) and one
  `risky_action`/`skill_check` zone (e.g. `dark_ravine`). Every other zone defaults to
  Layer 3 (absent from both `probabilistic_encounters` and `narrative_zones` — the
  incremental-migration path from research.md). Leave `reviewed_by`/`reviewed_at` unset
  (`null`) — they're only set by an actual human sign-off (T040), not by authoring the
  file.
- [ ] T023 **(analyze fix P1 — replaces the original "create FakeIntentClassifier" task)**
  [US1] [P] Set up `pydantic_ai` model-override test support for `ClassifyIntent` and
  `Narrate`: confirm/wire each node's `Agent` so tests can call
  `agent.override(model=FunctionModel(custom_fn))` (exact, assertable responses) or
  `TestModel()` (quick automatic-valid-output checks). **Do not** add a hand-rolled fake
  class — `FakeNarrator`'s queue pattern is for the `NarratorBackend` Protocol boundary
  (ADR-011), a different granularity than these two private in-graph agents; see
  `research.md`'s testing decision (added after `/speckit-analyze` checked this plan
  against the `pydantic-ai` skill's own guidance: *"Use `TestModel` for fast
  deterministic tests and `FunctionModel` for custom response logic"*).
- [ ] T024 [US1] [P] Write `tests/server/test_dispatcher.py`: seeded RNG, in-memory MCP
  server (matching `rules`/`combat`'s existing determinism convention), `FunctionModel`/
  `TestModel` overrides (T023) for `ClassifyIntent`/`Narrate` — one test per node:
  `ClassifyIntent` routing (confident → `MechanicalDispatch`, unconfident →
  `NarrativeFree`), `MechanicalDispatch` check execution against a `risky_action`
  template, `CombatRound` cycling (multi-round fight, verify no round is skipped),
  `NarrativeFree` passthrough (no engine calls made).
- [ ] T025 [US1] [P] Write an integration test in `tests/server/test_dispatcher.py` (or a
  sibling file): a full graph run for a `risky_action` and for a `combat` template
  produces a `Scene` whose narrated outcome is backed by a `TurnOutcome` entry for every
  claimed check — the automated, in-memory version of quickstart.md's Story 1 assertion.
- [ ] T026 **(analyze fix C1, new task)** [US1] [P] Write a test asserting the
  narration-call bound (SC-005 — "every mechanical-action turn resolves in a consistent,
  bounded number of narration steps, regardless of how many mechanical checks occur
  within it"): run a multi-round `combat` template through the graph and assert
  `Narrate`/the narration `Agent` is invoked **exactly once** for the whole turn,
  independent of how many times `CombatRound` cycled. T024's "no round is skipped" check
  proves completeness; this proves the bound on narration steps specifically — a
  distinct claim SC-005 makes.
- [ ] T027 [US1] Update `tool_trace_audit.py`'s `assert_tool_trace_consistency` call site:
  it now audits the **dispatcher's** own tool-call trace (belt-and-suspenders — the
  dispatcher is code, not an LLM, so this layer is now a lower-value safety net than it
  was against the narrator, but still catches a `MechanicalDispatch`/`CombatRound`
  implementation bug that skips a call it claims to have made).
- [ ] T028 [US1] Run quickstart.md's "Story 1" and "Story 1 (extended encounter)" live
  validation against at least two different models (e.g. `anthropic:claude-opus-4-8` and
  a cheaper `openai:*` or `openrouter:*` model, matching ADR-033's own two-model
  reproduction method) — record results as the MVP acceptance evidence (SC-001).

**Checkpoint**: User Story 1 is fully functional and independently testable — the
integrity guarantee holds, live-verified across models. This is the MVP; Stories 2–4 add
value on top without it.

---

## Phase 4: User Story 3 - A player can act in their own words without being boxed into a menu (Priority: P2)

**Goal**: Free text with no mechanical stakes is narrated freely; free text with
ambiguous mechanical stakes defaults to free narration rather than guessing. Most of the
mechanism (the `ClassifyIntent` confidence gate, the `NarrativeFree` node) already exists
from Phase 3 — this phase is about deliberately exercising and tuning it, not building
new infrastructure.

**Independent Test**: [quickstart.md](./quickstart.md) — "Story 3."

### Implementation for User Story 3

- [ ] T029 [US3] Add a `narrative_zones` entry to `backbone.yaml` for at least one fully
  free zone (e.g. `foothills`) — a zone with no `probabilistic_encounters`, explicitly
  marked Layer 3 rather than merely defaulting to it, to exercise the explicit path.
- [ ] T030 [US3] [P] Write tests in `tests/server/test_dispatcher.py` (or a sibling):
  free text with no mechanical stakes routes to `NarrativeFree` with zero engine calls;
  free text with clear mechanical stakes routes to `MechanicalDispatch`; deliberately
  ambiguous free text (confidence near/below threshold) routes to `NarrativeFree`, never
  to a guessed mechanical consequence (the edge case in spec.md).
- [ ] T031 [US3] Tune and document `ClassifyIntent`'s confidence threshold constant in
  `dispatcher.py` — pick and justify a specific value (e.g. `0.7`), record the rationale
  as a comment referencing FR-004's "when unsure, never guess" requirement.
- [ ] T032 **(analyze fix C2, new task)** [US3] Run a live-validation pass for SC-003
  ("players attempting an unanticipated free-text action receive a sensible narrative
  continuation... in effectively all attempts"): against a real model, send a varied
  batch of unanticipated/ambiguous free-text actions (not just T030's couple of unit
  cases) and confirm none error out or produce a forced menu — the same empirical bar
  T028 applies to SC-001, applied here to SC-003. Record results as acceptance evidence.

**Checkpoint**: User Stories 1 and 3 both hold — mechanical integrity and free-text play
coexist.

---

## Phase 5: User Story 2 - The same adventure never plays out exactly the same way twice (Priority: P2)

**Goal**: Two playthroughs share the same backbone (zones, boss, victory condition) but
differ in which probabilistic encounters appear, and a determination made earlier in a
playthrough is remembered, not re-rolled.

**Independent Test**: [quickstart.md](./quickstart.md)'s implied Story 2 scenario (two
playthroughs comparison — add explicit steps if not already covered by Story 1's
`stone_archway`/`dark_ravine` content).

### Implementation for User Story 2

- [ ] T033 [US2] In `dispatcher.py` (a pre-step in `MechanicalDispatch` or a new
  `EnterZone` check at graph start): on first entry to a zone with
  `probabilistic_encounters`, roll each entry once against its `probability` and persist
  the result to `World.flags["encounter.<zone>.<encounter_id>"]` via `update_world`
  (`call_engine()`, per `data-model.md`'s state-transition table).
- [ ] T034 [US2] Implement the "remembered" read path: before rolling, check whether
  `World.flags` already has an entry for `<zone>.<encounter_id>` in the current
  playthrough — if so, reuse it rather than re-rolling (FR-007).
- [ ] T035 [US2] [P] Expand `backbone.yaml`'s `dark_ravine` entry to two competing
  probabilistic encounters (`cave_bat` 0.4, `rogue_goblin` 0.3, per ADR-033's own
  example) so variance is observable, not just present/absent for a single encounter.
- [ ] T036 [US2] [P] Write tests: re-entering the same zone twice in one playthrough
  (same `World`/`campaign_id`) yields the same presence/absence both times; two
  independent playthroughs (fresh `World.flags`, different seeded RNG) may differ.
- [ ] T037 [US2] Run a manual two-playthrough validation of Ignarok (start twice, same
  adventure) confirming the shared backbone (SC-002) while noting which encounters
  differed — record as acceptance evidence.

**Checkpoint**: User Stories 1, 2, and 3 all hold together — integrity, replay variance,
and free text.

---

## Phase 6: User Story 4 - An adventure's author can trust it plays safely before anyone else does (Priority: P3)

**Goal**: New adventures reuse the shared template library instead of inventing rules,
and a structural check catches authoring mistakes before a human review gate.

**Independent Test**: [quickstart.md](./quickstart.md) — "Structural validation."

### Implementation for User Story 4

- [ ] T038 [US4] [P] Write `tests/qa/test_adventure_structure.py` (matching this repo's
  existing `tests/qa/` plugability-audit style): validates every adventure module's
  `backbone.yaml` against `templates.yaml` per `contracts/adventure-module-schema.md`'s
  rules — every referenced zone exists in `zones`, every `template` reference resolves,
  every `probability` is in `[0.0, 1.0]`, no zone is in both `probabilistic_encounters`
  and `narrative_zones`, every encounter's `params` match its template's declared
  `ParamSpec`s, **and** `reviewed_by`/`reviewed_at` are both present — reported as a
  distinct failure reason from a structural error (**analyze fix U1** — FR-011's gate is
  now checked, not just documented).
- [ ] T039 [US4] Add `tests/qa/test_adventure_structure.py` to the mandatory pre-merge
  suite alongside the existing plugability audit (document the command in `CLAUDE.md`'s
  Build/test/run section, next to `test_dependencies.py`/`test_isolation.py`).
- [ ] T040 [US4] **(analyze fix U1 — was "document the human-review requirement"; now
  also performs it)** Once `backbone.yaml`'s content (T022, T029, T035) has actually been
  reviewed by a human, set `reviewed_by`/`reviewed_at` in the file and note in
  `contracts/adventure-module-schema.md` (or a new
  `specs/009-deterministic-turn-dispatcher/checklists/adventure-release.md`) that T038's
  passing validator run is necessary but never sufficient — the two fields record that a
  human looked, not that the review was thorough.
- [ ] T041 [US4] [P] Write a test proving the template library is genuinely shared, not
  per-module: construct a second, minimal hypothetical `backbone.yaml` referencing
  `templates.yaml`'s existing templates with no new template definitions, and confirm it
  validates (SC-004 — authoring without inventing new mechanical rules).

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Regression safety and documentation hygiene once the above are in place.

- [ ] T042 [P] Run the full regression suite:
  `uv run pytest tests/engine tests/server tests/qa -q` and the plugability audit
  (`uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q`) — confirm
  green.
- [ ] T043 [P] Update `docs/CONTRACTS.md`'s cross-references and `CLAUDE.md`'s Status
  section once this merges (epic decomposition table, ADR-033 status `Proposed` →
  `Accepted`).
- [ ] T044 [P] Record a Learning Lesson if implementation surfaced anything unanticipated
  (this repo's strong convention — see `auth_redirect_flows_require_live_testing.md` for
  the most recent precedent) — e.g. anything about `pydantic_graph`'s actual behavior
  under this project's async/toolset stack that the plan didn't anticipate.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks all user stories** — the MCP
  contract extension (T004–T006), the adventure-structure data model (T007–T010), and
  the empty narrator toolset (T012–T013) are load-bearing for every story.
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 3 (Phase 4)**: Depends on Foundational **and** User Story 1 (the
  `ClassifyIntent`/`NarrativeFree` nodes it exercises are built in Phase 3) — mostly
  coverage/tuning, not new infrastructure.
- **User Story 2 (Phase 5)**: Depends on Foundational **and** User Story 1 (needs the
  working `MechanicalDispatch` node to hang the encounter-rolling step off of). Can
  proceed in parallel with Phase 4 — disjoint files.
- **User Story 4 (Phase 6)**: Depends on Foundational only, technically — the validator
  only needs the Pydantic models (T007–T009) to exist. In practice, sequence it after
  Phase 3 so there's real `backbone.yaml` content worth validating, and after Phases 4–5
  if T040's actual human sign-off is meant to cover their `backbone.yaml` additions too.
- **Polish (Phase 7)**: Depends on whichever stories are in scope for the change being
  shipped.

### Parallel Opportunities

- T002 and T003 (Setup) can run alongside T001.
- T006 (MCP integration tests) can run alongside T007/T008 (Pydantic models) — disjoint
  files.
- T007 and T008 (Foundational Pydantic models) are parallel — different classes, same
  file, no ordering dependency between them (sequence the actual edits, but no logical
  dependency).
- Within User Story 1: T022 (backbone.yaml), T023 (TestModel/FunctionModel wiring),
  T024–T026 (tests) can all start once T014–T021 exist, in parallel with each other.
- User Story 2 (Phase 5) and User Story 3 (Phase 4) touch disjoint files and can proceed
  in parallel once User Story 1 is done.
- T042, T043, T044 (Polish) are parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (User Story 1).
2. **STOP and VALIDATE**: run `quickstart.md`'s Story 1 scenarios against at least two
   different models. This alone restores Constitution Principle I and closes both of
   ADR-033's empirical reproductions.
3. This satisfies FR-001, FR-002, FR-003 (recognize mechanical vs. narrative actions —
   the classifier), FR-004 (default to narrative-free when unsure), FR-012, FR-013,
   SC-001, and SC-005 (T026's narration-call-count bound).

### Incremental Delivery

1. Setup + Foundational → contract extended (with direct test coverage), narrator has
   zero tools, adventure-structure models exist (including the FR-011 review-gate
   fields).
2. User Story 1 → integrity guarantee restored and live-verified (MVP, mergeable).
3. User Story 3 → free-text coverage deliberately exercised, tuned, and live-validated
   for breadth (SC-003).
4. User Story 2 → replay variance via probabilistic encounters.
5. User Story 4 → structural validator (including the FR-011 gate) + shared-template-
   library proof + the actual human sign-off once content is ready.
6. Polish → full regression, docs, learning lesson if warranted.

### Parallel Team Strategy

With multiple developers, after Foundational is done: one on User Story 1 (must land
first — everything else depends on it), then split User Story 2 and User Story 3 across
two people in parallel once US1 lands, with User Story 4 picked up by whoever frees up
first (it only needs the Foundational data model, not US1's graph) — though its final
task (T040, the actual sign-off) should wait until the content it's reviewing is done.
