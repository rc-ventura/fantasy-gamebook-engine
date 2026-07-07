# ADR-033: Pure narrator + deterministic dispatcher — eliminate narrator fabrication by construction

**Status**: Proposed
**Date**: 2026-07-04 (original), 2026-07-05 (revised — full architectural shift)
**Related**: [ADR-018](./ADR-018-multi-tenant-engine-per-call-campaign-id.md) (`ScopedMCPToolset` — prevention, not detection), [ADR-029](./ADR-029-narrator-as-tool-use-agent-eliminate-effects.md) (tool-use agent pattern + Alternativa E — deterministic combat loop), `docs/CONTRACTS.md` §2 (`Attribute` invariant) and §6 (`update_character_sheet` patch semantics), `.specify/memory/constitution.md` Principle I (Numbers Never in Prose)
**Code**: `src/gamebook/mcp/server.py` (`update_character_sheet`, combat tools), `src/gamebook_web/harness/agent.py` (`PydanticNarrator`, `_NARRATOR_ALLOWED_TOOLS`), `src/gamebook_web/harness/tool_trace_audit.py` (detection layer), `src/gamebook/domain/models.py` (`Attribute._check_bounds`)

---

## Context

Principle I ("Numbers Never in Prose") and ADR-029 both claim the narrator cannot
fabricate numbers because it calls MCP tools during generation and narrates from real
tool results. That claim is true for numbers that appear in the **narrative text** when
the narrator chooses to call the right tool. It is not true for:

- Numbers the narrator supplies as **tool-call arguments** (Mode 2)
- Numbers the narrator **invents in event data** without calling the corresponding tool (Mode 1)
- State changes the narrator **narrates without consulting the engine** (Mode 4)
- Results the narrator **receives correctly but passes differently** to the update tool (Mode 3)

### Empirical reproduction #1 — gpt-4o-mini (2026-07-04)

While validating the multi-provider narrator (`feat/009`) against a real docker-compose
stack with `NARRATOR_MODEL=openai:gpt-4o-mini`, a real turn produced:

1. `read_character_sheet` / `read_world` — narrator correctly read real state
   (`stamina.current=19`, `luck.current=8`).
2. `update_character_sheet` called with
   `changes={"stamina": 10, "luck": 5, "gold": 0, "backpack": []}` plus a hallucinated
   `auto_merge=true` keyword argument. Both `stamina` and `luck` values are fabricated —
   neither derived from the values just read, nor from any `roll_dice`/`test_luck`/combat
   result in this turn.
3. The tool rejected the call (attribute fields require a partial object like
   `{"current": 18}`, not a bare scalar). The model retried once, produced the same
   shape of error, and pydantic-ai raised `UnexpectedModelBehavior`.

The turn failed loudly only because of a *schema* mismatch. Had `gpt-4o-mini` sent
`{"stamina": {"current": 10}, "luck": {"current": 5}}` — syntactically valid — the write
would have **succeeded**, silently overwriting real engine state with fabricated numbers
within valid bounds. The failure was luck, not a guarantee.

### Empirical reproduction #2 — gpt-5-chat-latest (2026-07-05)

A full play session (9 turns: create character → explore → combat → healing → trap →
examine) was run against the same docker-compose stack with
`NARRATOR_MODEL=openai:gpt-5-chat-latest` — the strongest non-reasoning model available,
specifically the best for tool-use and prose. The results:

| Turn | Action | Mode | What happened |
|---|---|---|---|
| 4 | Combat (Archway Guardian) | — | Engine computed damage correctly (stamina 16→14). Narrator narrated real value ("stamina holding at fourteen"). **This worked.** |
| 6 | Rest (healing) | **Mode 2** | Narrator called `update_character_sheet(changes={"stamina": {"current": 16}})` — fabricated absolute value 16 (full heal) without any engine rule. Engine accepted silently (16 is within `0 <= current <= initial`). Event: `rest: {stamina_after_rest: 16}`. |
| 8 | Leap over rune | **Mode 1 + 4** | Narrator narrated success ("your leap flawless") without calling `test_luck` or `roll_dice`. Registered event `jump_attempt: {success: true, roll_result: 11}` — **fabricated roll_result** without `roll_dice`. `luck.current` remained 11 (= initial) across the entire campaign, proving `test_luck` was never called despite luck-dependent narrative. |
| 9 | Examine crystal | **Mode 1** | Narrator registered event `examine_object: {roll_result: 7}` without calling `roll_dice`. |

