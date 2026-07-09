# Data Model: Deterministic Turn Dispatcher (Pure Narrator) — 009

**Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

Existing `domain` entities (`CharacterSheet`, `World`, `Event`, `Combat`) are
**unchanged** — this feature changes who calls the tools that mutate them, not their
shape (`docs/CONTRACTS.md` §2 stays as-is). What's new lives at the harness layer
(`src/gamebook_web/harness/`) and as adventure-module content (swap boundary #2).

---

## Graph nodes (`src/gamebook_web/harness/dispatcher.py`, new)

The `pydantic_graph.Graph` that replaces `PydanticNarrator`'s free-tool-use loop.
`GraphRunContext` carries a `DispatchState` dataclass through the run.

```python
@dataclass
class DispatchState:
    campaign_id: str
    toolset: MCPToolset
    context: NarratorContext        # existing type, unchanged
    adventure: AdventureStructure   # loaded once per turn (backbone + templates)
    classification: IntentClassification | None = None
    outcome: TurnOutcome | None = None
```

| Node | Calls | Returns (→ = edge) |
|---|---|---|
| `ClassifyIntent` | 1 LLM call (`Agent(..., name="intent_classifier")`, structured output, no tools) | → `MechanicalDispatch` (confident + template found) or `NarrativeFree` (low confidence or no mechanical match — FR-004) |
| `MechanicalDispatch` | 0 LLM calls; looks up the template, runs its `mandatory_checks` via `call_engine()` | → `CombatRound` (template == `combat`) or → `Narrate` (single-check templates: `risky_action`, `skill_check`, `rest_heal`, `move`) |
| `CombatRound` | 0 LLM calls; one `resolve_combat_round` per visit | → `CombatRound` (combat still active — the one cyclic edge) or → `Narrate` (combat ended: victory/defeat/fled) |
| `NarrativeFree` | 0 LLM calls | → `Narrate` (no `TurnOutcome`, narrator improvises fully) |
| `Narrate` | 1 LLM call (`Agent(..., name="pure_narrator")`, `output_type=Scene`, `toolsets=[]`) | → `End[Scene]` |

Both agents get an explicit `name=` (not left to variable-name inference) — this project
already runs OTel instrumentation (ADR-024) and two nameless agents in one process trace
indistinguishably; the `pydantic-ai` skill flags this as exactly the case where an
explicit name pays off.

Every path passes through exactly one `Narrate` node before `End` — this is the
structural guarantee FR-001/FR-002 depend on (see research.md's graph-engine decision).

---

## `IntentClassification` (new, `harness/dispatcher.py`)

```python
class IntentClassification(BaseModel):
    action: str | None       # a template/encounter id from the current zone, or None
    confidence: float = Field(ge=0.0, le=1.0)
    template: str | None     # which entry in templates.yaml `action` maps to, if any
```

No numeric game field (no `roll_result`, no `stamina`, no `success`) — the classifier
names an action, it never states an outcome. This is what makes fabrication structurally
unavailable to this LLM call, not merely discouraged.

## `TurnOutcome` (new, `harness/dispatcher.py`)

```python
class TurnOutcome(BaseModel):
    action: str
    template: str
    checks: list[dict[str, Any]]   # raw results from each call_engine() invocation, in order
    final_state: dict[str, Any]    # character/world deltas actually applied, for the narrator's context
```

Handed to `Narrate` as settled fact — per spec.md's own Key Entities section, "handed to
the narration step as settled fact, never something the narration step invents itself."

---

## Adventure module content (swap boundary #2 — new files, `SKILL.md` retained)

### `AdventureStructure` (loaded from `backbone.yaml`, validated as a `BaseModel`)

```python
class ProbabilisticEncounter(BaseModel):
    id: str
    probability: float = Field(ge=0.0, le=1.0)
    template: str                      # references templates.yaml
    params: dict[str, Any]

class AdventureStructure(BaseModel):
    zones: list[str]                                        # Layer 1 — backbone
    key_npcs: list[str]
    boss: str
    victory_condition: dict[str, Any]                        # e.g. {"flag": "malachar_defeated"}
    opening_location: str
    probabilistic_encounters: dict[str, list[ProbabilisticEncounter]] = {}   # Layer 2, keyed by zone
    narrative_zones: list[str] = []                           # Layer 3 — explicitly free
    reviewed_by: str | None = None    # FR-011 human-review gate — see below
    reviewed_at: str | None = None    # ISO-8601; both fields set together or not at all
```

Validation rules (enforced by the structural validator, FR-010):
- Every zone referenced anywhere (`opening_location`, encounter keys, `narrative_zones`)
  MUST appear in `zones`.
- Every `template` referenced by a `ProbabilisticEncounter` MUST exist in the shared
  template library.
- `reviewed_by` and `reviewed_at` MUST both be present (FR-011 — a passing structural
  check alone is necessary but never sufficient for release; this is the validator's
  concrete, checkable proxy for "a human signed off," not a claim that it verifies review
  *quality*). A `backbone.yaml` failing only this check is a distinct validator failure
  from a structural error — surface it separately so an author isn't left guessing
  whether their YAML is malformed or just unreviewed.
- `probability` MUST be in `[0.0, 1.0]`.
- A zone MUST NOT appear in both `probabilistic_encounters` and `narrative_zones`
  (ambiguous layer).
- A zone with no entry in either `probabilistic_encounters` or `narrative_zones` is
  Layer 3 by default (the incremental-migration case from research.md).

### `MechanicalSituationTemplate` (loaded from the shared `templates.yaml`)

```python
class CheckStep(BaseModel):
    tool: str                                 # e.g. "test_luck", "roll_dice", "apply_damage"
    args: dict[str, Any] = {}                 # may reference "${param_name}" — resolved, never eval()'d
    comparator: dict[str, Any] | None = None  # {"op": "le", "left": "${result}", "right": "${skill.current}"}
    on_success: list[CheckStep] = []
    on_failure: list[CheckStep] = []

class MechanicalSituationTemplate(BaseModel):
    name: str                                 # "risky_action", "skill_check", "rest_heal", "move", "combat"
    description: str
    params: dict[str, ParamSpec]              # bounded — {"risk_amount": {"type": "int", "min": 1, "max": 3}}
    mandatory_checks: list[CheckStep]
```

`comparator`'s `op` is a closed enum (`eq`, `ne`, `lt`, `le`, `gt`, `ge`) — structured
data interpreted by the dispatcher, never a string passed to `eval()`/`exec()` (ADR-033's
"Structural requirement 1").

---

## State transitions

```
World.flags["encounter.<zone>.<encounter_id>"]:
  (absent) --first entry to <zone>, dispatcher rolls-->  True | False
  True | False --revisit <zone> in same playthrough-->  unchanged (FR-007)
```

```
CombatRound (graph node, per-turn, not persisted across turns):
  active --resolve_combat_round: still fighting--> active (cycle)
  active --resolve_combat_round: hero or last enemy at 0 stamina--> ended
  active --flee_combat (only if flee_allowed)--> ended
```

No new domain-level state transitions — `Attribute`, `Combat`, `World` invariants
(`docs/CONTRACTS.md` §2) are unchanged; only the *caller* of the tools that drive those
transitions changes (dispatcher, not narrator).
