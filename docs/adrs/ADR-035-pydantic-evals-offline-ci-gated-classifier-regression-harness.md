# ADR-035: Pydantic Evals as an offline, CI-gated regression harness for the classifier — not a runtime/online mechanism

**Status**: Accepted
**Date**: 2026-07-11
**Related spec**: [009-deterministic-turn-dispatcher](../../specs/009-deterministic-turn-dispatcher/)
**Related ADRs**: [ADR-030](./ADR-030-observability-and-evals-otel-stack.md) (this ADR concretizes decision #3 — HOW `pydantic-evals` actually plugs into the codebase — it does not replace ADR-030), [ADR-033](./ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md) (the "numbers never invented in prose" principle this regression class violates)
**Code**: `src/gamebook_web/harness/dispatch_types.py:76` (`build_classifier_agent`), `src/gamebook_web/harness/graph.py` (`ClassifyIntent`, `MechanicalDispatch`, `_resolve_zone_encounters`)

---

## Context

A live end-to-end test of spec 009's deterministic turn dispatcher (`docker compose --profile gameobs up -d --build` — real Postgres, real Dex OIDC, real `openai:gpt-4o-mini`) found that the `move` mechanical template silently never dispatched. `ClassifyIntent` correctly recognized the player's intent (`action=move template=move confidence=0.90`), but `IntentClassification.params` was always empty — `build_classifier_agent`'s system instructions told the model to set `action`/`confidence`/`template`, but never told it to populate `params` (e.g. `destination` for `move`). `MechanicalDispatch`'s existing safety guard then silently fell back to free narration on every attempt. The narrator, receiving no `turn_outcome`, freely narrated full zone transitions ("you emerge into the Shattered Trailhead...") while `World.location` in Postgres never advanced past `stone_archway` — confirmed by direct query. Reproduced identically across two different player phrasings.

Fixed same-session by (a) adding explicit params-filling instructions to the classifier's system prompt, and (b) a deterministic, code-side fallback in `MechanicalDispatch` that matches `_adjacent_zones` candidates against the player's raw text — defense in depth, not a replacement for (a). Both were validated live: one test phrase relied on the fallback, a second phrase with no zone name in the text proved the LLM itself now populates `params`.

As part of this same hardening pass, audit logging was added (in scope for spec 009, since it documents spec 009's own new mechanism):
- `_resolve_zone_encounters` now logs every probabilistic-encounter roll: zone, encounter id, `source` (`forced_always`/`forced_never`/`rolled`/`remembered`), roll value, threshold, and the resulting presence.
- `ClassifyIntent`/`MechanicalDispatch` now log and trace `classification.params` plus a `params_source` field (`classifier`/`fallback_substring_match`/`encounter`), so it is auditable, per turn, whether the LLM itself supplied a required parameter or the code-side heuristic covered for it.

This closed the *logging* gap, but not the *regression-prevention* gap. `specs/009-deterministic-turn-dispatcher/tasks.md` shows T028/T032/T037 — the tasks meant to validate the classifier against real models — were all one-off manual sessions: *"Validated live in a prior session with `openai:gpt-4o-mini`... Marked accepted."* No repeatable dataset, no CI gate, nothing re-run when the prompt or model changes. That is exactly why the `move`/`params` bug shipped past those tasks and was only caught by an unrelated, ad hoc live-inspection session.

`ADR-030` already decided `pydantic-evals` as the evaluation library (for spec 004's FR-014/FR-015), but never specified *how* it plugs into a running codebase, and it was never implemented — `grep -r "pydantic_evals"` returns zero results anywhere in this repo. This ADR fills that gap concretely, using the `move` bug as the worked example.

## Decision

Adopt `pydantic-evals` as an **offline, batch regression harness that lives entirely outside the running application**, with zero coupling to the production request path.

**1. Placement**: a new `tests/evals/` directory, parallel to this repo's existing `tests/engine`/`tests/server`/`tests/qa` convention.
```
tests/evals/
  datasets/classifier_moves.yaml   # versioned data, not Python literals
  test_classifier_eval.py          # a normal pytest file
```

**2. Zero runtime coupling**: `graph.py`, `dispatch_types.py`, and the `DispatcherNarrator` serving real player turns never import `pydantic_evals`. Nothing in the eval harness is reachable from a live HTTP request.

**3. Reuse, don't reimplement**: eval "task" functions call the exact same production function the app calls — `build_classifier_agent(model)` from `dispatch_types.py` — never a copy or paraphrase of the prompt. An eval failure means the real prompt is wrong, not a stale fixture.
```python
async def classify(prompt: str) -> IntentClassification:
    agent = build_classifier_agent("openai:gpt-4o-mini")  # production function, unmodified
    result = await agent.run(prompt)
    return result.output
```

**4. Datasets are YAML, not code**: `Dataset.to_file()`/`Dataset.from_file()` — reviewed like any other fixture, so adding a regression case is a data change, not a code change.

**5. Explicitly offline/batch, not online/production-monitoring**: the harness evaluates a fixed, curated dataset of synthetic cases on demand. It does not score live player traffic in real time. This reaffirms, rather than merely inherits, ADR-030's own "Conditions that invalidate this decision" #3 (*"real-time online evals... that Pydantic Evals does not support adequately"*) — if online/production-traffic scoring is ever needed, it is a different mechanism and a different ADR, not an extension of this one.

**6. Real LLM calls, gated like this repo's existing live-LLM tests**: no mocking — same category as the tests that already produce this suite's **80 skipped** count (Postgres/live-LLM, gated behind env credentials). Eval tests skip identically when the relevant API key env var is absent.

**7. CI placement**: a separate job/step from the fast, hermetic, no-network suite (`tests/engine`/`tests/server`/`tests/qa`). Gated behind real API-key secrets being configured in CI, and **not** run on every push — token cost and LLM non-determinism make that both expensive and flaky. Triggered instead by: manual dispatch, a schedule (e.g. nightly), or a path filter on `src/gamebook_web/harness/dispatch_types.py`, `src/gamebook_web/harness/graph.py`, or any `adventure_modules/**/backbone.yaml`. This is regression-testing of prompt+model behavior — closer to a lightweight CI gate on a prompt/model artifact than to ML training/deployment MLOps.

**8. First dataset case is the bug just found**, not a hypothetical:
```yaml
name: classifier_moves
cases:
  - name: move_to_adjacent_zone_implicit
    inputs: |
      PLAYER ACTION: <<<Begin the climb into the mountain.>>>
      AVAILABLE MECHANICAL ACTIONS: - action="move" destination=one of ['dark_ravine']
    expected_output: {action: move, template: move, params: {destination: dark_ravine}}
    evaluators: [EqualsExpected]
```

## Alternatives considered

### Alternative A: Keep relying on manual live-validation sessions (status quo)

**Why not chosen**: this is precisely the practice that let the `move`/`params` bug ship past T028/T032/T037's "accepted" marks — an anecdotal, one-time pass has no way to catch a regression the next time the prompt, model, or adventure content changes.

### Alternative B: Bespoke eval scripts instead of `pydantic-evals`

**Why not chosen**: already rejected by ADR-030 for the same reasons (more maintenance, no span-based evaluation, no regression tracking); nothing learned today changes that calculus.

### Alternative C: Wire evals into the running app (e.g. shadow-evaluate every real turn)

**Why not chosen**: conflates two different problems. Regression-testing a prompt against a fixed dataset (this ADR) is offline by nature; scoring live production traffic in real time is a different, unsolved problem that ADR-030 already flagged as out of scope for `pydantic-evals`. Bolting the former onto the request path would add latency/cost to every real player turn for no benefit — the dataset doesn't need live traffic to be evaluated.

## Consequences

### Accepted

- The exact bug class found today (a classifier field silently never populated) becomes a permanent, re-runnable regression case instead of institutional memory.
- Eval failures point at the real production prompt/function, not a maintained duplicate.
- CI cost is bounded and predictable — a separate, path-filtered/scheduled job, not a tax on every commit.
- Datasets grow by data changes (YAML), keeping the bar for adding a regression case low.

### Trade-offs

- `pydantic-evals` is a new dev dependency (MIT, per ADR-030) with its own API surface to track as it evolves.
- Real API calls in CI mean real cost and non-zero flakiness (LLM non-determinism) — mitigated by gating/scheduling, not eliminated.
- This ADR only covers the classifier's structured-output correctness (`action`/`template`/`params`). It does not cover narrator prose quality (e.g. today's separate finding that the narrator can narrate an event — "the guardian... barely grazing you" — not backed by the settled `TurnOutcome`); that would need its own dataset/evaluator and is out of scope here.

### Conditions that invalidate this decision

This decision should be **revisited** if:

1. A future phase requires real-time scoring of live production traffic — `pydantic-evals` does not support this adequately (ADR-030), and this ADR does not attempt to stretch it to.
2. The `pydantic-evals` API diverges enough that dataset YAML files become brittle across versions (same condition ADR-030 already names).
3. CI eval-job cost or flakiness grows large enough that the schedule/path-filter gating needs to change (e.g. moving from nightly to weekly, or adding a manual-approval gate).

## References

- [ADR-030 — Observability and evaluation stack](./ADR-030-observability-and-evals-otel-stack.md)
- [ADR-033 — Engine-side guard against narrator-supplied attribute values](./ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md)
- [Spec 009 — Deterministic turn dispatcher](../../specs/009-deterministic-turn-dispatcher/spec.md), `tasks.md` T028/T032/T037
- Pydantic Evals docs: https://ai.pydantic.dev/evals