**Mathematical proof against persisted state**: `luck.current == luck.initial == 11`
across 9 turns with luck-dependent narrative (combat, trap, examination) is a direct
invariant violation — `test_luck` always decrements luck by exactly 1 (engine rule,
CONTRACTS.md §6). If the engine had been consulted, luck would be < 11. It wasn't.

**Bonus bug**: `visited_locations` was **overwritten** instead of appended on every turn.
After 7 locations visited, only 4 remained in the list. The `/map` command shows wrong
state.

### What the two reproductions prove together

The same failure modes appear at **opposite ends of the model capability spectrum** —
`gpt-4o-mini` (cheap, weak) and `gpt-5-chat-latest` (expensive, strongest for tool-use).
This kills the argument "a stronger model would not do this." The problem is
**architectural, not model-capacity**: the narrator has tools that accept
narrator-supplied values, and no structural guarantee forces the narrator to call the
right tool before narrating a result.

### The four modes of failure

| Mode | Description | Empirically confirmed | Addressed by |
|---|---|---|---|
| 1 | Narrator invents numbers in event data without calling the corresponding tool | ✅ gpt-5-chat-latest | This ADR (dispatcher owns tool calls) |
| 2 | Narrator supplies fabricated absolute values as tool-call arguments | ✅ gpt-4o-mini + gpt-5-chat-latest | This ADR (narrator has no mutation tools) |
| 3 | Narrator receives correct result but passes different value to update tool | Partially (combat resolves correctly; outside combat, `amount` is narrator-supplied) | This ADR (dispatcher computes, narrator never sees raw values to pass) |
| 4 | Narrator decides outcome without consulting engine at all | ✅ gpt-5-chat-latest | This ADR (dispatcher runs checks before narrator sees result) |

### Design constraint

The fix must not rely on model quality. An argument of the form "a stronger/more
expensive model would not have done this" is **empirically falsified** by reproduction #2.
The primary guarantee must be structural and model-independent — matching the
"prevention, not detection" posture already established for `campaign_id` (ADR-018).

---

## Decision

**Split the narrator's responsibilities into two layers:**

1. **Intent classifier (LLM)** — maps the player's free-text choice to a structured
   action from the adventure module's backbone + active encounters, or to
   `narrative_free` (fallback).
2. **Deterministic dispatcher (code)** — executes the mandatory engine checks for the
   classified action, computes all numeric results, and passes them to the narrator.
3. **Narrator (LLM)** — receives the action + engine results and narrates the scene.
   Has **no mutation tools** — cannot call `update_character_sheet`,
   `apply_healing`, `apply_damage`, `roll_dice`, `test_luck`, or any combat tool.

The narrator becomes a **pure narrator**: it receives what happened and writes prose.
It never decides what happened. Modes 1, 2, 3, and 4 are eliminated by construction —
the narrator has no tool through which to fabricate, omit, or override a number.

### Architecture

```
Player says: "I try to leap over the rune"
        ↓
Intent classifier (LLM, 1 call):
  → reads: current state (zone, active encounters, character sheet, available templates)
  → outputs: { action: "leap_over", confidence: 0.92 }
        ↓
Deterministic dispatcher (code, 0 LLM calls):
  → looks up action "leap_over" in the adventure module's encounters for current state
  → mandatory_checks: [test_luck]
  → calls engine: test_luck() → luck 11→10, result: success
  → calls engine: update_world(current_location: rune_chamber)
  → collects: { action: leap_over, luck_result: success, luck_after: 10,
                 new_location: rune_chamber }
        ↓
Narrator (LLM, 1 call):
  → receives: action + engine results (no mutation tools available)
  → outputs: Scene with narrative + choices
  → "You sprang over the glowing rune. Your luck held — the rune flared
     impotently beneath your boots as you landed safely beyond."
        ↓
2 LLM calls total (fixed). Narrator never had the chance to skip test_luck
or fabricate roll_result. Mode 1, 2, 3, 4 impossible by construction.
```

### The adventure module — three-layer structure

The adventure module (swap boundary #2) is **not a fully fixed graph** (that would make
every playthrough identical) and **not fully free lore** (that reintroduces fabrication).
It is a **three-layer hybrid**: a fixed backbone, probabilistic encounters, and
narrative-free zones. This preserves the AI gamebook's core appeal — the same adventure
plays differently each time — while keeping mechanical integrity deterministic.

