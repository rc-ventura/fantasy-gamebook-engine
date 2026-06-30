# Tasks: Narrator Tool-Use Refactor

**Input**: Design documents from `specs/007-narrator-tool-use-refactor/`

**Feature**: `007-narrator-tool-use-refactor` | **Depends on**: `006-cycle1-remediation` merged

**Tech stack**: Python 3.12, PydanticAI, FastAPI, FastMCP, Pydantic v2, pytest, TypeScript (frontend)

**Migration phases** (from ADR-029): 5 phases, each independently mergeable as internal
feature-branch commits. **IMPORTANT (Principle III)**: Phases 1–4 MUST NOT be merged to `dev`
independently — only Phase 5 completion (CONTRACTS.md + frontend types updated) makes the
branch eligible for merge. Phases are mapped to user stories below.

**Tests note**: Tests are included where they change or must be deleted. No net-new test suite is
added — the _existing_ tests are updated to match the simplified model. One test file is entirely
rewritten (`test_scene_numbers.py`) and one is deleted (`test_scene_effects_contract.py`).

---

## Phase 1: Foundational — System Prompt Change

**Purpose**: Change the narrator's instruction from "emit effects[]" to "call tools directly."
This is the first change and the one that most changes narrator behaviour. The effects[] field
on Scene still exists in this phase — the narrator just won't emit it.

**Gate**: Verify the test baseline is green on `dev` (006 merged) before starting.

- [X] T001 Verify test baseline on `dev` branch: `uv run pytest -q` must be green before first commit
- [X] T002 Update `_NUMBERS_NEVER_IN_PROSE_RULE` and system prompt in `src/gamebook_web/harness/agent.py` — replace "emit effects[], engine executes them" with "call MCP tools during generation, narrate real results, return Scene(narrative, choices) with empty effects"
- [X] T003 Add active-combat detection instruction to narrator system prompt in `src/gamebook_web/harness/agent.py` — "if you detect an active combat in world state on retry, continue it (call resolve_combat_round) — never start a new combat while one is active" _(Acceptance: manual smoke test T039 must confirm a ModelRetry on active combat continues, not restarts, the fight)_
- [X] T004 Add pre-combat decision framing instruction to narrator system prompt in `src/gamebook_web/harness/agent.py` — narrator must offer "fight or flee?" choice _before_ calling start_combat, using TurnRequest.choice from the prior turn to decide

**Checkpoint Phase 1**: `uv run pytest -q` green. Narrator instructs tool-use; effects[] still accepted structurally but narrator won't emit them.

---

## Phase 2: US1 + US2 — Remove effects[] Execution Layer (Priority: P1)

**Goal**: Player receives narratives with real numbers. `effects[]` field and its entire execution
layer are removed from `Scene`, `play.py`, and `TurnResponse`.

**Independent Test**: Assert `Scene.model_fields` has no `effects` key. Assert `TurnResponse.model_fields` has no `effects_applied` key. Run `uv run pytest -q`.

### Implementation for US1 + US2

- [X] T005 [US1] Remove `effects` field from `Scene` in `src/gamebook_web/harness/scene.py` (keep `narrative`, `choices`, `narrative_not_empty` validator, `is_terminal` property)
- [X] T006 [US1] Remove `_apply_scene_effects`, `_build_tool_args`, `_CHANGES_WRAPPED` functions from `src/gamebook_web/api/play.py`
- [X] T007 [US1] Remove `effects_applied` field from `TurnResponse` in `src/gamebook_web/api/play.py`
- [X] T008 [US1] Remove `EFFECT_TO_MCP_TOOL` import and Step 4 effects-application block from `take_turn()` in `src/gamebook_web/api/play.py`
- [X] T009 [US1] Update `NarratorContext` docstring in `src/gamebook_web/harness/base.py` — remove "State changes happen ONLY via Scene.effects[]" claim; replace with "Narrator calls MCP tools directly during generation"
- [X] T010 [US1] Remove `effects=[]` from `_DEFAULT_OPENING_SCENE` in `src/gamebook_web/harness/base.py`
- [X] T011 [US1] Remove `effects=[]` from `_DEFAULT_FOLLOWUP_SCENE` in `src/gamebook_web/harness/base.py`
- [X] T012 [US2] Rewrite `tests/server/test_scene_numbers.py` — replace fabricated-number validator tests (which test the removed validator) with tool-use output tests: given a FakeNarrator that returns Scene(narrative, choices), assert no `effects_applied` in response and no `effects` in scene; keep any tests that verify structural Scene invariants (non-empty narrative, etc.)
- [X] T013 [US2] Verify `tests/server/test_api_play_loop.py` compiles and passes — fix any Scene constructions that include `effects=` kwarg (grep: `effects=[`)

