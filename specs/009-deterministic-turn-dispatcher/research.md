# Research: Deterministic Turn Dispatcher (Pure Narrator) — 009

**Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md) | **Decision record**: [ADR-033](../../docs/adrs/ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md)

ADR-033 already carries most of the architectural decision (the three-layer adventure
module, the classify→dispatch→narrate pipeline, the template library). This document
resolves the remaining implementation-level unknowns needed to turn that decision into a
plan, grounded in what actually exists in this codebase today.

---

## Decision: graph engine — `pydantic_graph`, one graph, combat as the only cyclic node

**Decision**: Implement the classify→dispatch→narrate pipeline as a single
`pydantic_graph.Graph` (already available — bundled with `pydantic-ai>=2.0.0`, confirmed
importable in this project's venv, **no new dependency**). Nodes are `BaseNode`
dataclasses; edges are the union types in each node's `run()` return annotation. Combat
is the one node type with a self-edge (`CombatRound → CombatRound`); every other path is
acyclic and converges on a single `Narrate` node before `End`.

**Rationale**: discussed and agreed with the project owner in-session. Two separate
graphs (one for combat, one for the general dispatcher) would require passing
`GraphRunContext` state across a seam between two graph runs — exactly the kind of
boundary where a fabricated/stale value could slip back in, which is the failure class
this whole spec exists to eliminate. A single graph makes "every path reaches the same
gated `Narrate` node" a structural property, not a convention two independent graphs
would have to uphold by discipline. `pydantic_graph`'s own worked example
(`DivisibleBy5 ⇄ Increment` looping until a condition, from its README) is exactly the
same "typed node returns itself" pattern `CombatRound` needs — cycles are a first-class,
documented case, not a workaround.

**Alternatives considered**: plain Python control flow (`match`/`if` chain, no graph
library) — viable for the non-combat paths (they're close to linear), rejected because
it doesn't buy anything over `pydantic_graph` here and loses the typed, replayable
execution trace that directly serves FR-001's "every stat change traces back to
something that was actually checked" requirement — a `pydantic_graph` run's node history
*is* that trace. Two separate graphs (combat vs. general) — rejected, see above.

---

## Decision: insertion point — a new `NarratorBackend` implementation, zero route changes

**Decision**: The dispatcher pipeline lives behind the **existing**
`NarratorBackend` Protocol (`src/gamebook_web/harness/base.py`) — a single
`narrate(campaign_id, context) -> Scene` method. `PydanticNarrator`
(`src/gamebook_web/harness/agent.py`) is replaced by a new class satisfying the same
Protocol, internally running the `pydantic_graph` pipeline instead of a single
free-tool-use `agent.run()`. `FakeNarrator` (the test double) and every FastAPI route in
`src/gamebook_web/api/play.py` are **untouched** — they only ever depended on the
Protocol, never on `PydanticNarrator`'s internals.

**Rationale**: this is swap boundary #3 (harness) working exactly as designed
(Principle II) — the same seam that already absorbed the Phase-1→Phase-2 harness swap
and the ADR-029 effects-elimination refactor. No new seam needs to be invented.

**Alternatives considered**: inserting the dispatcher as a pre-processing step inside
`play.py`'s turn route, ahead of calling the narrator — rejected, because it would leak
turn-resolution logic into the API layer (violates the module boundary: `harness` owns
narration, `api` only orchestrates HTTP) and would need its own new test seam instead of
reusing `FakeNarrator`'s existing one.

---

## Decision: how the dispatcher calls engine tools — `call_engine()` / `direct_call_tool`, zero LLM calls

**Decision**: Dispatcher nodes call MCP tools the same way `play.py`'s routes already
do for non-narrator-driven operations: `call_engine(toolset, tool_name, **args)` →
`toolset.direct_call_tool(tool_name, args)` (`src/gamebook_web/mcp_host.py`, ADR-021's
established pattern — `direct_call_tool` for code, `toolsets=[]`/filtered toolsets for
agents). This is code calling a tool directly, no LLM round-trip, no chance for a model
to alter, omit, or re-order the call — matching ADR-033's diagram ("Deterministic
dispatcher (code, 0 LLM calls)") exactly.

**Rationale**: this mechanism already exists and is already used in this exact file for
this exact purpose (non-agent, code-driven engine calls) — no new integration pattern
needed, only new callers of an existing one.

---

## Decision: narrator's tool access — empty toolset (zero mutation *and* zero read tools)

**Decision**: The new pure narrator receives **no toolset at all** (`toolsets=[]`), not
even the read-only tools (`read_character_sheet`, `read_world`, etc.) it has access to
today. It receives everything it needs as already-resolved values in the prompt (the
dispatcher already read the state to run its checks, and hands the narrator the action +
results + relevant state directly) — mirroring `NarratorContext`'s existing shape
(`character`, `world`, `summary`, `recent_events`, `choice`), extended with the turn's
`TurnOutcome`.

**Rationale**: ADR-033's decision text says the narrator "has no mutation tools", which
leaves open whether *read* tools stay. Removing read tools too is strictly safer and
simpler: it removes any residual tool-call surface (Modes 1–4 all require the narrator
to *call something*; zero tools means zero surface, not "zero mutation tools but still a
possible malformed read call to audit"), and the dispatcher already necessarily reads
character/world state to run its checks — handing that same data to the narrator as
plain context avoids a second, redundant read round-trip per turn. This also caps the
per-turn LLM call count at exactly 2 (classify + narrate) plus one per combat round,
matching ADR-033's "2 LLM calls total (fixed)" example precisely — today's narrator can
take up to `_MAX_TOOL_CALLS_PER_TURN` (30) tool-call round-trips per turn.

**Alternatives considered**: keep read-only tools on the narrator for flexibility —
rejected as unnecessary residual attack/failure surface once the dispatcher already has
everything the narrator needs to receive as context.

---

## Decision: new engine tools — `apply_healing` / `apply_damage`, relative not absolute

**Decision**: Add two new MCP tools alongside the existing 18 (`docs/CONTRACTS.md` §6),
per ADR-033's original (2026-07-04) proposal, now used by the **dispatcher** rather than
the narrator: `apply_healing(campaign_id, amount, source)` and
`apply_damage(campaign_id, amount, source)`. Both take a **relative** `amount: int`
(added/subtracted from `stamina.current`, clamped to `[0, initial]` by the existing
domain invariant) and a closed `source` enum, matching the template library's bounded
params (`risk_amount: {min: 1, max: 3}`, `risk_source: {values: [...]}}`) from ADR-033.
`update_character_sheet` (absolute-value patch semantics) stays in the contract for
lifecycle/admin use (e.g. `create_character`'s initial roll) but is **removed from any
LLM-reachable toolset** — narrator has zero tools, and the dispatcher only ever calls
`apply_healing`/`apply_damage`/`roll_dice`/`test_luck`/`update_world`/`register_event`/
combat tools for in-play mechanics.

**Rationale**: this is the concrete fix for Mode 2 (fabricated absolute values as
tool-call arguments) at the schema level, not just "nobody calls the dangerous tool
anymore" — even if a future toolset misconfiguration re-exposed a mutation tool to an
LLM, `apply_healing`/`apply_damage` bound the blast radius to the template's declared
`risk_amount` range, whereas `update_character_sheet` accepts any in-bounds absolute
value. Defense in depth, not reliance on toolset filtering alone.

---

## Decision: intent classification — a separate, small, structured-output `Agent` call

**Decision**: `ClassifyIntent` is one `pydantic_ai.Agent` call with
`output_type=IntentClassification` (a `BaseModel`: `action: str | None`,
`confidence: float`, `template: str | None`) — **not** a tool-use agent, no MCP toolset
at all. It reads the current zone's available templates/encounters (already resolved by
the calling node from the adventure structure, passed as plain context) and the
player's free text, and returns a structured guess. It is not asked to compute or state
any game number — only to name which action (if any) the player's text corresponds to.

**Rationale**: structured output with no tool access has no fabrication surface by
construction — the classifier cannot invent a stat change because it has no tool through
which to apply one, and its output type has no field for one either. Confidence
threshold + "default to narrative-free below threshold" (FR-004) is a plain numeric
comparison in the graph node, not an LLM decision.

**Alternatives considered**: fold classification into the same call as narration (one
LLM call decides both "what happened" and "how to tell it") — this is close to today's
architecture and exactly what produces Modes 1–4; rejected on the same grounds as the
rest of this spec.

---

## Decision: testing `ClassifyIntent` and `Narrate` in isolation — `TestModel`/`FunctionModel`, not a hand-rolled fake

**Decision**: Unit tests for the `ClassifyIntent` and `Narrate` graph nodes override
their internal `pydantic_ai.Agent`'s model directly —
`agent.override(model=FunctionModel(custom_fn))` for exact, assertable responses, or
`TestModel()` for a quick automatic-valid-output check — rather than a hand-rolled fake
class returning a queued value.

**Rationale**: found during `/speckit-analyze` cross-checking this plan against the
`pydantic-ai` skill's own testing guidance ("Use `TestModel` for fast deterministic
tests and `FunctionModel` for custom response logic"). `FakeNarrator`
(`harness/base.py`) is the right pattern for testing at the `NarratorBackend`
**Protocol** boundary (ADR-011's explicit swap point — a full alternate
implementation makes sense there). `ClassifyIntent`/`Narrate` are not a swap boundary —
they're private `Agent` instances inside the graph — so overriding the model via
`FunctionModel`/`TestModel` is the right granularity: it exercises the real `Agent`
object (structured-output validation, retries) while controlling what the model
"returns," instead of bypassing the `Agent` entirely with a parallel fake-class
hierarchy that would need to be kept in sync with it by hand.

**Alternatives considered**: a `FakeIntentClassifier` class mirroring `FakeNarrator`'s
queue pattern — this was the original draft of this decision; rejected once checked
against the `pydantic-ai` skill's explicit guidance for this exact scenario.

---

## Decision: per-playthrough encounter persistence — reuse `World.flags`

**Decision**: FR-007 ("once determined, remember it") is stored in the existing
`World.flags: dict[str, bool]` (`src/gamebook/domain/models.py`) — e.g.
`flags["encounter.dark_ravine.cave_bat"] = True` — written via the existing
`update_world` tool the dispatcher already calls. No new domain entity or storage
schema.

**Rationale**: `flags` already exists precisely for "sticky boolean story state" and is
already persisted/patched atomically by `update_world`'s existing merge semantics
(`docs/CONTRACTS.md` §6). Reusing it keeps `domain`'s schema stable (Principle III —
`CONTRACTS.md` changes should be deliberate, not incidental) and needs no migration.

**Alternatives considered**: a new `EncounterState` domain entity — rejected as
unnecessary; a boolean flag keyed by zone+encounter-id is exactly what `flags` already
models.

---

## Decision: adventure module format — new YAML files alongside `SKILL.md`, not replacing it

**Decision**: Swap boundary #2 (`adventure-module`) gains two new files: per-module
`backbone.yaml` (zones, key NPCs, boss, victory condition, probabilistic encounters —
ADR-033's Layers 1–2), co-located inside `.claude/skills/<module>/` next to that module's
existing `SKILL.md`, and a shared `templates.yaml` (the mechanical situation library —
not per-module, referenced by every module) at the new top-level `adventure_modules/templates.yaml`
— **not** inside `.claude/skills/`. `SKILL.md` is **kept** as the source of narrative
lore text the narrator still reads for atmosphere/tone in Layer-3 (narrative) zones — it
stops being the sole source of *structure*.

**Rationale**: matches the spec's own Assumption: "the first adventure (Ignarok) is
migrated incrementally, one area at a time... areas not yet migrated continue to behave
as free narrative areas in the meantime." Keeping `SKILL.md` alongside the new
structured files makes that incremental migration literal — a zone with no `backbone`/
`probabilistic_encounters` entry is, by construction, Layer 3 (fully narrative) until
someone adds one.

**File location, resolved** (found underspecified during `/speckit-analyze`, resolved
here rather than left as a hedge): `backbone.yaml` living inside
`.claude/skills/<module>/` matches existing precedent — `agent.py`'s
`_load_adventure_lore()` already reads `.claude/skills/ignarok/SKILL.md` directly from
the web backend, so this doesn't introduce a new blur of swap-boundary #2's Phase-1/
Phase-2 distinction. `templates.yaml`, however, is **not** module-specific and does not
belong inside `.claude/skills/` at all — that directory's contract (per this project's
own Phase-1 harness convention) is "each subdirectory is a Claude Code Skill," which
requires its own `SKILL.md`; a bare shared-data subdirectory there has no such file and
sits oddly among genuine skills. Moved to a new top-level `adventure_modules/templates.yaml`
instead — parallel to `.claude/skills/`, dedicated to swap-boundary-#2 content that isn't
Claude-Code-skill-shaped.

**Alternatives considered**: fully replacing `SKILL.md` with structured YAML in one pass
— rejected, contradicts the spec's own incremental-migration assumption and would block
starting this work until every zone of Ignarok is authored. Keeping `templates.yaml`
under `.claude/skills/_shared/` (the original draft of this decision) — rejected per the
resolution above.

---

## Decision: FR-011 (mandatory human review) is enforced by a schema field + validator check, not documentation alone

**Decision**: `AdventureStructure` gains two optional fields, `reviewed_by: str | None`
and `reviewed_at: str | None` (ISO-8601). The structural validator (FR-010,
`tests/qa/test_adventure_structure.py`) fails if either is absent — separately from its
structural checks (broken references, out-of-bounds probabilities) — so a `backbone.yaml`
with valid structure but no recorded human sign-off still fails the mandatory pre-merge
gate.

**Rationale**: found during `/speckit-analyze` — FR-011 is phrased as a hard "MUST"
requirement ("An adventure's structure MUST receive human review at least once before
its first release... even after it has passed the automated check"), but the original
draft of this plan only *documented* that requirement (a note in the schema contract)
with nothing in the design that actually gates on it — passing the automated structural
check alone would have been sufficient to merge. A `reviewed_by`/`reviewed_at` pair
gives the validator something concrete to check for presence; it does not (and cannot)
verify the review was *thorough*, only that someone recorded doing it — matching FR-011's
own framing that the automated check is "necessary, not sufficient."

**Alternatives considered**: a separate `checklists/adventure-release.md` process
document with no automated gate — rejected, since "documented but unenforced" is exactly
the gap this decision closes; a full sign-off workflow (e.g. a PR-approval bot) — rejected
as disproportionate for a single-adventure-module project at this stage.

---

## Decision: structural validator (FR-010) — a standalone script + test, not a new MCP tool

**Decision**: `FR-010`'s consistency check (broken template references, out-of-bounds
probabilities, unreachable/undefined zones) is a plain Python validator invoked via a
test (`tests/qa/test_adventure_structure.py`, in the spirit of the existing plugability
audit in `tests/qa/`) and optionally a standalone script for CI/authoring workflow — not
an MCP tool, since it has nothing to do with a live campaign and shouldn't be reachable
by the narrator or the dispatcher at runtime.

**Rationale**: matches this repo's existing pattern for structural/architectural checks
(`tests/qa/test_dependencies.py`, `tests/qa/test_isolation.py` — the plugability audit)
— a test that fails the build, not a runtime tool.

---

## MVP scoping (per project-owner decision, this session)

**Decision**: This plan covers the full architecture (the graph, the three-layer
adventure structure, the template library, the validator) because User Story 1 already
requires most of it — a working dispatcher needs at least the graph, at least one
mechanical template category (risky/skill checks), and the combat loop to make good on
"a hero's stats can never be corrupted." User Stories 2 (replay variance) and 4
(authoring tooling beyond the minimal validator) are the parts that can genuinely wait.
`/speckit-tasks` (next) sequences User Story 1 as the MVP checkpoint; Stories 2–4 are
later phases, not cut from this plan.

---

## Out of scope / explicitly deferred

- Migrating all of Ignarok's zones to `backbone.yaml`/`probabilistic_encounters` in this
  pass — per the spec's own Assumption, incremental, and only as many zones as are
  needed to prove User Story 1 end-to-end (the `stone_archway` guardian fight and one
  `risky_action` zone are enough for the MVP checkpoint; the rest stay Layer 3 narrative
  until a later pass).
- An AI "rules compiler" that drafts `backbone.yaml` from existing lore (mentioned as an
  acceptable *input* to the human-review step in the spec's Assumptions) — not required
  to build the dispatcher itself; the first `backbone.yaml` for the MVP checkpoint can be
  hand-authored.
