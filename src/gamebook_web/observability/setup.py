from __future__ import annotations

import logging
import os
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

logger = logging.getLogger(__name__)

_SETUP_DONE = False
_IN_MEMORY_EXPORTER: InMemorySpanExporter | None = None
_TRACER_PROVIDER: TracerProvider | None = None
_METER_PROVIDER: MeterProvider | None = None
_INSTRUMENTED_APP: Any | None = None


def setup_telemetry(
    service_name: str = "gamebook-web",
    otlp_endpoint: str | None = None,
    app: Any | None = None,
) -> InMemorySpanExporter | None:
    """Configure OpenTelemetry with OTLP exporter.

    Returns the InMemorySpanExporter when no OTLP endpoint is configured
    (useful in tests for asserting spans).

    Parameters
    ----------
    service_name:
        OTel resource service name.
    otlp_endpoint:
        OTLP HTTP endpoint (e.g. "http://localhost:4318"). Defaults to
        ``OTLP_ENDPOINT`` env var. If neither is set, an in-memory exporter
        is used (dev/test).
    app:
        The FastAPI app to instrument (T045).  When provided, only this app is
        instrumented via ``FastAPIInstrumentor.instrument_app(app)`` rather than
        globally patching every FastAPI app in the process.
    """
    global _SETUP_DONE, _IN_MEMORY_EXPORTER, _TRACER_PROVIDER, _METER_PROVIDER
    global _INSTRUMENTED_APP

    if _SETUP_DONE:
        return _IN_MEMORY_EXPORTER

    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)
    endpoint = otlp_endpoint or os.getenv("OTLP_ENDPOINT", "")

    # TLS by default (T051/FR-032): the http-exporter migration
    if endpoint and os.getenv("ENV", "").lower() == "production" and not endpoint.startswith("https://"):
        raise RuntimeError(
            f"OTLP_ENDPOINT={endpoint!r} is not TLS-secured (https://) and "
            "ENV=production. Use a TLS-secured OTLP collector endpoint."
        )

    resource = Resource.create({"service.name": service_name})

    # ---------------------------------------------------------------
    # Traces
    # ---------------------------------------------------------------
    tracer_provider = TracerProvider(resource=resource)

    if endpoint:
        traces_url = endpoint.rstrip("/") + "/v1/traces"
        span_exporter = OTLPSpanExporter(endpoint=traces_url)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        logger.info("OTel traces → %s", traces_url)
        _IN_MEMORY_EXPORTER = None
    else:
        in_mem = InMemorySpanExporter()
        tracer_provider.add_span_processor(SimpleSpanProcessor(in_mem))
        logger.info("OTel traces → InMemorySpanExporter (no OTLP_ENDPOINT)")
        _IN_MEMORY_EXPORTER = in_mem

    trace.set_tracer_provider(tracer_provider)
    _TRACER_PROVIDER = tracer_provider

    # ---------------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------------
    if endpoint:
        metrics_url = endpoint.rstrip("/") + "/v1/metrics"
        metric_exporter = OTLPMetricExporter(endpoint=metrics_url)
        reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10_000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    else:
        meter_provider = MeterProvider(resource=resource)

    metrics.set_meter_provider(meter_provider)
    _METER_PROVIDER = meter_provider

    # ---------------------------------------------------------------
    # pydantic-ai GenAI instrumentation (ADR-030 §4 — privacy)
    #
    # Emits GenAI semantic-convention spans + the gen_ai token-usage metric
    # for every Agent.run() via plain OpenTelemetry (no Logfire SDK).
    # include_content=False keeps prompts/completions/tool args OUT of span
    # attributes — player narrative and the narrator system prompt must never
    # reach the OTel pipeline (issue #22).  Dev/eval runs can opt in with
    # OTEL_GENAI_INCLUDE_CONTENT=1; production refuses the override, same as
    # the OTLP_INSECURE guard above.
    # ---------------------------------------------------------------
    include_content = os.getenv("OTEL_GENAI_INCLUDE_CONTENT", "0") in ("1", "true", "True")
    if include_content and os.getenv("ENV", "").lower() == "production":
        raise RuntimeError(
            "OTEL_GENAI_INCLUDE_CONTENT=1 is not allowed in production "
            "(ENV=production). Prompts/completions must not be exported in "
            "span content (ADR-030 §4)."
        )
    try:
        from pydantic_ai import Agent as _PydanticAgent
        from pydantic_ai.models.instrumented import InstrumentationSettings

        _PydanticAgent.instrument_all(
            InstrumentationSettings(include_content=include_content)
        )
        logger.info(
            "pydantic-ai GenAI instrumentation enabled (include_content=%s)",
            include_content,
        )
    except ImportError:
        logger.warning("pydantic-ai not installed — skipping GenAI instrumentation")

    # ---------------------------------------------------------------
    # FastAPI auto-instrumentation
    # ---------------------------------------------------------------
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        if app is not None:
            # T045: instrument only this app, not every FastAPI app in the process.
            FastAPIInstrumentor.instrument_app(app)
            _INSTRUMENTED_APP = app
        else:
            FastAPIInstrumentor().instrument()
        logger.info("OTel FastAPI auto-instrumentation enabled (app-scoped=%s)", app is not None)
    except ImportError:
        logger.warning("opentelemetry-instrumentation-fastapi not installed — skipping")

    # ---------------------------------------------------------------
    # httpx auto-instrumentation (for JWKS fetches)
    # ---------------------------------------------------------------
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.info("OTel httpx auto-instrumentation enabled")
    except ImportError:
        logger.warning("opentelemetry-instrumentation-httpx not installed — skipping")

    _SETUP_DONE = True
    return _IN_MEMORY_EXPORTER


