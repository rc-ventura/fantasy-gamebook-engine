# Implementation Plan: Deterministic Turn Dispatcher (Pure Narrator)

**Branch**: `009-deterministic-turn-dispatcher` | **Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-deterministic-turn-dispatcher/spec.md`,
implementing the architecture decided in
[ADR-033](../../docs/adrs/ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md).

## Summary

Split the narrator's single free-tool-use LLM call into a three-stage pipeline — an
intent classifier (LLM, structured output, no tools), a deterministic dispatcher (code,
zero LLM calls, calls MCP tools directly), and a pure narrator (LLM, `output_type=Scene`,
zero tools) — so a hero's stats can never be changed by an invented outcome, regardless
of which AI model narrates. This closes an empirically-proven gap: ADR-033 reproduced
narrator-fabricated stat changes with both a cheap model (gpt-4o-mini) and the strongest
non-reasoning model available (gpt-5-chat-latest), proving the current architecture
(ADR-029's "narrator calls tools directly") is not sufficient — the fix must be
structural, not model-dependent. The pipeline is implemented as a single
`pydantic_graph.Graph` (already a transitive dependency via `pydantic-ai>=2.0.0`, no new
package) behind the existing `NarratorBackend` Protocol, so no FastAPI route changes.
The adventure module gains a three-layer structure (fixed backbone / probabilistic
per-playthrough encounters / free narrative zones) so replayability survives the
integrity fix.

## Technical Context

**Language/Version**: Python 3.12 (backend, unchanged).

**Primary Dependencies**: `pydantic_graph` (already available — bundled with
`pydantic-ai>=2.0.0`, verified importable in this project's `.venv`; no `pyproject.toml`
change needed). `pydantic-ai` (unchanged, already the narrator's foundation).
No frontend changes — this feature is entirely backend/engine-harness.

**Storage**: No new storage. Per-playthrough encounter determinations reuse
`World.flags: dict[str, bool]` (existing domain field). Adventure module structure
(`backbone.yaml`, `templates.yaml`) is static file content, not database-backed —
consistent with `SKILL.md`'s existing treatment (swap boundary #2).

**Testing**: `pytest`, following this repo's existing determinism convention (`rules`/
`combat` tests: seeded RNG, in-memory storage, no LLM, no disk). The dispatcher's graph
logic is testable the same way — `call_engine()` against an in-memory MCP server, no
LLM involved for any node except `ClassifyIntent` and `Narrate`. Those two are unit-tested
via `pydantic_ai`'s own `agent.override(model=FunctionModel(...))` (exact, assertable
responses) or `TestModel()` (quick automatic-valid-output checks) — not a hand-rolled
fake class; `FakeNarrator` (`harness/base.py`) stays reserved for testing at the
`NarratorBackend` **Protocol** boundary (ADR-011), a different granularity than these two
private in-graph agents (see `research.md`'s testing decision, added after
`/speckit-analyze` cross-checked this plan against the `pydantic-ai` skill's own guidance).
Live-model validation (`quickstart.md`) is separate, manual/scripted, matching how
ADR-033's own reproductions were found — mocked tests alone were shown insufficient for
this exact bug class (see the `auth_redirect_flows_require_live_testing` learning lesson
for the general principle, though this is engine/narrator, not auth).

**Target Platform**: Linux server (unchanged — same FastAPI/uvicorn deployment as the
rest of `gamebook_web`).

**Project Type**: Web application backend + engine harness (existing `src/gamebook/` +
`src/gamebook_web/harness/` split, unchanged).

**Performance Goals**: Turn latency should not regress meaningfully — today's narrator
can make up to `_MAX_TOOL_CALLS_PER_TURN` (30) LLM-mediated tool round-trips per turn;
the new pipeline caps at 2 fixed LLM calls (classify + narrate) plus one dispatcher-code
call per combat round (zero LLM cost per round). Expected **improvement**, not
regression, in both latency and token cost for non-combat turns.

**Constraints**: The fix must be structural/model-independent (ADR-033's explicit design
constraint) — "a stronger model would not do this" is empirically falsified and MUST NOT
be relied on anywhere in this design.

**Scale/Scope**: Single adventure module (Ignarok) migrated incrementally, one zone at a
time; the dispatcher graph and template library are adventure-agnostic (shared) from day
one.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Numbers Never in Prose (NON-NEGOTIABLE) | **This feature exists to restore this principle** | Today's narrator (ADR-029) claims compliance but ADR-033 empirically disproves it (2 independent reproductions, opposite ends of the model-capability spectrum). Post-feature: the narrator has zero tools, cannot call `roll_dice`/`test_luck`/any mutation tool — compliance becomes structural, not a prompt instruction. |
| II. Dependency on Interfaces Only | **Pass** | The dispatcher sits entirely behind the existing `NarratorBackend` Protocol (swap boundary #3) — `FakeNarrator` and every FastAPI route are untouched, only a new concrete implementation is added. `domain`/`rules`/`combat`/`storage` interfaces are unchanged; the dispatcher depends on the same `StorageBackend`-mediated MCP tool contract the narrator already depended on, via the same `call_engine()`/`direct_call_tool` mechanism `play.py` already uses (ADR-021). |
| III. CONTRACTS.md is Single Source of Truth | **Pass, with a deliberate update** | Adds 2 tools (`apply_healing`, `apply_damage`) to `docs/CONTRACTS.md` §6 in the same change that implements them (`contracts/mcp-tool-contract-changes.md` is the proposed delta) — not silent drift. The 18 existing tools' contracts are unchanged. |
| IV. Determinism and Isolated Testing | **Pass** | The dispatcher is pure code calling already-deterministic, seeded-RNG engine tools (`rules`, `combat` are unchanged) — testable in full isolation exactly like those modules already are. Only `ClassifyIntent` and `Narrate` involve an LLM, and both get fakeable test doubles (structured-input/output, no tool access to mock). |
| V. Domain Invariants and Atomic Persistence | **Pass** | `apply_healing`/`apply_damage` enforce the same `0 <= current <= initial` invariant `update_character_sheet` already enforces (`domain`'s `Attribute._check_bounds`, unchanged) — new tools, same invariant enforcement point. No new persistence entities; `World.flags` reuse needs no schema migration. |

No violations. Complexity Tracking below is filled anyway, given this is a
larger-than-usual architectural change — to make the tradeoffs explicit even though none
of them are Constitution violations.

*Post-Phase-1 re-check*: unchanged — `data-model.md` and `contracts/` confirm no
domain-model or storage-interface change, only new harness-layer types and two new MCP
tools with the same invariant-enforcement pattern as the existing ones.

## Project Structure

### Documentation (this feature)

```text
specs/009-deterministic-turn-dispatcher/
├── plan.md              # This file
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   ├── mcp-tool-contract-changes.md
│   └── adventure-module-schema.md
└── tasks.md              # Phase 2 output (/speckit-tasks — not yet generated)
```

### Source Code (repository root)

```text
src/gamebook/
├── mcp/server.py                 # CHANGED — add apply_healing, apply_damage tools
└── domain/models.py               # UNCHANGED — Attribute invariant already enforces bounds