#### Layer 1: Backbone (fixed)

The structural spine of the adventure. Every playthrough of this module has these
elements. This is what makes it *this* adventure and not another.

```yaml
# ignarok_module.yaml — backbone
backbone:
  zones: [mountain_pass, dark_ravine, grey_peak, malachar_lair]
  key_npcs: [Malachar, The Hermit]
  boss: malachar
  victory_condition: { flag: malachar_defeated }
  opening_location: mountain_pass
```

The backbone defines: which zones exist, who the key NPCs are, who the final boss is,
what victory means. It does **not** define what happens in each zone — that's layers 2
and 3. Every Ignarok campaign ends with "defeat Malachar"; the path there varies.

#### Layer 2: Probabilistic encounters (semi-structured)

Encounters that **may or may not appear** in a zone, rolled once on first entry and
persisted. This is the primary source of **structural variance** between playthroughs
of the same module. The cave_bat that attacked you last time might not be there this
time. The crystal curse might be active or dormant.

```yaml
# ignarok_module.yaml — probabilistic encounters
probabilistic_encounters:
  dark_ravine:
    - enemy: cave_bat
      probability: 0.4
      template: combat
      params: { enemies: [{name: "Cave Bat", skill: 4, stamina: 3}], flee_allowed: true }
    - enemy: rogue_goblin
      probability: 0.3
      template: combat
      params: { enemies: [{name: "Rogue Goblin", skill: 5, stamina: 4}], flee_allowed: true }
  hall_of_echoes:
    - trap: crystal_curse
      probability: 0.5
      template: risky_action
      params: { risk_amount: 2, risk_source: magical_trap }
  stone_archway:
    - enemy: archway_guardian
      probability: 1.0              # always — it's a backbone guardian
      template: combat
      params: { enemies: [{name: "Archway Guardian", skill: 8, stamina: 10}], flee_allowed: false }
```

When the player enters a zone, the dispatcher rolls for each encounter (once, persisted
to world state). If an encounter is active, it becomes part of the current state and
the narrator must account for it. If not, the zone is clear and the narrator describes
it accordingly. **This is why the same adventure is never identical** — the encounters
that are present change from campaign to campaign.

#### Layer 3: Narrative zones (free)

Zones (or parts of zones) with **no pre-defined encounters**. The narrator creates
content here freely — NPCs, minor traps, atmospheric scenes, side discoveries — using
the lore as context. Zero engine calls unless the narrator's narrative triggers a
mechanical action that the intent classifier maps to a template.

```yaml
# ignarok_module.yaml — narrative zones
narrative_zones:
  - foothills           # narrator creates freely, no encounters pre-defined
  - mountain_trails     # narrator creates freely
  - abandoned_camp      # narrator creates freely
```

In these zones, the narrator is free to invent. If the narrator invents a trap and the
player interacts with it, the intent classifier maps the player's action to a template
(e.g. `risky_action`) and the dispatcher runs the engine check. The narrator never
computes the result — but it can create the *situation* that leads to a mechanical
check. This is the "narrative-free" fallback, but as a **designed feature** of specific
zones, not just a safety net.

#### How the three layers interact at runtime

```
Player enters "dark_ravine" (first time)
        ↓
Dispatcher:
  → Is dark_ravine a backbone zone? Yes.
  → Roll probabilistic encounters (once, persist):
    → cave_bat: roll 0.4 → 0.27 → YES (present)
    → rogue_goblin: roll 0.3 → 0.82 → NO (absent)
  → Current state: dark_ravine + cave_bat_present
        ↓
Narrator:
  → Receives: "dark_ravine, cave_bat present, rogue_goblin absent"
  → Narrates: "Bats scatter from the ceiling as you enter the ravine..."

Player says: "I sneak past the bats"
        ↓
Intent classifier:
  → Available actions: [fight_bats, sneak_past, retreat, narrative_free]
  → "sneak_past" → maps to risky_action template (confidence: 0.85)
        ↓
Dispatcher:
  → risky_action: test_luck() → luck 11→10, result: success
  → No damage applied, player passes through
  → update_world(current_location: deeper_ravine)
        ↓
Narrator:
  → Receives: "sneak_past succeeded, luck_after=10, now in deeper_ravine"
  → Narrates: "You hold your breath and slip past the bats..."
```

