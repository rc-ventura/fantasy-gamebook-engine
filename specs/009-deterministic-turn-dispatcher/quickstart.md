# Quickstart: Deterministic Turn Dispatcher (Pure Narrator) — 009

**Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)

Validates the MVP checkpoint (User Story 1) end-to-end. Reuses ADR-033's own empirical
method — a real play session against a real model, not a synthetic test — since that is
exactly how the current gap was found, and mocked-provider tests alone were shown (spec
008's own learning lesson) to be insufficient for this class of bug.

## Prerequisites

- `ANTHROPIC_API_KEY` (or an OpenAI/OpenRouter key) set — this validation is only
  meaningful against a real model, per FR-002's "regardless of which AI model."
- At least one zone migrated to `backbone.yaml` with a `probabilistic_encounters` entry
  (e.g. `stone_archway`'s guardian, per `contracts/adventure-module-schema.md`) and one
  `narrative_zones` entry, so both mechanical and free-narrative paths are exercised.
- `uv run pytest tests/qa/test_adventure_structure.py -q` passes (FR-010's validator) —
  run before any live session.

## Story 1 — a hero's stats can never be corrupted by an invented outcome

1. Start a session and reach a zone with a `risky_action` or `skill_check` template
   attached (or the `stone_archway` combat).
2. Take the risky action / enter combat.
3. Read the recorded `Event` log (`read_events`) and the character sheet
   (`read_character_sheet`) for that turn.
4. **Expected**: the stamina/luck delta in the character sheet exactly matches a
   `roll_dice`/`test_luck`/`apply_damage`/`apply_healing` result logged for that turn —
   never a value with no corresponding tool-call result.
5. Repeat with a **second, different** model (e.g. switch `NARRATOR_MODEL` to a
   cheaper/weaker one) for the same kind of action.
6. **Expected**: identical guarantee holds — the model choice must not affect whether
   step 4 passes (FR-002, SC-001). This is the acceptance bar ADR-033's two empirical
   reproductions failed; it must now hold for both.

## Story 1 (extended encounter) — combat resolves under the same guarantee

1. Trigger the `stone_archway` guardian fight (`probability: 1.0`, always present).
2. Let combat run multiple rounds (don't flee immediately).
3. **Expected**: every round's stamina change traces to a `resolve_combat_round` result
   (FR-012) — inspect `read_events` for a `combat_round` (or equivalent) entry per round,
   not just a single pre/post delta.

## Story 3 — free text with no mechanical stakes still works

1. In a `narrative_zones` area (e.g. `foothills`), type a free-text action with no
   mechanical implication ("I hum a tune while I walk").
2. **Expected**: the story continues with a freely narrated response, no forced menu, no
   error, no stat change (FR-008, SC-003).
3. Type an action with mechanical stakes but ambiguous phrasing ("I do something risky").
4. **Expected**: if the intent classifier's confidence is below threshold, the system
   defaults to free narration rather than guessing and applying a consequence (FR-004,
   edge case in spec.md).

## Structural validation (FR-010/FR-011, run before any of the above)

```bash
uv run pytest tests/qa/test_adventure_structure.py -q
```

**Expected**: fails loudly on a broken `template` reference, an out-of-bounds
`probability`, or a zone appearing in both `probabilistic_encounters` and
`narrative_zones`. A pass here is necessary but — per FR-011 — **not sufficient** for
release; a human must still review `backbone.yaml` before real players see it.

## Regression

```bash
uv run pytest tests/engine tests/server -q
uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q   # plugability audit
```

**Expected**: unaffected — `domain`/`rules`/`combat`/`storage` and the MCP tool
contract's existing 18 tools are unchanged; only 2 new tools are added and the
narrator's toolset shrinks to empty.
