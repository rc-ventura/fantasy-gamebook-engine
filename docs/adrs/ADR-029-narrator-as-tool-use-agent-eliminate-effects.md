# ADR-029: Narrator as tool-use agent — eliminate effects[] pattern, restore Phase 1 interaction model

**Status**: Accepted
**Date**: 2026-06-30
**Related**: [ADR-001](./ADR-001-combat-sub-agent-delegation-pattern.md), [ADR-011](./ADR-011-phase2-harness-pydanticai-narrator-backend.md), [ADR-019](./ADR-019-allowlist-for-fabricated-number-detection.md)
**Depends on**: `006-cycle1-remediation` (complete)
**Supersedes**: The `effects[]` pattern introduced in ADR-011's web implementation

---

## Context

### The original model (Phase 1 — terminal)

In Phase 1 (Claude Code terminal), the narrator was a **tool-use agent**. During generation, it:

1. Read engine state via MCP tools (`read_character_sheet`, `read_world`, `read_summary`, `read_events`)
2. Applied changes via MCP tools (`roll_dice`, `update_character_sheet`, `register_event`, `update_world`)
3. Ran combat via MCP tools (`start_combat` → `resolve_combat_round` → `end_combat`)
4. Narrated with **real numbers** — because it had seen all tool results

The narrator never "emitted" a plan. It called tools directly and narrated from real results. Principle I
(Numbers Never in Prose) was enforced **by design** — the narrator knew the numbers because the engine
told it.

### The detour (Phase 2 — web)

The web implementation (ADR-011) introduced a different pattern: the narrator emits `Scene.effects[]` —
a list of engine operations to apply **after** generation. The API layer (`play.py:_apply_scene_effects`)
executes them via the `EFFECT_TO_MCP_TOOL` mapping.

This created problems that **did not exist in Phase 1**:

1. **Narrator writes blind**: it emits effects without seeing results. It writes "you strike the goblin"
   without knowing if the hit landed.
2. **Fabricated number risk**: the narrator may invent numbers in prose because it doesn't have real
   ones. Required `_scene_contains_fabricated_numbers` validator (ADR-019) as a post-hoc patch.
3. **Lockstep binding**: `EFFECT_TO_MCP_TOOL` + `EffectType` Literal + `test_scene_effects_contract.py`
   must stay synchronized — complexity that Phase 1 never needed.
4. **Combat is non-interactive**: effects[] are applied atomically after narration. The player cannot
   test luck per round or flee mid-combat. Required `combat_subagent.py` and explicit `POST /combat/round`
   endpoint as workarounds.
5. **Validator is heuristic**: `_scene_contains_fabricated_numbers` uses a denylist (`_RESULT_KEYS`) and
   a regex — both bypassable (ADR-019 acknowledged this).

### Root cause

The detour happened because PydanticAI's `output_type=Scene` (structured output) encourages "emit a
plan, execute later" thinking. The terminal had no `output_type` — Claude Code did tool-use naturally.
The web implementation conflated structured output with deferred execution.

**Structured output and deferred execution are independent concerns.** The narrator can return a
structured `Scene` (narrative + choices) AND call tools during generation. The `output_type` constrains
the final return value, not the tool-use behavior.

---

## Decision

Restore the Phase 1 interaction model in the web stack: **the narrator is a tool-use agent that calls
MCP tools directly during generation**. Eliminate the `effects[]` pattern entirely.

### What changes

| Component | Before | After |
|---|---|---|
| `Scene` model | `narrative + choices + effects[]` | `narrative + choices` (effects removed) |
| `Effect` model | `type: EffectType + params: dict` | Removed |
| `EFFECT_TO_MCP_TOOL` | 9-type mapping | Removed |
| `EffectType` Literal | Closed enum | Removed |
| `_apply_scene_effects` | API executes effects post-narration | Removed — narrator calls tools during generation |
| `_build_tool_args` / `_CHANGES_WRAPPED` | Effect-to-tool arg transformation | Removed |
| `_scene_contains_fabricated_numbers` | Post-hoc validator | Removed — narrator sees real numbers, doesn't fabricate |
| `_RESULT_KEYS` denylist | Fabricated number detection | Removed |
| `combat_subagent.py` | Separate agent for combat | Removed — narrator calls combat tools directly |
| `POST /combat/round` | Explicit stepwise combat | Removed — combat runs inside the turn |
| `POST /combat/flee` | Explicit flee | Removed — flee is a narrator choice |
| `CONTRACTS.md §10` | Scene with effects[] | Scene with narrative + choices only |
| `test_scene_effects_contract.py` | Lockstep parity test | Removed |
| `TurnResponse.effects_applied` | List of applied effects | Removed |