def reset_telemetry() -> None:
    """Reset telemetry state (for testing only).

    Shuts down the tracer/meter providers created by ``setup_telemetry`` and
    uninstruments FastAPI/httpx so a subsequent ``setup_telemetry`` starts from
    a clean slate.  Without this, repeated setup/reset cycles in tests leave the
    old instrumentors active and orphan the previous InMemorySpanExporter,
    producing unreliable span assertions (test pollution).
    """
    global _SETUP_DONE, _IN_MEMORY_EXPORTER, _TRACER_PROVIDER, _METER_PROVIDER
    global _INSTRUMENTED_APP

    # Turn pydantic-ai GenAI instrumentation back off so a later
    # setup_telemetry starts from a clean slate (mirrors the FastAPI/httpx
    # uninstrument below) rather than layering onto stale providers.
    try:
        from pydantic_ai import Agent as _PydanticAgent

        _PydanticAgent.instrument_all(False)
    except Exception:  # pragma: no cover — best-effort cleanup
        pass

    # Flush and close the providers we created.
    if _TRACER_PROVIDER is not None:
        try:
            _TRACER_PROVIDER.shutdown()
        except Exception:  # pragma: no cover — best-effort cleanup
            pass
    if _METER_PROVIDER is not None:
        try:
            _METER_PROVIDER.shutdown()
        except Exception:  # pragma: no cover — best-effort cleanup
            pass

    # Uninstrument so a later setup can re-instrument without double-wrapping.
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if _INSTRUMENTED_APP is not None:
            FastAPIInstrumentor.uninstrument_app(_INSTRUMENTED_APP)
        else:
            FastAPIInstrumentor().uninstrument()
    except Exception:  # pragma: no cover — not installed / not instrumented
        pass
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().uninstrument()
    except Exception:  # pragma: no cover — not installed / not instrumented
        pass

    _SETUP_DONE = False
    _IN_MEMORY_EXPORTER = None
    _TRACER_PROVIDER = None
    _METER_PROVIDER = None
    _INSTRUMENTED_APP = None