**Checkpoint Phase 2**: `uv run pytest -q` green. `Scene.effects` and `TurnResponse.effects_applied` do not exist. Narratives from FakeNarrator have no effects field.

---

## Phase 3: US3 — Remove Explicit Combat Endpoints (Priority: P2)

**Goal**: Combat resolves inside `POST /turn`. `POST /combat/round` and `POST /combat/flee`
return 404. `combat_subagent.py` deleted.

**Independent Test**: `POST /campaigns/{id}/combat/round` and `POST /campaigns/{id}/combat/flee`
return 404. `uv run pytest -q` green.

**Note**: This phase can run in parallel with Phase 4 (US4) — they touch different files.

### Implementation for US3

- [X] T014 [P] [US3] Delete `src/gamebook_web/harness/combat_subagent.py` entirely
- [X] T015 [P] [US3] Delete `src/gamebook_web/api/combat.py` entirely
- [X] T016 [US3] Remove combat router import and `app.include_router(combat_router)` from `src/gamebook_web/api/app.py` (lines 142, 145)
- [X] T017 [US3] Remove `current_combat_id` field and `set_combat()` method from `src/gamebook_web/sessions/campaign.py` — these were only used by the now-deleted `combat.py` endpoints
- [X] T018 [US3] Remove any `set_combat()` calls remaining in `src/gamebook_web/api/play.py` (currently called after `start_combat` / `end_combat` effects — no longer applies)
- [X] T019 [US3] Verify no test fixtures in `tests/server/conftest.py` reference `combat_subagent` or `combat_router` (`grep -n "combat_subagent\|combat_router" tests/server/conftest.py`) — confirmed no references as of spec date; this task is a sanity check only
- [X] T020 [US3] Verify no test imports `from gamebook_web.api.combat import ...` or `from gamebook_web.harness.combat_subagent import ...`

**Checkpoint Phase 3**: `uv run pytest -q` green. `combat_subagent.py` and `combat.py` gone. `/combat/*` routes return 404.

---

## Phase 4: US4 — Remove Dead Scaffolding (Priority: P2)

**Goal**: Developer sees clean, simplified harness code with no deferred-execution artifacts.
7 named constructs removed: `EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect`, `_apply_scene_effects`
(done in Phase 2), `_build_tool_args` (done), `_scene_contains_fabricated_numbers`, `_RESULT_KEYS`.

**Independent Test**: `grep -r "EFFECT_TO_MCP_TOOL\|_scene_contains_fabricated_numbers\|_RESULT_KEYS\|EffectType" src/` returns zero hits.

**Note**: Can run in parallel with Phase 3 (US3) — touches different files.

### Implementation for US4

- [X] T021 [P] [US4] Remove `EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect` class from `src/gamebook_web/harness/scene.py` — only `Choice` and `Scene` remain
- [X] T022 [P] [US4] Remove `_scene_contains_fabricated_numbers`, `_RESULT_KEYS`, `_NUMBERS_NEVER_IN_PROSE_RULE` from `src/gamebook_web/harness/agent.py`
- [X] T023 [US4] Simplify `output_validator` in `src/gamebook_web/harness/agent.py` — keep only narrative quality checks (empty prose, missing choices on non-terminal scenes); remove fabricated-number detection logic
- [X] T024 [US4] Delete `tests/server/test_scene_effects_contract.py` — lockstep parity test for the now-deleted mapping; no replacement needed