Next campaign, same zone: cave_bat roll → 0.71 → NO. The narrator describes an empty
ravine. Different experience, same backbone.

#### What is fixed vs variable per playthrough

| Component | Fixed (backbone) | Probabilistic | Narrator free |
|---|---|---|---|
| Zones that exist | ✅ | | |
| Boss + key NPCs | ✅ | | |
| Victory condition | ✅ | | |
| Which enemies appear | | ✅ rolled per zone | |
| Which traps are active | | ✅ rolled per zone | |
| Combat mechanics (dice, damage) | ✅ engine determinístico | | |
| Minor NPCs, side scenes | | | ✅ narrador cria |
| Narrative prose | | | ✅ LLM |
| Dice roll results | | ✅ (variável por roll) | |

**Two campaigns of the same Ignarok**: same boss (Malachar), same zones, same victory
condition — but different enemies encountered, different trap states, different dice
results, completely different prose. Structurally similar, mechanically and narratively
distinct. This is the AI gamebook's value proposition: more variance than a fixed
gamebook, more integrity than free-form LLM narration.

### Template library — generic, written once, reused across all modules

The template library is **shared across all adventure modules**. It defines the
mechanical patterns that the dispatcher executes. Writing a new adventure module does
not require writing new templates — it requires referencing existing ones from the
backbone and probabilistic encounter layers.

```yaml
# templates.yaml — reusable mechanical action templates (shared, not per-module)
templates:
  risky_action:
    description: "Risky action — test luck; success avoids consequence, failure takes damage"
    params:
      risk_amount: { type: int, min: 1, max: 3 }
      risk_source: { type: enum, values: [trap, magical_trap, environment, curse] }
    mandatory_checks:
      - tool: test_luck
        on_success: []
        on_failure:
          - tool: apply_damage
            args: { amount: "${risk_amount}", source: "${risk_source}" }

  skill_check:
    description: "Skill check — roll 2d6 vs skill; failure takes damage"
    params:
      risk_amount: { type: int, min: 1, max: 4 }
      risk_source: { type: enum, values: [trap, magical_trap, environment, curse] }
    mandatory_checks:
      - tool: roll_dice
        args: { notation: "2d6" }
      - comparator: { op: le, left: "${result}", right: "${skill.current}" }
        on_true: []
        on_false:
          - tool: apply_damage
            args: { amount: "${risk_amount}", source: "${risk_source}" }

  rest_heal:
    description: "Rest — deterministic healing"
    mandatory_checks:
      - tool: apply_healing
        args: { amount: 2, source: rest }

  move:
    description: "Move to a new location"
    mandatory_checks:
      - tool: update_world
        args: { current_location: "${destination}" }
```

**Params are bounded by the template schema.** The intent classifier (or the adventure
module author) can choose `risk_amount=2` or `risk_amount=3`, but **cannot choose 50** —
the schema rejects. `risk_source` is a closed enum — no fabricated `"divine_intervention"`.
This is what prevents fabrication even when the classifier chooses the params in runtime:
the choice is bounded, and the engine still computes the actual result.

### Three structural requirements

**1. DSL for conditions — no eval()**

The `comparator` field in templates is **structured data**, not a string to evaluate.
The dispatcher interprets it as a closed set of operations (`eq`, `ne`, `lt`, `le`,
`gt`, `ge`) with explicit `left` and `right` operands. No `eval()`, no `exec()`, no
arbitrary expression parsing — same spirit as the rest of the design (nothing free-form
from an LLM reaches code execution).

**2. Human review of the adventure module's backbone and encounters**

The backbone and probabilistic encounters can be authored by a "rules compiler" LLM
that reads the adventure module's lore (SKILL.md) and generates the structured YAML.
But a deterministic validator only catches **structural** errors (missing template
references, invalid probabilities, unknown zones). It cannot catch **semantic** errors
— e.g. the compiler deciding "examine the crystal" is narrative-free when the lore says
it carries a curse. **First-version backbones for each adventure module require human
review before production.** The validator is necessary, not sufficient. The template
library itself, being generic and shared, is validated once.

**3. Fallback is narrative-free, never "closest mechanical action"**

