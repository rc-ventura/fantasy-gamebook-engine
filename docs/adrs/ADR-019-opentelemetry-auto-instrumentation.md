# ADR-019: OpenTelemetry auto-instrumentation + no-PII-in-spans rule

**Status**: Accepted | **Date**: 2026-06-28 | **Branch**: `feat/004-auth-obs`

## Context

Slice 004 adds operational observability so operators can see health, error rate, latency, and basic play metrics, and trace failing requests without exposing internal state to players.

Key constraints:
1. No PII in span attributes (characters, narrative text, player names, inventory are PII).
2. Operators must be able to locate a failing turn from traces alone.
3. A failing narrator must not leak a raw Python traceback to the player.
4. Vendor-neutral (OTLP) — operators choose their own backend.

## Decision

### OTel SDK setup (`observability/setup.py`)

- `setup_telemetry(service_name, otlp_endpoint)` is called once from the FastAPI lifespan.
- Idempotent (safe for tests that reset and call multiple times).
- When `OTLP_ENDPOINT` is set: OTLP gRPC exporter + `BatchSpanProcessor` + `PeriodicExportingMetricReader`.
- When unset: `InMemorySpanExporter` (returned to tests for span assertions).

### FastAPI auto-instrumentation

`FastAPIInstrumentor().instrument()` adds a span for every HTTP request (method, path, status). No configuration needed — wraps the existing routing layer.

`HTTPXClientInstrumentor().instrument()` adds spans for JWKS fetch requests, making slow or failing OIDC calls visible in traces.

### Turn-level tracing (`observability/tracing.py`)

A `turn_span` context manager adds a child span for `/turn` with:
- `campaign_id` (opaque UUID — not PII)
- `account_id` (opaque UUID — not PII)
- `turn_number` (optional counter — not PII)

Forbidden attributes: character name, inventory items, narrative text, world flags, OIDC `sub`.

A `narrator_span` context manager wraps the LLM call inside a child span so slow AI responses are visible in traces separately from the DB/engine time.

### Error handling

`span_set_error(span, exc)` sets the span status to `ERROR` with only `type(exc).__name__` (no message, no traceback — prevents internal details reaching telemetry consumers with broad access). The API response handler returns `{"error": {"code": "internal_error", "message": "An error occurred"}}` — never the raw exception.

### Metrics

Pre-built instruments in `GamebookMetrics`:
- `http_requests_total` (counter, labels: method/path/status)
- `turn_duration_seconds` (histogram)
- `active_campaigns` (up/down counter)
- `combat_rounds_total` (counter)

### No PII rule enforcement

The rule is architectural: span attributes are set only via the `turn_span` / `narrator_span` helpers, which explicitly allow only opaque IDs. All other observability code records only exception class names, not messages.

## Consequences

**Positive**:
- Zero-code tracing of every HTTP request via auto-instrumentation.
- Failing turns surface in traces with campaign context, without leaking game state.
- `InMemorySpanExporter` enables span assertions in tests without an OTLP collector.
- OTLP is vendor-neutral; operators can use Jaeger, Tempo, Honeycomb, etc.

**Negative**:
- Auto-instrumentation adds a small overhead per request (~1 ms).
- `opentelemetry-instrumentation-fastapi` version must stay compatible with FastAPI's middleware version.

## Related

- T019 (OTel setup), T020 (per-request traces), T021 (observability tests)
- FR-014 (operational telemetry), FR-015 (diagnostic traces without PII)