**Checkpoint Phase 4**: `uv run pytest -q` green. Grep confirms all 7 constructs removed. `scene.py` contains only `Choice` and `Scene`.

---

## Phase 5: US5 — Contract + Frontend Update (Priority: P3)

**Goal**: `CONTRACTS.md §10`, frontend TypeScript types, and any remaining test/doc references
are updated. No `effects_applied` or `effects: list[Effect]` anywhere.

**Independent Test**: `grep -r "effects_applied" docs/CONTRACTS.md tests/ frontend/src/` returns
zero hits. `uv run pytest -q` green. Frontend type check passes.

### Implementation for US5

- [X] T025 [P] [US5] Update `docs/CONTRACTS.md §10` — rewrite Scene contract: `{narrative: str, choices: list[Choice]}` with no effects; update lifecycle description (narrator calls tools during generation, not after)
- [X] T026 [P] [US5] Update `docs/CONTRACTS.md §9` TurnResponse shape — remove `effects_applied` from the response fields table
- [X] T027 [P] [US5] Update frontend TypeScript `TurnResponse` type (in `frontend/src/api/` or equivalent) — remove `effects_applied` field
- [X] T028 [P] [US5] Update frontend TypeScript `Scene` type — remove `effects` field and any `Effect`/`EffectType` type definitions
- [X] T029 [US5] Remove any frontend component or debug panel that renders `effects_applied` (search `frontend/src/` for `effects_applied`)
- [X] T030 [US5] Run grep verification: `grep -r "effects_applied" docs/CONTRACTS.md tests/ frontend/src/` must return zero hits

**Checkpoint Phase 5**: All greps clean. Frontend type check passes. Full test suite green.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, ADR status update, quickstart verification.

- [X] T031 Run full test suite: `uv run pytest -q` — must be green with all phases complete
- [X] T032 Run plugability audit: `uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q` — must stay green (no engine changes, but verify)
- [X] T033 Run quickstart.md Phase 2–5 validation scripts to confirm structural assertions pass
- [X] T034 Update `docs/adrs/ADR-029-narrator-as-tool-use-agent-eliminate-effects.md` status from `Proposed` to `Accepted`
- [X] T035 [P] Update `CLAUDE.md` ADR table — mark ADR-029 as `Accepted`
- [X] T036 [P] Run `/sdd-qa` quality audit gate (constitution Development Workflow MUST — run in parallel with T037)
- [X] T037 [P] Run `/sdd-security` security audit gate (constitution Development Workflow MUST — run in parallel with T036)
- [X] T038 Run `/sdd-tech` as dispatching final review gate — depends on T036 + T037 completing (constitution Development Workflow MUST — no merge before this passes)
- [X] T039 **[Optional/manual smoke test]** SC-001 live-LLM verification: run quickstart.md End-to-End scenario with `ANTHROPIC_API_KEY` set — assert narrative contains no `effects_applied`, no `effects` field in scene, and narrative references values consistent with engine state; also verify a narrator retry on an active combat continues (not restarts) the fight — covers US1 AC-3 and SC-001

**Checkpoint Final**: All tests green, all greps clean, ADR-029 accepted, quickstart validated.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Foundational)**: No dependencies — start immediately after 006 merges
- **Phase 2 (US1+US2)**: Depends on Phase 1 — system prompt must change first
- **Phase 3 (US3)** and **Phase 4 (US4)**: Both depend on Phase 2 — can run **in parallel** with each other (touch different files)
- **Phase 5 (US5)**: Depends on Phase 3 + Phase 4 — contracts updated after all code deleted
- **Phase 6 (Polish)**: Depends on Phase 5 — final validation after everything lands