### What stays

| Component | Why |
|---|---|
| `Scene` structured output | PydanticAI `output_type=Scene` — narrative + choices, validated |
| `NarratorBackend` protocol | Swap boundary #3 — `PydanticNarrator` / `FakeNarrator` |
| MCP toolset | Same 18 tools, same contract |
| `_check_terminal_state` | API still checks post-narration state for death/victory |
| `output_validator` | Still useful for narrative quality (empty prose, missing choices) — not for fabricated numbers |

### Narrator behavior (restored Phase 1 model)

```
POST /turn
  → narrator agent runs with MCP toolset
  → reads state: read_character_sheet, read_world, read_summary, read_events
  → if combat: start_combat → resolve_combat_round (×N) → end_combat
  → applies changes: roll_dice, update_character_sheet, register_event, update_world
  → narrates with REAL numbers (seen from tool results)
  → returns Scene(narrative, choices) — changes already applied via MCP
  → API refreshes state, checks terminal conditions, returns response
```

### Combat: auto-resolved (no SSE)

Combat runs **inside the turn** via direct MCP tool calls. The narrator calls `start_combat` →
`resolve_combat_round` (×N) → `end_combat` during generation. No SSE, no explicit endpoints, no player
input mid-combat.

"Test luck" becomes a **pre-combat decision** — the narrator offers choices before the fight: "You face
a goblin. Do you want to test luck each round?" The player's choice is passed as `TurnRequest.choice`,
and the narrator uses it for all rounds.

Fleeing becomes a **narrator choice** — "Do you fight or flee?" before combat starts. If the player
chooses flee, the narrator calls `flee_combat` instead of starting combat.

**Trade-off (not equivalence)**: Phase 1 WAS interactive per-round — the combat sub-agent
asked the player each round via stdout/stdin ("test luck? y/n"). The web stack cannot pause
`agent.run()` mid-generation to accept player input, so per-round interactivity is intentionally
dropped. This is a deliberate simplification for the initial port. See Condition 2 under
"Conditions that invalidate this decision" — if per-round interaction becomes a hard requirement,
Alternative E (deterministic `run_combat` tool + SSE + `choice_queue`) is the upgrade path.

### Skills: direct injection (core fix) vs SkillsCapability (optional)

The core fix does **not** require `SkillsCapability`. The system prompt in `agent.py:118-126`
already injects `game-master/SKILL.md` content directly (`_load_adventure_lore()` pattern).
The only change needed for the core fix is updating the system prompt to instruct direct tool use
instead of emitting `effects[]`.

`SkillsCapability` (from the community package `pydantic-ai-skills`) is an **optional enhancement**
that makes the skill files the single authoritative source for both terminal and web. It carries
risk: community package, not PydanticAI core, stability unproven. It is **deferred** — evaluated
separately after the core fix lands.

`combat-sub-agent/SKILL.md` can be loaded via `SubAgentCapability` if combat delegation is desired
(ADR-001 pattern). Or the narrator calls combat tools directly — simpler, fewer LLM calls. This is
an additive choice; the architecture supports both. Also deferred.

### Turn endpoint simplification

```python
# ANTES (play.py take_turn):
scene = await narrator.narrate(campaign_id, ctx)  # emits effects[]
effects_applied = await _apply_scene_effects(scene.effects, toolset, ...)  # execute after
character = await call_engine(toolset, "read_character_sheet")  # refresh
world = await call_engine(toolset, "read_world")
await _check_terminal_state(campaign_id, character, world, toolset, registry)

# DEPOIS:
scene = await narrator.narrate(campaign_id, ctx)  # tools already called during generation
character = await call_engine(toolset, "read_character_sheet")  # refresh post-narration
world = await call_engine(toolset, "read_world")
await _check_terminal_state(campaign_id, character, world, toolset, registry)
```