adventure_modules/                 # NEW top-level directory — not under .claude/skills/
└── templates.yaml                  # NEW — shared mechanical situation library (research.md's
                                     #   resolved file-location decision)

src/gamebook_web/
├── harness/
│   ├── agent.py                   # CHANGED — PydanticNarrator's tool-use loop replaced;
│   │                               #   narrator becomes toolsets=[] pure-narration call
│   ├── dispatcher.py               # NEW — the pydantic_graph.Graph: ClassifyIntent,
│   │                               #   MechanicalDispatch, CombatRound, NarrativeFree,
│   │                               #   Narrate nodes; IntentClassification, TurnOutcome
│   ├── adventure_structure.py      # NEW — AdventureStructure, MechanicalSituationTemplate
│   │                               #   Pydantic models + backbone.yaml/templates.yaml loader
│   ├── base.py                     # UNCHANGED — NarratorBackend Protocol, FakeNarrator
│   └── tool_trace_audit.py         # CHANGED (reduced role) — kept as belt-and-suspenders
│                                    #   detection on the dispatcher's own calls, no longer
│                                    #   the primary defense (prevention supersedes it)
├── mcp_host.py                     # UNCHANGED — call_engine()/direct_call_tool already exists
└── api/play.py                      # UNCHANGED — depends only on NarratorBackend Protocol

.claude/skills/ignarok/
├── SKILL.md                        # UNCHANGED — retained for Layer-3 narrative lore
└── backbone.yaml                    # NEW — Layers 1-2 for the zones migrated in this pass,
                                      #   includes reviewed_by/reviewed_at (FR-011 gate)

tests/
├── server/test_dispatcher.py        # NEW — graph node unit tests, in-memory MCP, seeded RNG,
│                                      #   TestModel/FunctionModel overrides for ClassifyIntent/Narrate
├── server/test_narrator_integration.py  # CHANGED — test_allowlist_excludes_lifecycle_tools /
│                                      #   test_allowlist_includes_core_play_tools now assert an
│                                      #   empty narrator toolset (the old _NARRATOR_ALLOWED_TOOLS
│                                      #   is removed)
├── qa/test_mcp_integration.py       # CHANGED — direct-call tests for apply_healing/apply_damage
│                                      #   (bounds, invariant, amount<=0 rejection)
└── qa/test_adventure_structure.py   # NEW — FR-010 structural validator (structure + FR-011's
                                      #   reviewed_by/reviewed_at gate), part of the existing
                                      #   plugability-audit-style qa suite
```

**Structure Decision**: Existing module boundaries (`src/gamebook/` engine,
`src/gamebook_web/harness/` harness, `.claude/skills/` adventure modules) are preserved
and extended, not restructured. The dispatcher is new code within the existing
`harness/` package (it is harness-layer orchestration, not an engine change) — this
keeps swap boundary #3 (harness) as the only thing that changed, matching
Constitution Principle II.

## Complexity Tracking

*No Constitution violations to justify — filled for transparency given the scope.*

| Added complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| A graph library (`pydantic_graph`) instead of plain `if`/`match` control flow | The combat case is inherently cyclic (round → round → round); a typed graph makes "every path converges on one gated `Narrate` node" a structural property the type checker/runtime enforces, not a convention | Plain control flow works for the non-combat paths but would need its own ad-hoc loop-with-a-guard for combat, re-deriving what `pydantic_graph` already provides, with a weaker guarantee that no path skips the narration gate |
| A second LLM call per turn (intent classifier, separate from narration) | Structured-output-only, no-tool classification has zero fabrication surface by construction; folding classification into the narration call is exactly today's (broken) architecture | One combined call is what ADR-033 empirically proved unsafe — not a viable simpler alternative for *this* problem |
| Two new MCP tools (`apply_healing`/`apply_damage`) alongside the existing `update_character_sheet` | Bounds the blast radius of any future toolset misconfiguration to a template's declared range, rather than any in-bounds absolute value — defense in depth, not reliance on toolset filtering alone | Keeping only `update_character_sheet` and just not exposing it to the narrator was considered — rejected because it makes the guarantee depend entirely on toolset wiring being correct forever, exactly the kind of single point of failure ADR-018's "prevention, not detection" posture argues against |