```
Phase 1 (system prompt)
    ↓
Phase 2 (remove effects[] — US1+US2)
    ↓          ↓
Phase 3      Phase 4     ← PARALLEL
(US3)        (US4)
    ↓          ↓
       Phase 5 (US5)
           ↓
       Phase 6 (Polish)
```

### User Story Dependencies

| Story | Depends on | Can start after |
|---|---|---|
| US1+US2 (P1) | Phase 1 complete | T004 |
| US3 (P2) | US1+US2 complete | T013 |
| US4 (P2) | US1+US2 complete | T013 |
| US5 (P3) | US3 + US4 complete | T024 |

### Files touched per phase

| Phase | Files changed | Files deleted |
|---|---|---|
| 1 | `agent.py` | — |
| 2 | `scene.py`, `play.py`, `base.py`, `test_scene_numbers.py`, `test_api_play_loop.py` | — |
| 3 | `app.py`, `campaign.py`, `play.py`, `conftest.py` | `combat_subagent.py`, `combat.py` |
| 4 | `scene.py`, `agent.py` | `test_scene_effects_contract.py` |
| 5 | `CONTRACTS.md`, `frontend/src/api/types*`, frontend components | — |
| 6 | `ADR-029.md`, `CLAUDE.md` | — |

---

## Parallel Opportunities

### Phases 3 + 4 in parallel (after Phase 2)

```bash
# In parallel — different files, no conflicts:
# Worker A (US3):
Task: "Delete combat_subagent.py" (T014)
Task: "Delete combat.py" (T015)
Task: "Remove combat router from app.py" (T016)
Task: "Remove current_combat_id from campaign.py" (T017)

# Worker B (US4):
Task: "Remove EFFECT_TO_MCP_TOOL, EffectType, Effect from scene.py" (T021)
Task: "Remove _scene_contains_fabricated_numbers from agent.py" (T022)
Task: "Simplify output_validator in agent.py" (T023)
Task: "Delete test_scene_effects_contract.py" (T024)
```

### Phase 5 parallel tasks

```bash
# All can start simultaneously:
Task: "Update CONTRACTS.md §10" (T025)
Task: "Update CONTRACTS.md §9 TurnResponse" (T026)
Task: "Update frontend TurnResponse type" (T027)
Task: "Update frontend Scene type" (T028)
```

---

## Implementation Strategy

### MVP (Phase 1 only — safe to ship, no breakage)

1. Complete Phase 1: system prompt change in `agent.py`
2. `uv run pytest -q` green
3. **STOP and VALIDATE**: narrator now instructs direct tool use. `effects[]` still accepted by
   `Scene` but narrator doesn't emit them. Safe intermediate state.

### Incremental Delivery

1. **Phase 1**: Prompt change → narrator uses tools → green tests ✅
2. **Phase 2**: Remove effects[] layer → US1+US2 done → green tests ✅
3. **Phase 3+4** (parallel): Remove combat endpoints + remove scaffolding → US3+US4 done ✅
4. **Phase 5**: Contract + frontend → US5 done → green tests + type check ✅
5. **Phase 6**: Polish + ADR accepted → slice complete ✅

Each phase is an independently committable unit on the feature branch. The branch merges to `dev` only after Phase 5 completes (Principle III — CONTRACTS.md must not lag behind code).

---

## Notes

- `[P]` = parallelizable (different files, no task dependencies)
- `[USn]` = maps to User Story n in `spec.md`
- PC-001 (mutation semantics audit) is already resolved in `research.md` — set-based confirmed
- `test_scene_numbers.py` is a **rewrite**, not a deletion — the file tests narrative quality and
  scene structure, which remain valid concerns even without the fabricated-number validator
- `test_scene_effects_contract.py` is a **deletion** — it tests lockstep parity between
  `EFFECT_TO_MCP_TOOL` keys and `EffectType` literals, both of which are removed
- `CampaignState.current_combat_id` (T017) is only read by the deleted `combat.py` — safe to remove
- Frontend changes (T027-T029) may have zero impact if the SPA doesn't render `effects_applied`;
  type-check confirms correctness either way