The turn endpoint shrinks. `_apply_scene_effects`, `_build_tool_args`, `_CHANGES_WRAPPED` all removed.

---

## Atomicity trade-off

The effects[] pattern had one advantage: **atomicity**. If the Scene was invalid, no effects were
applied — the engine state was untouched. With direct tool use, the narrator may apply changes
mid-generation that can't be rolled back.

### Mitigations

1. **`roll_dice` is pure**: no state change, safe under any retry.
2. **`register_event` is append-only**: duplicate events on retry are acceptable (idempotent from
   the story perspective).
3. **`output_validator` catches output issues**: if the narrator returns empty prose or no choices,
   `ModelRetry` fires. The state may have changed, but the narrator regenerates with the updated
   state — which is correct (regeneration should account for what already happened).
4. **`_check_terminal_state` runs post-narration**: death and victory are still detected by the API.
5. **Prerequisite — verify `update_character_sheet` mutation semantics**: the idempotency claim
   depends on whether the tool takes set-based changes (`{stamina_current: 8}`) or delta-based
   (`{stamina_delta: -2}`). If delta-based, a `ModelRetry` could apply the delta twice. This must
   be audited against `src/gamebook/mcp/server.py` before the migration lands. If delta-based,
   the narrator must read current state before mutating (already part of the tool-use flow) and
   pass the absolute target value.
6. **Combat is the main risk**: `start_combat` creates state, `resolve_combat_round` mutates
   stamina. If the narrator starts combat but produces an invalid Scene, a partial combat state
   exists. Mitigation: the narrator sees combat results during generation — if it called
   `start_combat`, the skill instructs it to call `end_combat` before returning the Scene. An
   `output_validator` rule can enforce this: Scene with no choices must have no active combat
   (check world state).

### Net assessment

Phase 1 accepted this trade-off for years. The terminal narrator called tools directly and never had
rollback. The atomicity concern is real but manageable — and the benefit (Principle I by design, no
validator, no lockstep) outweighs it.

---

## ADR-018 (per-campaign isolation) — implementation status as of spec 007

**ADR-018 was NOT implemented by spec 006.** This is a load-bearing precondition for enabling `PydanticNarrator` in any multi-account deployment.

### Current state (post-007, 2026-06-30)

All `call_engine(...)` calls in `play.py` pass **no `campaign_id`**. The MCP subprocess launched by `app.py` at startup is shared across all campaigns; it reads/writes state from a single engine storage instance determined at server startup. There is **no per-campaign engine isolation**.

This means:
- In single-account / single-campaign deployments (dev, smoke tests): no observable impact.
- In multi-account deployments: narrator tool calls on campaign A can read and write state belonging to campaign B. This is the A01 breach originally identified in the 006 SDD review.

### Release gate

**`PydanticNarrator` must NOT be enabled (i.e., `ANTHROPIC_API_KEY` must NOT be set) in any multi-account or multi-campaign deployment until ADR-018 is implemented.** The `FakeNarrator` is the default and is safe because it makes no engine tool calls.

### What ADR-018 implementation requires (tracked to slice 004)

1. `mcp_host.py`: `storage_factory` — accepts `campaign_id`, returns per-campaign `StorageBackend`.
2. `play.py`: `call_engine(toolset, tool_name, campaign_id=campaign_id, ...)` on every engine call.
3. `app.py`: per-request toolset scoping (one subprocess per campaign, or campaign_id forwarded to the engine).

Until those three changes land, the narrator tool-use loop runs against a shared engine instance.

### Why this is documented here and not fixed

Per the user decision during spec 007 SDD cycle-1 review (item 2): implement items 1, 3, 4, 5, 6 in code; for item 2 (ADR-018 isolation), **skip implementation and document current state**. The fix is deferred to slice 004.

---

## Relationship to spec 006

