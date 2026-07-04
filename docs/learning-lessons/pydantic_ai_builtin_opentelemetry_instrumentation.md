# Pydantic AI has built-in OpenTelemetry instrumentation

**Date**: 2026-07-01
**Slice**: 004-accounts-hardening-obs

---

## Discovery

While researching observability options for spec 004, discovered that
**Pydantic AI has native OpenTelemetry support** — no manual span code needed
for the narrator harness. This creates a natural synergy with the spec 004
decision to use OpenTelemetry (research.md §7, vendor-neutral rationale).

### Built-in classes and functions

1. **`InstrumentationSettings`** (`pydantic_ai.models.instrumented`):
   Configures how spans/metrics are emitted.
   - `tracer_provider`: OTel `TracerProvider` (defaults to global, set by
     `logfire.configure()` or `opentelemetry.sdk.trace.set_tracer_provider()`)
   - `meter_provider`: OTel `MeterProvider` (defaults to global)
   - `include_content`: `bool` — whether to include prompts, completions, and
     tool call args/responses in spans. Set `False` for privacy (don't expose
     user data in the telemetry backend)
   - `include_binary_content`: `bool` — include binary content in events
   - `version`: `Literal[2,3,4,5]` — data format version. v5 is current; uses
     OTel GenAI semantic conventions (`gen_ai.system_instructions`,
     `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.usage.*`)
   - `use_aggregated_usage_attribute_names`: `bool` — prevents double-counting
     tokens in backends that aggregate span attributes

2. **`InstrumentedModel`** (`pydantic_ai.models.instrumented`):
   `WrapperModel` subclass that wraps any model (e.g. `AnthropicModel`) to
   emit OTel spans around each LLM request automatically.

3. **`instrument_model(model, instrument)`**:
   Function that wraps a model in `InstrumentedModel`.

4. **`Agent.instrument()` / `Agent.instrument_all()`**:
   Instance/class methods that activate instrumentation on all models and
   tool calls for the agent. Emits spans for:
   - Each model request (LLM call)
   - Each tool call execution (name, args, response)
   - Agent run span with full message history

### What you get for free (zero manual instrumentation)

```
trace: POST /campaigns/{id}/turn
├── span: narrator.narrate               ← Pydantic AI OTel native
│   ├── span: model_request (LLM call)   ← automatic
│   ├── span: tool_call: set_character   ← automatic
│   ├── span: tool_call: set_world       ← automatic
│   └── span: tool_call: add_event       ← automatic
```

The narrator spans (LLM calls + tool calls) come from `agent.instrument_all()`
with no manual span code in `harness/agent.py`. The rest of the turn
(auth, campaign lookup, DB reads/writes, terminal check) needs standard OTel
instrumentation (e.g. `opentelemetry-instrumentation-fastapi`).

### Backend options (all receive the same OTel data)

| Backend | Type | Setup | LLM-optimized UX |
|---------|------|-------|-------------------|
| Grafana + Tempo + Prometheus | Self-hosted, free | docker-compose with 5 services | No (general-purpose) |
| Logfire (Pydantic's platform) | SaaS, free tier | `logfire.configure()` one-liner | Yes (conversation panels, token tracking, tool inspection) |
| Jaeger | Self-hosted, free | docker-compose, 1 service | No (traces only) |
| SigNoz | Self-hosted or SaaS | docker-compose | Moderate |
| Datadog / New Relic | SaaS, paid | vendor SDK or OTLP | Yes |

### Logfire is built on OpenTelemetry (key insight)

Logfire is NOT a proprietary protocol — it receives data via standard OTLP.
This means:

- `logfire.configure()` → sends to Logfire SaaS (uses global OTel TracerProvider)
- `logfire.configure(send_to_logfire=False)` → uses Logfire SDK convenience
  but exports to YOUR OTLP endpoint (Grafana, Jaeger, etc.) — no data goes to
  Pydantic's servers
- Switching backends = changing the OTLP endpoint, zero code change in
  instrumentation

### Privacy consideration

`include_content=False` in `InstrumentationSettings` excludes prompts,
completions, and tool call arguments/responses from telemetry while preserving
structural information (span names, durations, token counts) for debugging.
Relevant for production with real player data.

## Rule of thumb

| Context | Pattern |
|---------|---------|
| Enable narrator tracing | `agent.instrument_all()` at app startup |
| Privacy mode (no prompt/response data) | `InstrumentationSettings(include_content=False)` |
| Custom OTel provider | `InstrumentationSettings(tracer_provider=my_provider)` |
| Self-hosted backend | Grafana + Tempo + Prometheus via docker-compose |
| SaaS backend (LLM-optimized) | `logfire.configure()` |
| SaaS SDK convenience, self-hosted backend | `logfire.configure(send_to_logfire=False)` + OTLP exporter |
| Switch backends | Change OTLP endpoint only — instrumentation code unchanged |