When the intent classifier's confidence is below threshold for all mechanical actions,
the default is **narrative-free** — the narrator handles the action with zero engine
calls. This is a **fail-safe**: classification error loses some mechanical interest
(the player's action doesn't trigger a dice roll it maybe should have) but **never
corrupts state** (no wrong tool call, no fabricated number). The alternative — "try
the closest mechanical action" — is **fail-dangerous**: it runs engine checks for the
wrong action, potentially applying damage or consuming luck for something the player
didn't do. This property is stated explicitly because it is what makes classification
error acceptable.

### Combat — via ADR-029 Alternativa E (deterministic loop)

Combat is structurally different from single-check actions: it is a multi-round loop
(`start_combat` → `resolve_combat_round` × N → `end_combat`). The encounter layer does not
model individual rounds as separate actions. Instead, combat uses the pattern ADR-029
Alternativa E already endorsed:

```yaml
templates:
  combat:
    description: "Fight — deterministic combat loop, zero LLM in the loop"
    mandatory_checks:
      - tool: start_combat
        args: { enemies: "${enemies}", flee_allowed: "${flee_allowed}" }
      - loop: resolve_combat_round
        until: combat_ended
      - tool: end_combat
    on_success: { transition: "${victory_transition}" }
    on_failure: { transition: "${defeat_transition}" }  # or terminal=death
```

The dispatcher runs the entire combat loop deterministically (zero LLM calls in the
loop), collects the `FinalResult`, and passes it to the narrator who narrates the
outcome with real round counts and damage. This is the pattern ADR-029 explicitly
endorsed as the correct upgrade path; this ADR generalizes it from combat to all
mechanical actions.

### Engine primitivas — `apply_healing` and `apply_damage`

Two new MCP tools replace `update_character_sheet` for attribute changes:

- `apply_healing(campaign_id, amount: int, source: SourceEnum)` — engine computes
  `current = min(current + amount, initial)`, validates invariant, persists.
- `apply_damage(campaign_id, amount: int, source: SourceEnum)` — engine computes
  `current = max(current - amount, 0)`, validates invariant, persists, sets
  `alive=False` if `current == 0`.

`source` is a closed `Enum` (`combat | trap | potion | curse | rest | environment`)
owned by the adventure module, not `str` — the schema rejects fabricated sources
before the tool body runs.

**These tools are called only by the deterministic dispatcher, never by the narrator.**
The narrator's tool allowlist (`_NARRATOR_ALLOWED_TOOLS`) excludes all mutation tools:
no `update_character_sheet` (attribute fields), no `apply_healing`, no `apply_damage`,
no `roll_dice`, no `test_luck`, no combat tools. The narrator keeps only read tools
(`read_character_sheet`, `read_world`, `read_events`, `read_summary`) and
`register_event` / `update_summary` / `update_world` (for narrative metadata like
visited_locations, known_npcs — but not `turn`, which the dispatcher owns).

### Detection layer — `tool_trace_audit` (already implemented, needs rework)

A post-audit detection layer (`src/gamebook_web/harness/tool_trace_audit.py`) runs
after each turn, checking for fabricated numbers in `register_event` data:

- **Mode 1**: event data contains `roll_result` but `roll_dice` was never called
- **Mode 4**: event data claims `stamina_after_rest` but no state tool was called

This layer is **detection-only** (logs warnings, doesn't raise) and was empirically
validated against the gpt-5-chat-latest reproduction patterns.

**Today (pre-ADR-033):** the audit is the only protection against narrator fabrication.
It runs on `result.all_messages()` — the narrator's tool-call history from `agent.run()`.
This is correct for the current architecture (ADR-029), where the narrator calls all
tools itself.

**After ADR-033: the audit needs rework.** Two issues arise:

1. **False positives from split tool traces.** The dispatcher calls `roll_dice`/
   `test_luck`/`apply_damage`/`apply_healing` **outside** the narrator's `agent.run()`.
   `result.all_messages()` contains only the narrator's calls (read tools +
   `register_event`), not the dispatcher's. If the narrator echoes the dispatcher's
   result in `register_event` data (e.g. `roll_result: 10`), the current audit would
   flag it as "roll_dice was never called" — a **false positive**, because roll_dice
   *was* called, just by the dispatcher, not the narrator.

2. **Semantic shift.** The check "roll_dice was never called this turn" becomes
   meaningless when the narrator never has `roll_dice` in its toolset. The check must
   change from **presence-based** ("was roll_dice called?") to **cross-reference-based**
   ("does the roll_result in the event match the dispatcher's computed result?").