**This ADR is post-006.** Spec 006 (cycle-1 remediation) must land first:

| 006 item | Why it must land first |
|---|---|
| Multi-tenant engine (ADR-018) | Narrator calls tools with `campaign_id` — must be in place |
| Security fixes (A01, A07, A04) | Can't build new architecture on CRITICAL vulnerabilities |
| ADR-019 allowlist | Hardens the current effects[] system while the replacement is built |
| ADR-028 victory path fix | Needed until explicit combat endpoints are removed |
| `combat_subagent.py` tests (SC-027) | Proves the sub-agent pattern before deciding keep/remove |
| Dep upper bounds (FR-049) | Any new deps (none required for core fix) enter with bounds |

### What becomes moot after ADR-029

| 006 item | Status after ADR-029 |
|---|---|
| ADR-019 allowlist (`_ALLOWED_EFFECT_PARAMS`) | Moot — no effects[] to validate |
| `test_scene_effects_contract.py` | Removed — no lockstep to test |
| `POST /combat/round` victory fix (ADR-028 of spec 006) | Moot — endpoint removed |
| `combat_subagent.py` tests (SC-027) | Evolved or removed |

This is acceptable: 006 hardens the current system; ADR-029 replaces it. The hardening work is not
wasted — it makes the system safe in the interim.

---

## Alternatives considered

### Alternative A: Keep effects[] pattern, add SubAgentCapability for combat only

Combat delegated to sub-agent (direct tool use), non-combat stays as effects[].

**Why not chosen**:
- Two interaction models in one system — complexity.
- Non-combat turns still write blind — fabricated number risk remains for non-combat.
- Validator, lockstep, and `_apply_scene_effects` all remain.
- Half-measure: fixes combat but not the root cause.

### Alternative B: Effects[] with SubAgentCapability + SSE for interactive combat

The previous version of this ADR (before renumbering to 029).

**Why not chosen**:
- SSE adds transport complexity (queues, connection management, choice endpoint).
- SubAgentCapability for combat = 10+ LLM calls per fight (expensive, slow).
- Still keeps effects[] for non-combat — doesn't solve the root cause.
- Over-engineered for a problem that Phase 1 solved simply.

### Alternative C: Claude Code Agent SDK (native skills, Claude-only)

Use the Agent SDK programmatically — skills load natively, tool-use loop identical to Phase 1.

**Why not chosen**:
- **Claude-only** — loses model agnosticism (ADR-011).
- No `output_type=Scene` — structured output parsing is manual.
- No `output_validator` / `ModelRetry` — loses output quality gates.
- No `deps_type` — loses dependency injection.

### Alternative D: Narrator as tool-use agent + SubAgentCapability for combat delegation

Same as the decision, but with combat delegated to a sub-agent (ADR-001 pattern) instead of the
narrator calling combat tools directly.

**Why not chosen as primary**:
- More LLM calls per combat (sub-agent is a separate agent run).
- The narrator can call combat tools directly — simpler, cheaper.
- **Kept as option**: if combat narration quality is better with a dedicated sub-agent,
  `SubAgentCapability` with `combat-sub-agent/SKILL.md` can be added later. The architecture supports
  it; it's an additive change.

### Alternative E: Deterministic `run_combat` tool + SSE + Queue (upgrade path for interactive combat)

If per-round combat interaction becomes a hard requirement (Condition 2), the correct upgrade path
is **not** SubAgentCapability (Alternative B) — it is a deterministic `run_combat` tool registered
on the narrator agent, combined with SSE for event streaming and an `asyncio.Queue` for player
input.

```python
@narrator_agent.tool
async def run_combat(ctx: RunContext[NarratorDeps], combat_id: str) -> CombatResult:
    """Deterministic combat loop — no LLM in the combat loop, just MCP calls."""
    event_queue = ctx.deps.event_queue
    choice_queue = ctx.deps.choice_queue
    while True:
        outcome = await call_engine(ctx.deps.toolset, "resolve_combat_round",
                                     combat_id=combat_id)
        await event_queue.put({"type": "round", "outcome": outcome})
        if outcome.get("ended"):
            break
        # Pause and wait for player input (test luck? flee?)
        choice = await choice_queue.get()
        if choice.get("flee"):
            flee_result = await call_engine(ctx.deps.toolset, "flee_combat",
                                             combat_id=combat_id)
            await event_queue.put({"type": "flee", "result": flee_result})
            break
    final = await call_engine(ctx.deps.toolset, "end_combat", combat_id=combat_id)
    await event_queue.put({"type": "final", "result": final})
    return CombatResult(**final)
```

