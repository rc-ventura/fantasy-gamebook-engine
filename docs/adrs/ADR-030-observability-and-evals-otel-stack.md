# ADR-030: Observability and evaluation stack — OpenTelemetry + Pydantic Evals

**Status**: Proposed
**Date**: 2026-07-01
**Related spec**: [004-accounts-hardening-obs](../../specs/004-accounts-hardening-obs/) (FR-014, FR-015)
**Related ADRs**: [ADR-011](./ADR-011-phase2-harness-pydanticai-narrator-backend.md) (PydanticAI narrator), [ADR-029](./ADR-029-narrator-as-tool-use-agent-eliminate-effects.md) (narrator as tool-use agent)
**Related research**: [001-web-platform-migration/research.md](../../specs/001-web-platform-migration/research.md) §7

---

## Context

Spec 004 (accounts-hardening-obs) requires operational telemetry (FR-014:
health, error rate, latency, play metrics) and diagnostic traces (FR-015:
locate a failing turn without exposing internal failure as corrupted state).

The research decision (research.md §7) chose **OpenTelemetry** for
vendor-neutral observability: "OTel is the vendor-neutral standard; exporting
via OTLP avoids lock-in and lets the operator pick a backend."

During implementation research, two discoveries shaped this ADR:

1. **Pydantic AI has built-in OTel instrumentation** — `Agent.instrument_all()`
   emits spans for LLM calls and tool calls automatically, using the global
   OTel `TracerProvider`. No manual span code needed in the narrator harness.

2. **Pydantic Evals** (`pydantic-evals`, MIT) is an open-source evaluation
   framework that uses OTel natively — eval traces go to the same backend as
   production traces. Supports span-based evaluation (assert on tool-call
   behavior, not just output text).

These discoveries mean the observability and evaluation concerns share a
single telemetry pipeline, with the narrator harness (ADR-011) providing
spans for free.

## Decision

### 1. OpenTelemetry as the observability standard

Instrument the backend with OpenTelemetry (traces, metrics, logs) exported via
OTLP. This follows the research decision (§7) and is not changed by this ADR.

**Implementation**:
- `src/gamebook_web/observability/` module configures the OTel `TracerProvider`,
  `MeterProvider`, and OTLP exporter at app startup
- `opentelemetry-instrumentation-fastapi` auto-instruments HTTP routes
- `Agent.instrument_all()` on the Pydantic AI narrator provides LLM + tool
  call spans automatically (no manual instrumentation in `harness/agent.py`)
- Custom spans for non-FastAPI, non-narrator operations (session lease check,
  terminal state check, scene persistence)

### 2. Backend: operator-chosen, default to self-hosted Grafana stack

The OTLP exporter endpoint is configuration-driven. The default
`docker-compose.yml` includes:

- **OTel Collector** — receives OTLP, redistributes
- **Tempo** — trace storage
- **Prometheus** — metric storage
- **Loki** — log storage
- **Grafana** — dashboard (datasources: Tempo + Prometheus + Loki)

**Logfire compatibility**: Logfire is built on OpenTelemetry and receives data
via standard OTLP. Operators can point the OTLP exporter at Logfire instead of
the self-hosted stack by changing one configuration value. The Logfire SDK
(`logfire.configure(send_to_logfire=False)`) can also be used for convenience
while exporting to a self-hosted backend. No code change required to switch.

### 3. Pydantic Evals for narrator evaluation

Use `pydantic-evals` (MIT) for systematic evaluation of narrator quality.

**Why Pydantic Evals over alternatives**:
- Same OTel pipeline — eval traces and production traces go to the same
  backend, enabling direct comparison
- Span-Based Evaluation — can assert on narrator tool-call behavior (did the
  narrator call `set_character` after combat? did it call `add_event`?), not
  just output text. Critical because ADR-029 moved state changes inside the
  narrator's tool calls
- Code-first — datasets in Python, versioned in git (Principle IV alignment)
- No Logfire dependency — works with any OTel backend
- Integrates with Pydantic AI agent structure (ADR-011)

**Rejected alternatives**:
- **DeepEval** (Apache 2.0) — no native OTel integration; would require a
  separate pipeline
- **Bespoke eval scripts** — more maintenance, no span-based evaluation, no
  regression tracking
- **Logfire's eval UI only** — vendor lock-in for viewing; Pydantic Evals is
  open-source and backend-agnostic

### 4. Privacy: `include_content=False` for production telemetry

`InstrumentationSettings(include_content=False)` excludes prompts, completions,
and tool call arguments/responses from telemetry spans while preserving
structural information (span names, durations, token counts). This prevents
player narrative content from appearing in the observability backend.

Eval runs may use `include_content=True` since they use synthetic test data,
not real player content.

## Consequences

### Positive

- **Narrator traces for free**: `Agent.instrument_all()` provides LLM and tool
  call spans with zero manual instrumentation in the harness
- **Unified pipeline**: production observability and eval evaluation share one
  OTel backend — one Grafana dashboard shows both
- **Vendor-neutral**: OTLP export to any backend (Grafana, Logfire, Jaeger,
  Datadog, etc.) — switching is a config change, not a code change
- **Span-based evals**: can assert narrator called correct MCP tools, not just
  that the output text looks good — essential post-ADR-029 where state changes
  happen inside narrator tool calls
- **Privacy by default**: production traces exclude player content

### Negative / trade-offs

- **docker-compose complexity**: self-hosted stack adds 5 services (collector,
  Tempo, Prometheus, Loki, Grafana). Mitigated by making the OTLP endpoint
  configurable — operators can use Logfire SaaS instead
- **`pydantic-evals` dependency**: MIT, minimal, but adds a package
- **Eval datasets require maintenance**: test cases must be kept current as
  the narrator system prompt and adventure content evolve

### Conditions that invalidate this decision

1. OTel instrumentation overhead proves significant at scale (> 5% latency on
   the turn path) — would need sampling configuration
2. `pydantic-evals` API diverges enough that eval datasets become brittle
3. A future phase requires real-time online evals (production traffic scoring)
   that Pydantic Evals does not support adequately

## References

- [Research §7 — Observability](../../specs/001-web-platform-migration/research.md)
- [Spec 004 — FR-014, FR-015](../../specs/004-accounts-hardening-obs/spec.md)
- [ADR-011 — PydanticAI narrator harness](./ADR-011-phase2-harness-pydanticai-narrator-backend.md)
- [ADR-029 — Narrator as tool-use agent](./ADR-029-narrator-as-tool-use-agent-eliminate-effects.md)
- [Learning lesson: Pydantic AI built-in OTel instrumentation](../learning-lessons/pydantic_ai_builtin_opentelemetry_instrumentation.md)
- [Learning lesson: Pydantic Evals open-source OTel-native](../learning-lessons/pydantic_evals_open_source_otel_native.md)
- Pydantic AI docs: `Agent.instrument_all()`, `InstrumentationSettings`
- Pydantic Evals docs: https://ai.pydantic.dev/evals
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