**Rework required when ADR-033 is implemented:**

- The audit must receive **both** the dispatcher's tool-call trace and the narrator's
  `result.all_messages()`, combined.
- Mode 1 check changes from "roll_dice was never called" to "event claims roll_result
  that doesn't match any dispatcher-computed roll this turn."
- Mode 4 check changes from "no state tool was called" to "event claims state change
  that doesn't match any dispatcher-computed state change this turn."
- The audit's unit tests (`tests/server/test_tool_trace_consistency.py`) must be
  updated to reflect the split-trace architecture.

This rework is part of the ADR-033 migration path (step 8), not a follow-up. The
current implementation remains correct and valuable for the existing architecture
until the dispatcher is introduced.

### What changes

| Component | Before (ADR-029) | After (this ADR) |
|---|---|---|
| Narrator tool access | 14 tools including all mutation tools | Read tools + `register_event` + `update_summary` + `update_world` (metadata only) |
| Who calls `roll_dice`/`test_luck` | Narrator LLM during generation | Deterministic dispatcher, based on template + encounter |
| Who calls `apply_healing`/`apply_damage` | N/A (didn't exist) | Deterministic dispatcher only |
| Who calls combat tools | Narrator LLM (loop in agent.run) | Deterministic dispatcher (ADR-029 Alt E pattern) |
| Who decides action→checks mapping | Narrator LLM (implicitly, via system prompt) | Template library (generic) + adventure module backbone (per-module) |
| LLM calls per turn | 3-8+ (variable, worse in combat) | 2 (fixed: classify + narrate) |
| Intent classifier | Does not exist | New component — 1 LLM call per turn |
| Adventure module structure | Free SKILL.md (lore only) | Three layers: backbone (fixed) + probabilistic encounters + narrative zones |
| Template library | Does not exist | New component — generic, shared across all modules, written once |
| `update_character_sheet` | Accepts `skill`/`stamina`/`luck` | Rejects attribute fields; scalar/list fields only |
| MCP tool contract | 18 tools | 20 tools — add `apply_healing`, `apply_damage` |

---

## Alternatives considered

### Alternative A (superseded): Narrow `update_character_sheet` only — add `apply_healing`/`apply_damage` for the narrator

The original version of this ADR proposed only narrowing `update_character_sheet` and
adding `apply_healing`/`apply_damage` as narrator-callable tools with bounded amounts
and per-turn call caps.

**Why superseded**: this closes Mode 2 only. Modes 1, 3, and 4 remain — the narrator
can still fabricate `roll_result` in event data (Mode 1), still decide outcomes without
calling the engine (Mode 4), and still pass wrong amounts outside combat (Mode 3).
The gpt-5-chat-latest reproduction confirmed all three modes are live. Narrowing the
tool is necessary (the primitivas are reused in this ADR) but not sufficient.

**What survives**: `apply_healing`/`apply_damage` as engine primitivas, the `source`
Enum, `strict=True`, and `additionalProperties: false` — all are reused by the
deterministic dispatcher. The original Alternative A's best-practice alignment section
applies unchanged to the new tools.

### Alternative B: Provenance/attestation check on `update_character_sheet`

Keep the tool as-is; require server-side that any attribute change matches a preceding
`roll_dice`/`test_luck`/combat result in the same session.

**Why not chosen**: does not cover non-dice narrative changes (potions, traps, curses)
without a full item/effect rules table. Requires cross-call session state that is harder
to reason about than a narrow tool. Still an allowlist bolted onto a wide tool.

### Alternative C: Bounded-delta-only schema on `update_character_sheet`

Accept only signed deltas (`{"stamina_delta": -2}`) instead of absolute values.

**Why not chosen**: keeps skill/stamina/luck in the same wide tool as
name/inventory/gold. A bounded delta still lets the narrator apply unearned-but-plausible
changes repeatedly. The bounded-delta idea is reused inside `apply_healing`/`apply_damage`
(which are bounded by design), but as dedicated tools, not as a suffix convention.

### Alternative D: Status quo + detection-only

Keep everything as-is; add post-hoc audit of attribute changes.

**Why not chosen as primary**: detection tells an operator a fabricated value was
written *after* it corrupted a player's save. Fails the design constraint.

**Kept as secondary**: the `tool_trace_audit` detection layer is implemented and runs
alongside this ADR's prevention architecture as defense-in-depth.

### Alternative E: pydantic-ai retry/validator mechanisms as defense-in-depth

`ModelRetry`, `args_validator`, `WrapperToolset.call_tool()` overrides, configurable
`max_retries` — all reduce the frequency of malformed narrator tool calls.

**Why not chosen as primary**: all four improve the *expected* probability of well-formed
arguments. None *guarantees* it. A weaker model or sampling variance can still produce
a plausible, syntactically valid fabricated value that passes every validator.

**Kept as secondary**: applied to the new tools (`apply_healing`/`apply_damage`) as
defense-in-depth on the dispatcher path — but the dispatcher is deterministic code, so
these mechanisms are belt-and-suspenders against dispatcher bugs, not against LLM
fabrication.

### Alternative F: Deferred tool approval (`ApprovalRequired` / `DeferredToolRequests`)

pydantic-ai's native human-in-the-loop mechanism: gate tool execution on an explicit
approval step.

**Why not adopted**: bigger change to the turn lifecycle than the dispatcher approach.
The dispatcher already provides deterministic gating with zero LLM involvement in the
approve/deny logic. If future actions need materially higher stakes, this is the
fallback mechanism.

---

## Consequences

### Accepted

- **Modes 1, 2, 3, 4 eliminated by construction.** The narrator has no mutation tools.
  The dispatcher calls the engine; the narrator narrates the result. There is no tool
  path through which the narrator can fabricate, omit, or override a number.
- **Principle I holds at every layer** — tool arguments, event data, narrative text —
  because the narrator never touches numbers. It receives them pre-computed.
- **Model-independent guarantee**: swapping `NARRATOR_MODEL` to any provider cannot
  regress this property. The narrator's tool access is structurally limited; no model
  can call a tool it doesn't have.
- **Latency improvement**: 2 fixed LLM calls per turn (classify + narrate) vs 3-8+
  variable today. Combat is zero LLM in the loop (ADR-029 Alt E). More predictable UX.
- **`visited_locations` bug fixed** as a side effect: movement is a dispatcher-owned
  mechanical action; the dispatcher appends to `visited_locations` correctly by code,
  not by narrator whim.
- **Detection layer (`tool_trace_audit`) remains** as defense-in-depth against dispatcher
  regressions.

### Trade-offs

- **New component: intent classifier.** 1 LLM call per turn that does not exist today.
  Introduces **Mode 5 (classification error)**: the classifier maps "bribe the guard" to
  `attack` instead of `bribe`. Mitigated by: (a) confidence threshold → fallback to
  narrative-free (fail-safe, never fail-dangerous); (b) well-modeled backbone + template
  library reduces ambiguity; (c) `raw_interpretation` field lets the narrator signal
  discrepancy in prose. Mode 5 is a **trade-off accepted explicitly**: it loses
  mechanical interest but never corrupts state.
- **New component: adventure module structure (three layers).** Each adventure module
  must define a backbone (zones, boss, NPCs) and probabilistic encounters. This is
  **design work, not code work** — but lighter than a full state graph per zone: the
  backbone is a small list of fixed elements, and probabilistic encounters are optional
  per zone. Narrative zones require zero structure. The Ignarok module (currently free
  SKILL.md) must gain a backbone + encounter layer. This is the **condition of
  adoption**, not a follow-up.
- **Backbone semantic correctness is not guaranteed by the validator.** The
  deterministic validator catches structural errors (invalid probabilities, unknown
  template references, missing zones). It cannot catch semantic errors (an encounter
  that should be mechanical is placed in a narrative zone). **Human review of the first
  version of each adventure module's backbone is required before production.**
- **Narrative freedom is preserved** in two ways: (a) narrative zones where the narrator
  creates freely by design; (b) any player action that the classifier doesn't map to a
  mechanical template falls back to narrative-free. The machine is only the "when to
  roll dice" layer, not the game.
- **Variance between playthroughs is structural, not just narrative.** Two campaigns of
  the same Ignarok share the backbone (same boss, same zones) but differ in: which
  probabilistic encounters are active, dice roll results, and all narrative prose. This
  is more variance than a fixed gamebook, less variance than pure free-form — by design.

### Conditions that invalidate this decision

1. The backbone + encounter structure cannot be authored for a given adventure module
   (too complex, too open-ended) — would need to fall back to Alternative A (narrow
   tools only) for that module while keeping the dispatcher for modules that can be
   structured.
2. The intent classifier's accuracy is too low even with a well-modeled backbone,
   causing too many actions to fall into narrative-free fallback — would need a
   stronger classifier model or a different classification approach (e.g. structured
   output with the template enum as a literal).
3. Gameplay design requires mechanical actions that cannot be expressed as
   template + params — would need to extend the template library or add custom
   dispatcher logic for that action.
4. The probabilistic encounter layer proves too rigid (e.g. the adventure needs
   encounters that emerge dynamically from narrative state, not from a pre-defined
   list) — would need to extend the encounter model or allow the narrator to propose
   encounters that the dispatcher validates and rolls.

### Migration path

1. **Engine primitivas**: add `apply_healing`/`apply_damage` to `src/gamebook/mcp/server.py`
   (bounded, invariant-checked, `source` Enum) and to the tool contract in
   `docs/CONTRACTS.md` §6. Remove `skill`/`stamina`/`luck` from
   `update_character_sheet`'s accepted fields.
2. **Template library**: create `templates.yaml` with the generic mechanical action
   templates (`risky_action`, `skill_check`, `rest_heal`, `move`, `combat`). Shared
   across all modules. Validated once.
3. **Ignarok backbone + encounters**: define the backbone (zones, boss, key NPCs,
   victory condition) and probabilistic encounters per zone. Start with one zone (e.g.
   dark_ravine) as a pilot. Human review before production. Narrative zones need no
   structure — they stay as SKILL.md lore.
4. **Intent classifier**: new component in `src/gamebook_web/harness/` — an LLM call
   that maps player free-text to a template + bounded params, or to `narrative_free`
   fallback. Confidence threshold configurable.
5. **Deterministic dispatcher**: new component that reads the template + params,
   executes mandatory_checks via the engine, rolls probabilistic encounters on zone
   entry (once, persisted), collects results, and passes them to the narrator.
   Zero LLM calls.
6. **Narrator tool restriction**: update `_NARRATOR_ALLOWED_TOOLS` to exclude all
   mutation tools. Update system prompt — narrator no longer needs tool-call guidance
   for dice/combat/healing; it receives pre-computed results and active encounter state.
7. **Validator**: deterministic schema + invariant checker for adventure module
   backbones and encounter lists. Rejects invalid probabilities, unknown template
   references, missing zones.
8. **Detection layer rework**: `tool_trace_audit` (already implemented) must be
   reworked to handle the split-trace architecture — the dispatcher's tool calls
   happen outside the narrator's `agent.run()`, so the audit must receive both traces
   combined. Mode 1 and Mode 4 checks shift from presence-based ("was roll_dice
   called?") to cross-reference-based ("does the event's roll_result match the
   dispatcher's computed result?"). Unit tests updated accordingly. See "Detection
   layer" section above for full detail.

---

## References

- [ADR-018 — Multi-tenant engine via per-call `campaign_id`](./ADR-018-multi-tenant-engine-per-call-campaign-id.md) — `ScopedMCPToolset`, "prevention, not detection"
- [ADR-029 — Narrator as tool-use agent](./ADR-029-narrator-as-tool-use-agent-eliminate-effects.md) — Alternativa E (deterministic combat loop), atomicity trade-off
- `docs/CONTRACTS.md` §2 (`Attribute` invariant), §6 (MCP tool contract)
- `.specify/memory/constitution.md` Principle I — Numbers Never in Prose
- `src/gamebook_web/harness/tool_trace_audit.py` — detection layer (Modes 1 & 4)
- `src/gamebook_web/harness/agent.py` — `PydanticNarrator`, `_NARRATOR_ALLOWED_TOOLS`
- `src/gamebook/mcp/server.py` — `update_character_sheet`, combat tools
- OWASP Top 10 for LLM Applications — LLM06:2025 Excessive Agency (minimize tool
  functionality/permissions; prefer narrow, typed tools with server-side validation)
- [OpenAI — Function calling guide](https://developers.openai.com/api/docs/guides/function-calling),
  principle 3 ("Offload the burden from the model and use code where possible")
- Empirical reproduction #1: `NARRATOR_MODEL=openai:gpt-4o-mini`, 2026-07-04, real
  docker-compose stack
- Empirical reproduction #2: `NARRATOR_MODEL=openai:gpt-5-chat-latest`, 2026-07-05,
  real docker-compose stack, 9-turn play session, Postgres-confirmed state