**Why this is the correct upgrade path (not SubAgentCapability)**:
- **Zero LLM calls for combat orchestration**: the `while` loop is deterministic Python. The narrator
  calls `run_combat` as a single tool, receives `CombatResult`, narrates with real numbers. Compare
  with SubAgentCapability: 10+ LLM calls per fight (one per round for the sub-agent to decide what
  to do).
- **Instant round events**: SSE streams `RoundOutcome` as soon as the engine computes it — no LLM
  latency between rounds.
- **Player input via `choice_queue`**: the tool pauses on `await choice_queue.get()`. The client
  sends choices via `POST /combat/{id}/choice`. This is the HTTP equivalent of Phase 1's
  stdout/stdin interaction.
- **No community dependency**: `run_combat` is a plain PydanticAI tool. No `subagents-pydantic-ai`
  needed.

**Transport layer (SSE + POST)**:
- `GET /campaigns/{id}/turn/stream` — SSE endpoint. Opens connection, runs narrator agent, streams
  events from `event_queue` to the client.
- `POST /campaigns/{id}/combat/{combat_id}/choice` — receives player decisions, pushes to
  `choice_queue`.

**Why not chosen now (deferred to future ADR)**:
- Adds transport complexity: SSE connection management, `asyncio.Queue` lifecycle, choice endpoint,
  client-side `EventSource` + parallel POST.
- The initial port (ADR-029 decision) should land first and prove the tool-use model. Interactive
  combat is an additive upgrade — `run_combat` tool replaces the narrator's direct combat tool calls,
  SSE replaces the synchronous HTTP response. The rest of the architecture is unchanged.
- If adopted, this would be a new ADR (e.g. ADR-030) that extends ADR-029, not a modification to it.

---

## Consequences

### Positive

- **Principle I by design**: narrator sees real numbers during generation. No fabrication risk. No
  post-hoc validator needed.
- **Eliminates complexity**: `EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect`, `_apply_scene_effects`,
  `_build_tool_args`, `_CHANGES_WRAPPED`, `_scene_contains_fabricated_numbers`, `_RESULT_KEYS` — all
  removed.
- **Restores Phase 1 parity**: web narrator behaves like terminal narrator. Single source of truth
  (`game-master/SKILL.md`).
- **Simplifies API**: `take_turn` shrinks. Explicit combat endpoints removed. `combat_subagent.py`
  removed.
- **Simplifies contract**: `Scene` = narrative + choices. `CONTRACTS.md §10` shrinks.
- **Skills drive behavior**: `SkillsCapability` loads `game-master/SKILL.md` — same file as Phase 1.

### Trade-offs

- **No atomicity**: narrator applies changes mid-generation. Invalid Scene → state already changed.
  Mitigated by tool safety + `output_validator` + `_check_terminal_state`.
- **No per-round combat interaction**: "test luck" is pre-combat, not per-round. Fleeing is pre-combat.
  This is a deliberate regression from Phase 1's round-by-round interactivity — accepted as the cost
  of architectural simplicity. Condition 2 defines the threshold for reversing this decision.
- **FakeNarrator refactor**: `base.py` `_DEFAULT_OPENING_SCENE` and `_DEFAULT_FOLLOWUP_SCENE` both carry
  `effects[]`. Every test that asserts `TurnResponse.effects_applied` must be rewritten. This is
  non-trivial test churn — estimate 1-2 days of test refactor. Must be scoped in the spec.
- **Contract change**: `TurnResponse.effects_applied` removed. `CONTRACTS.md §10` rewritten. Frontend
  `TurnResponse` type updated. `test_scene_effects_contract.py` removed.
