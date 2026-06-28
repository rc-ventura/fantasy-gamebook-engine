"""OpenTelemetry setup — traces, metrics, logs via OTLP (T019).

Called from ``app.py`` lifespan.  Safe to call multiple times (idempotent).

Environment variables
---------------------
OTLP_ENDPOINT       — gRPC endpoint for OTLP exporter, e.g. "http://localhost:4317"
                      If unset, uses a no-op exporter (dev/test).
OTEL_SERVICE_NAME   — overrides the service_name argument.

No PII in spans (FR-015):
  - campaign_id and account_id as span attributes (opaque identifiers).
  - No character name, inventory, or narrative text in span attributes.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

logger = logging.getLogger(__name__)

_SETUP_DONE = False
_IN_MEMORY_EXPORTER: InMemorySpanExporter | None = None


def setup_telemetry(
    service_name: str = "gamebook-web",
    otlp_endpoint: str | None = None,
) -> InMemorySpanExporter | None:
    """Configure OpenTelemetry with OTLP exporter.

    Returns the InMemorySpanExporter when no OTLP endpoint is configured
    (useful in tests for asserting spans).

    Parameters
    ----------
    service_name:
        OTel resource service name.
    otlp_endpoint:
        OTLP gRPC endpoint.  Defaults to ``OTLP_ENDPOINT`` env var.
        If neither is set, an in-memory exporter is used (dev/test).
    """
    global _SETUP_DONE, _IN_MEMORY_EXPORTER

    if _SETUP_DONE:
        return _IN_MEMORY_EXPORTER

    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)
    endpoint = otlp_endpoint or os.getenv("OTLP_ENDPOINT", "")

    resource = Resource.create({"service.name": service_name})

    # ---------------------------------------------------------------
    # Traces
    # ---------------------------------------------------------------
    tracer_provider = TracerProvider(resource=resource)

    if endpoint:
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        logger.info("OTel traces → OTLP %s", endpoint)
        _IN_MEMORY_EXPORTER = None
    else:
        in_mem = InMemorySpanExporter()
        tracer_provider.add_span_processor(SimpleSpanProcessor(in_mem))
        logger.info("OTel traces → InMemorySpanExporter (no OTLP_ENDPOINT)")
        _IN_MEMORY_EXPORTER = in_mem

    trace.set_tracer_provider(tracer_provider)

    # ---------------------------------------------------------------
    # Metrics
    # ---------------------------------------------------------------
    if endpoint:
        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10_000)
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    else:
        meter_provider = MeterProvider(resource=resource)

    metrics.set_meter_provider(meter_provider)

    # ---------------------------------------------------------------
    # FastAPI auto-instrumentation
    # ---------------------------------------------------------------
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument()
        logger.info("OTel FastAPI auto-instrumentation enabled")
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
    """Reset telemetry state (for testing only)."""
    global _SETUP_DONE, _IN_MEMORY_EXPORTER
    _SETUP_DONE = False
    _IN_MEMORY_EXPORTER = None
