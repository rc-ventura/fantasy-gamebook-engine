# Pydantic Evals: open-source, OTel-native evaluation framework

**Date**: 2026-07-01
**Slice**: 004-accounts-hardening-obs

---

## Discovery

While researching observability options for spec 004, discovered that
**Pydantic Evals** (`pydantic-evals`, MIT license) is an open-source evaluation
framework that uses OpenTelemetry natively — same stack as the observability
decision (research.md §7) and the narrator harness (ADR-011).

### What it is

- **Code-first** evaluation framework for stochastic functions (LLM calls,
  agents, multi-agent workflows)
- **Does NOT depend on `pydantic-ai`** — works with any AI library or arbitrary
  function
- **Does NOT depend on Logfire** — optional dependency for OTel trace
  integration; works with any OTel backend
- **License**: MIT (same as Pydantic AI)
- **Package**: `pydantic-evals` on PyPI

### Core concepts

1. **Dataset** → contains many **Cases** (test scenarios with inputs + optional
   expected outputs)
2. **Experiment** → runs a Dataset against a **Task** (the function being
   evaluated) using multiple **Evaluators**
3. **EvaluationReport** → results with metrics, assertions, performance data
4. **Evaluators** → score/validate task outputs:
   - **Built-in**: `Equals`, `Contains`, `IsInstance`
   - **LLMJudge**: uses an LLM to evaluate subjective qualities (accuracy,
     helpfulness, instruction-following)
   - **Custom**: Python functions with domain-specific scoring logic
   - **Span-Based**: evaluates internal agent behavior (tool calls, execution
     flow) using OTel traces — not just the final output

### Span-Based Evaluation (the key feature for this project)

The narrator calls MCP tools during generation (ADR-029). Correctness depends
on **which tools were called**, not just the narrative text. Span-Based
Evaluation can assert:

- Did the narrator call `set_character` after combat?
- Did the narrator call `add_event` to log the turn?
- Were the right tool arguments used?

This uses the same OTel traces that `Agent.instrument_all()` emits — evals and
production share the same telemetry pipeline.

### OTel integration

> *"Pydantic Evals uses OpenTelemetry to record traces for each case in your
> evaluations. You can send these traces to any OpenTelemetry-compatible
> backend."*

The traces from eval runs go to the **same backend** as production traces
(Grafana/Tempo, Jaeger, Logfire, etc.). No separate eval infrastructure
needed.

### Example for the gamebook narrator

```python
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import LLMJudge, Contains

dataset = Dataset(
    name="narrator_quality",
    cases=[
        Case(
            inputs={"choice": "attack the goblin"},
            expected_output_contains="goblin",
            evaluators=[
                Contains(text="goblin"),
                LLMJudge(
                    rubric="Narrative is engaging, uses second person, "
                           "no fabricated numbers",
                    include_input=True,
                    model="anthropic:claude-sonnet-4-20250514",
                ),
            ],
        ),
    ],
)

async def narrator_task(inputs):
    return await narrator.narrate(campaign_id, ctx)

report = await dataset.evaluate(narrator_task)
```

### Alternatives considered

| Tool | License | OTel-native | Focused on agents | Notes |
|------|---------|-------------|-------------------|-------|
| **Pydantic Evals** | MIT | Yes | Yes | Code-first, Python, integrates with Pydantic AI |
| DeepEval | Apache 2.0 | No | General LLM | G-Eval, hallucination, relevancy metrics |
| Bespoke (custom OTel + assertions) | — | Yes | — | Roll-your-own, more maintenance |

### Why Pydantic Evals is the natural choice for this project

1. **Same OTel stack**: eval traces and production traces go to the same
   backend (Grafana/Tempo) — one pipeline, one dashboard
2. **Integrates with Pydantic AI**: the narrator is already a Pydantic AI agent
   (ADR-011); evals understand the agent structure
3. **Span-Based Evaluation**: can evaluate whether the narrator called the
   correct MCP tools — critical for gamebook correctness
4. **Code-first**: datasets in Python, versioned in git — aligned with the
   project's testing philosophy (Principle IV)
5. **No Logfire dependency**: works with any OTel backend
6. **MIT license**: no commercial lock-in

## Rule of thumb

| Context | Pattern |
|---------|---------|
| Evaluate narrator output quality | `Dataset` + `LLMJudge` evaluator |
| Evaluate narrator tool calls | Span-Based Evaluation via OTel traces |
| Deterministic output check | `Contains` / `Equals` / `IsInstance` |
| Custom domain logic | Custom evaluator (Python function) |
| Run evals | `dataset.evaluate(task_function)` |
| View eval results | Same OTel backend as production (Grafana/Tempo) |
| Track regressions | Compare eval reports across runs over time |
