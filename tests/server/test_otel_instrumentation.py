"""OTel instrumentation tests (T054, SC-012, ADR-024).

Verifies the observability wiring added in spec-006 US7:
  * ``turn_span`` / ``narrator_span`` set only opaque attributes (no PII).
  * ``span_set_error`` records ONLY the exception type — no message, no
    stacktrace event (FR-031).
  * The HTTP metrics middleware increments ``http_requests_total`` per request.
  * ``setup_telemetry(app=...)`` instruments that specific app via
    ``FastAPIInstrumentor.instrument_app`` (T045), not the global instrumentor.

Span assertions use a locally-constructed TracerProvider (via monkeypatching
``tracing.get_tracer``) so they do not depend on the process-global provider,
which OpenTelemetry only lets you set once.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from gamebook_web.observability import tracing


@pytest.fixture
def local_tracer(monkeypatch):
    """A tracer whose spans land in an InMemorySpanExporter."""
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(tracing, "get_tracer", lambda: tracer)
    return exporter


# ---------------------------------------------------------------------------
# Spans — attributes and PII
# ---------------------------------------------------------------------------

def test_turn_span_sets_only_opaque_attributes(local_tracer):
    with tracing.turn_span("camp-1", "acct-1", turn_number=3):
        pass

    spans = local_tracer.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes)
    assert attrs["campaign_id"] == "camp-1"
    assert attrs["account_id"] == "acct-1"
    assert attrs["turn_number"] == 3
    # No PII-bearing attribute keys.
    forbidden = {"name", "narrative", "sub", "email", "inventory", "choice"}
    assert not (forbidden & set(attrs)), attrs


def test_narrator_span_sets_campaign_id_only(local_tracer):
    with tracing.narrator_span("camp-9"):
        pass

    span = local_tracer.get_finished_spans()[0]
    assert dict(span.attributes) == {"campaign_id": "camp-9"}


def test_span_set_error_records_type_only_no_message_or_traceback(local_tracer):
    tracer = tracing.get_tracer()
    with tracer.start_as_current_span("op") as span:
        tracing.span_set_error(span, ValueError("SECRET PLAYER INPUT rm -rf /"))

    finished = local_tracer.get_finished_spans()[0]
    assert finished.status.status_code == StatusCode.ERROR
    assert finished.attributes.get("exception.type") == "ValueError"
    # No exception event (record_exception would add message + stacktrace).
    assert not finished.events
    # The secret message must not appear anywhere in the span.
    blob = repr(finished.attributes) + repr(finished.status.description)
    assert "SECRET PLAYER INPUT" not in blob


# ---------------------------------------------------------------------------
# Metrics — http_requests_total
# ---------------------------------------------------------------------------

class _FakeCounter:
    def __init__(self) -> None:
        self.total = 0
        self.last_attrs: dict | None = None

    def add(self, amount, attributes=None) -> None:
        self.total += amount
        self.last_attrs = attributes


class _FakeMetrics:
    def __init__(self) -> None:
        self.http_requests_total = _FakeCounter()
        self.combat_rounds_total = _FakeCounter()
        self.active_campaigns = _FakeCounter()

        class _Hist:
            def record(self, *a, **k):
                pass

        self.turn_duration = _Hist()


def test_http_requests_total_incremented(api_client, monkeypatch):
    fake = _FakeMetrics()
    monkeypatch.setattr(tracing, "get_metrics", lambda: fake)

    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert fake.http_requests_total.total >= 1
    assert fake.http_requests_total.last_attrs is not None
    # Attributes are opaque: method/path/status only.
    assert set(fake.http_requests_total.last_attrs) <= {"method", "path", "status"}


# ---------------------------------------------------------------------------
# instrument_app (T045)
# ---------------------------------------------------------------------------

def test_setup_telemetry_uses_instrument_app(monkeypatch):
    from fastapi import FastAPI
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    from gamebook_web.observability.setup import reset_telemetry, setup_telemetry

    calls: list = []
    monkeypatch.setattr(
        FastAPIInstrumentor, "instrument_app", staticmethod(lambda app, **k: calls.append(app))
    )

    reset_telemetry()
    try:
        fake_app = FastAPI()
        setup_telemetry(app=fake_app)
        assert fake_app in calls
    finally:
        reset_telemetry()
