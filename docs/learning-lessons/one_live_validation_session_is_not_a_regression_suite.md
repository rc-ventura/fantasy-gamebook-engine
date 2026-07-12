# One live-validation session is not a regression suite: a classifier field silently unpopulated shipped past a task marked "accepted"

**Context:** Discovered during spec 009 (`feat/009-deterministic-turn-dispatcher`), during a
full live end-to-end test (`docker compose --profile gameobs` — real Postgres, real Dex
OIDC, real `openai:gpt-4o-mini`) run specifically to sanity-check Phases 3–6 before closing
the spec.
**Date:** 2026-07-11
**Future intent:** Any task in a spec whose acceptance evidence is "ran it live once, looked
right" must either be re-run on every relevant change (CI-gated, per ADR-035) or explicitly
labeled as a one-time smoke test, not permanent acceptance evidence.

---

## What happened

`specs/009-deterministic-turn-dispatcher/tasks.md`'s T028 was a "live validation against
real models" task. It was executed once, manually, in a prior session with
`openai:gpt-4o-mini`, and marked: *"Validated live in a prior session... Marked accepted."*
No repeatable dataset. No CI gate. Nothing re-run when the prompt or model changed.

Today's live E2E session found that the `move` mechanical template silently never
dispatched. `ClassifyIntent` correctly recognized the player's intent
(`action=move template=move confidence=0.85-0.90`), but `IntentClassification.params` was
always empty — `build_classifier_agent`'s system instructions
(`src/gamebook_web/harness/dispatch_types.py`) told the LLM to set `action`/`confidence`/
`template`, but never mentioned that `params` existed or needed to be populated.
`MechanicalDispatch`'s existing safety guard (`graph.py`) then silently fell back to free
narration on every single `move` attempt.

The narrator, receiving no `turn_outcome`, freely and convincingly narrated full zone
transitions ("you emerge into the Shattered Trailhead...") while `World.location` in
Postgres never advanced past `stone_archway` — confirmed by direct SQL query, reproduced
identically across two different player phrasings. This is a state/narrative desync, not
just a missing number: an entire persisted game-progression field silently diverged from
what the player was told happened. Nothing in the existing test suite (340 tests, all
green) caught it, because no test exercised a live LLM's actual willingness to populate a
structured-output field it was never told about — `TestModel`/`FunctionModel` unit tests
supply canned outputs and can't surface a real model's tendency to leave a field empty.

## The fix

Same-session: (a) added an explicit instruction to the classifier's system prompt telling
it to populate `params` using values from the candidate bounds already shown per-turn
(e.g. `"destination=one of [...]"` for `move`), and (b) a deterministic code-side fallback
in `MechanicalDispatch` matching the adjacency list against the player's raw text, as
defense-in-depth — not a replacement for (a).

Both validated live: one test phrase exercised the fallback; a second phrase with no zone
name in the text at all proved the LLM itself now correctly populates `params` after the
prompt fix — isolating that the actual fix, not just the safety net, works.

## The deeper lesson

T028 (and T032, T037 — the other "live validation" tasks in this spec) shared the same
shape: a single, anecdotal, manual session with a real model, marked as permanently
"accepted" acceptance evidence. That pattern validates *one moment*, not a contract — it
cannot catch a regression the next time the prompt, model, or adventure content changes.
It is exactly why this bug shipped past a task explicitly designed to catch it.

This is why `ADR-035` (`docs/adrs/ADR-035-pydantic-evals-offline-ci-gated-classifier-regression-harness.md`)
was written same-session: adopt `pydantic-evals` as an offline, CI-gated, versioned-dataset
regression harness that reuses the exact same `build_classifier_agent` production function
as its "task" — so this bug class gets a permanent, re-runnable regression case (the exact
`move`/`destination` scenario above becomes dataset case #1) instead of living only in
institutional memory or a session transcript.

## A related, still-open observation

The same live session confirmed a full mechanical combat dispatch
(`start_combat` → 3× `resolve_combat_round` → `end_combat`) ran correctly end-to-end with
real dice/engine state (`hero_damage=0` every round, confirmed via engine logs and
unchanged stamina 20/20) — the dispatcher itself was airtight. But the narrator
(`gpt-4o-mini`) still narrated a fabricated event ("the guardian... barely grazing you")
contradicting the settled `TurnOutcome`. Filed as
[GitHub issue #27](https://github.com/rc-ventura/fantasy-gamebook-engine/issues/27) — a
distinct, softer reliability concern: even when the deterministic dispatcher is provably
correct, prose-level fidelity to the settled facts is a separate failure mode that
structural output validation (narrative non-empty, choices present) does not catch. Likely
cause: `TurnOutcome` is handed to the narrator as a dense, unstructured dict repr rather
than a pre-summarized natural-language fact ("the enemy never landed a hit"), putting the
burden of correct aggregation on the LLM itself.

## Relation to ADRs and next steps

- **ADR-035** — the direct response to this lesson: offline, CI-gated eval harness so this
  bug class becomes a permanent regression case, not a session transcript.
- **ADR-033** — the "numbers never invented in prose" principle this bug (and the related
  observation above) both threaten from different angles: one via a silently-empty
  structured field, the other via free-text narration of an event that didn't happen.
- **Next steps**: `specs/009-deterministic-turn-dispatcher/tasks.md` T045/T046 record the
  fix and the audit-logging hardening (`params`/`params_source`/`encounter_roll` logging)
  that make this bug class observable in logs even before the eval harness exists.
  GitHub issues [#24](https://github.com/rc-ventura/fantasy-gamebook-engine/issues/24) and
  [#27](https://github.com/rc-ventura/fantasy-gamebook-engine/issues/27) track the two
  related, still-open gaps (dead audit trail; narrator prose fidelity).
