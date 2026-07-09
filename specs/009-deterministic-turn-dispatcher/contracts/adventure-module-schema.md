# Contract: Adventure module structure schema (swap boundary #2 extension) — 009

**Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)

Extends swap boundary #2 (`adventure-module`) — see `data-model.md` for the full
Pydantic model definitions. This document is the file-format contract an adventure
author (human or AI-assisted-draft-then-human-reviewed, per spec.md's Assumptions) must
follow.

---

## File layout per adventure module

```
.claude/skills/<adventure-name>/
  SKILL.md            # unchanged — narrative lore, tone, opening hook, bestiary flavor text
  backbone.yaml        # NEW — Layers 1-2 (fixed backbone + probabilistic encounters)

adventure_modules/                # NEW top-level directory — NOT under .claude/skills/
  templates.yaml                   # NEW — shared across every adventure module, not per-module
```

`backbone.yaml` stays co-located with its module's `SKILL.md` — matches existing
precedent (`agent.py`'s `_load_adventure_lore()` already reads
`.claude/skills/ignarok/SKILL.md` from the web backend). `templates.yaml` is
deliberately **outside** `.claude/skills/`: that directory's contract is "each
subdirectory is a Claude Code Skill" (needs its own `SKILL.md`), which a bare
shared-data directory doesn't satisfy — see `research.md`'s resolved decision on this.

A module with no `backbone.yaml` behaves exactly as it does today (fully Layer 3 /
narrative-free) — this is the incremental-migration path from research.md, not an
error case.

## `backbone.yaml` — example (Ignarok, partial)

```yaml
backbone:
  zones: [mountain_pass, dark_ravine, stone_archway, malachar_lair]
  key_npcs: [Malachar, The Hermit]
  boss: malachar
  victory_condition: { flag: malachar_defeated }
  opening_location: mountain_pass

probabilistic_encounters:
  dark_ravine:
    - id: cave_bat
      probability: 0.4
      template: combat
      params: { enemies: [{ name: "Cave Bat", skill: 4, stamina: 3 }], flee_allowed: true }

  stone_archway:
    - id: archway_guardian
      probability: 1.0            # always present — a backbone guardian, not variance
      template: combat
      params: { enemies: [{ name: "Archway Guardian", skill: 8, stamina: 10 }], flee_allowed: false }

narrative_zones:
  - foothills
  - mountain_trails

# FR-011 — set only by an actual human reviewer, never by an authoring tool or AI draft.
# Absent (both null) until that sign-off happens; the validator fails either way if only
# one of the two is set.
reviewed_by: null
reviewed_at: null
```

**Validation** (structural validator, FR-010 — fails the build, not a runtime check):
- Every zone named anywhere resolves against `backbone.zones`.
- Every `template` value resolves against `templates.yaml`.
- `probability` ∈ `[0.0, 1.0]`.
- No zone appears in both `probabilistic_encounters` and `narrative_zones`.
- `params` for each encounter match the referenced template's declared `params` schema
  (names, types, bounds).
- `reviewed_by` and `reviewed_at` are both present (FR-011 — reported as a distinct
  failure reason from a structural error, so an author can tell "malformed" apart from
  "structurally fine, just not yet signed off").

## `templates.yaml` — shared library (excerpt)

```yaml
templates:
  risky_action:
    params:
      risk_amount: { type: int, min: 1, max: 3 }
      risk_source: { type: enum, values: [trap, magical_trap, environment, curse] }
    mandatory_checks:
      - tool: test_luck
        on_failure:
          - tool: apply_damage
            args: { amount: "${risk_amount}", source: "${risk_source}" }

  combat:
    params:
      enemies: { type: list }
      flee_allowed: { type: bool }
    mandatory_checks:
      - tool: start_combat
        args: { enemies: "${enemies}", flee_allowed: "${flee_allowed}" }
      # CombatRound graph node loops resolve_combat_round until Combat ends —
      # not expressible as a flat mandatory_checks list; the dispatcher special-cases
      # template == "combat" (see data-model.md's MechanicalDispatch node).
```

`${param_name}` substitution is a closed, structured lookup against the resolved
`params` dict — **never** `eval()`/`exec()`/arbitrary string interpolation into code
(ADR-033 structural requirement 1; see `data-model.md`'s `CheckStep.comparator`).

## Consumers

- **Dispatcher** (`harness/dispatcher.py`, new): loads `backbone.yaml` +
  `templates.yaml` once per turn (or cached per campaign), resolves the classified
  action against them.
- **Structural validator** (`tests/qa/test_adventure_structure.py`, new): loads and
  validates every module's `backbone.yaml` against `templates.yaml` before merge (FR-010),
  independent of any live campaign.
- **Narrator**: does not read these files directly — receives only the resolved
  `TurnOutcome` and the existing `SKILL.md` lore text for atmosphere.
