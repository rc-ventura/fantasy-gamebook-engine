# pydantic-ai's output_validator can see per-call context via deps_type + RunContext, enabling semantic (not just structural) validation

**Date**: 2026-08-09
**Spec**: [009-deterministic-turn-dispatcher](../../specs/009-deterministic-turn-dispatcher/) (ADR-033)
**Code**: `src/gamebook_web/harness/agent.py::PydanticNarrator`

## What happened

`PydanticNarrator`'s `output_validator` originally only checked the `Scene` output's own
shape (non-empty narrative, choices present unless terminal) — it had no way to check the
narrative's *content* against the turn's settled facts (`NarratorContext.turn_outcome`),
because the validator function only received the output object:

```python
@self._agent.output_validator
def _validate_scene_structure(scene: Scene) -> Scene:
    ...
```

Adding a semantic check (issue #27: reject a narrative that claims the hero was hit when
`hero_damage_taken == 0`) needed access to that turn's `turn_outcome` *inside* the
validator — but the validator is registered once at `Agent.__init__` time, not per call.

## The resolution

`pydantic_ai.Agent` supports a generic `deps_type` (declared once, at construction) whose
value is supplied per-call via `agent.run(..., deps=...)`. When `deps_type` is set, an
`output_validator` (and tool functions) can declare a first parameter
`ctx: RunContext[DepsT]` and read `ctx.deps` — the exact object passed to that specific
`run()` call:

```python
self._agent: Agent[NarratorContext, Scene] = Agent(
    model=model, output_type=Scene, deps_type=NarratorContext, ...
)

@self._agent.output_validator
def _validate_scene_structure(ctx: RunContext[NarratorContext], scene: Scene) -> Scene:
    outcome = ctx.deps.turn_outcome if ctx.deps is not None else None
    ...

# at call time:
await self._agent.run(prompt, deps=context, ...)
```

`RunContext` doesn't need special construction — pydantic-ai supplies it automatically
based on the validator function's declared signature (reflection over the parameter list,
same mechanism used for tool functions).

## Rule

When an `output_validator` (or a tool) needs to check the model's output against
request-scoped data that isn't part of the output schema itself, reach for `deps_type` +
`RunContext` before reaching for a module-level/closure workaround. It composes cleanly
with `ModelRetry` — the validator can reject on either a structural violation or a semantic
one using the same mechanism, and the model sees the same kind of retry-with-explanation
either way.