- **`update_character_sheet` mutation audit required** before Phase 2 of migration (see Atomicity
  section above). If delta-based, narrator system prompt must enforce read-before-write.

### Conditions that invalidate this decision

1. Atomicity proves critical — narrator makes wrong calls mid-generation that corrupt state
   unrecoverably.
2. Per-round combat interaction becomes a requirement — SSE + deterministic `run_combat` tool +
   `choice_queue` needed (see Alternative E; would be a new ADR-030 extending this one).
3. PydanticAI tool-use loop proves unreliable for multi-step tool chains (combat, multi-effect turns).

---

## Migration path

**Slice 007 (post-006)**. Phased rollout. `SkillsCapability` is NOT in this migration — it is
an optional enhancement evaluated separately. The core fix requires no community packages.

**Pre-condition**: audit `update_character_sheet` mutation semantics (`src/gamebook/mcp/server.py`)
before Phase 2. Confirm set-based or delta-based; update system prompt if delta-based.

1. **Phase 1 — system prompt change only**: Update `agent.py` system prompt to instruct direct
   tool use ("call MCP tools during generation, narrate with real results, return Scene with
   empty effects[]"). No code changes to Scene model or play.py yet. The narrator may still emit
   effects[] (it's not yet an error). Validate via integration test that narrator calls tools
   during generation and produces real-number narrative.
2. **Phase 2 — remove effects[] from Scene**: Remove `effects` field from `Scene` model. Remove
   `_apply_scene_effects`, `_build_tool_args`, `_CHANGES_WRAPPED` from `play.py`. Update
   `FakeNarrator` default scenes to `Scene(narrative, choices)`. Update all tests asserting
   `TurnResponse.effects_applied`. Estimate: 1-2 days test refactor.
3. **Phase 3 — remove scaffolding**: Remove `EFFECT_TO_MCP_TOOL`, `EffectType`, `Effect` from
   `scene.py`. Remove `_scene_contains_fabricated_numbers`, `_RESULT_KEYS` from `agent.py`.
   Simplify `output_validator` to narrative quality only (empty prose, missing choices).
   Remove `test_scene_effects_contract.py`.
4. **Phase 4 — remove explicit combat endpoints**: Remove `combat_subagent.py`. Remove
   `POST /combat/round`, `POST /combat/flee`. Remove `combat.py` router. Combat now runs
   inside `take_turn` via narrator direct tool calls.
5. **Phase 5 — contract + frontend update**: Update `CONTRACTS.md §10` (Scene contract — narrative
   + choices only). Remove `TurnResponse.effects_applied`. Update frontend `TurnResponse` type.
   Update API integration tests.

---

## References

- [ADR-001 — Combat sub-agent delegation pattern](./ADR-001-combat-sub-agent-delegation-pattern.md)
- [ADR-011 — Phase-2 harness: PydanticAI narrator backend](./ADR-011-phase2-harness-pydanticai-narrator-backend.md)
- [ADR-019 — Allowlist for fabricated-number detection](./ADR-019-allowlist-for-fabricated-number-detection.md)
- `.claude/skills/game-master/SKILL.md` — Phase 1 narrator behavior (reused via SkillsCapability)
- `.claude/skills/combat-sub-agent/SKILL.md` — Phase 1 combat sub-agent (optional via SubAgentCapability)
- `src/gamebook_web/harness/agent.py` — current narrator + validator (to be simplified)
- `src/gamebook_web/harness/scene.py` — current Scene + EFFECT_TO_MCP_TOOL (to be simplified)
- `src/gamebook_web/harness/combat_subagent.py` — current combat sub-agent (to be removed)
- `src/gamebook_web/api/play.py` — current turn endpoint (to be simplified)
- `src/gamebook_web/api/combat.py` — explicit combat endpoints (to be removed)
- `.specify/memory/constitution.md` — Principle I (Numbers Never in Prose)
- `docs/CONTRACTS.md §10` — Scene contract (to be updated)
- [pydantic-ai-skills](https://github.com/DougTrajano/pydantic-ai-skills) — SkillsCapability community package
