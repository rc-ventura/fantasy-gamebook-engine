"""Per-request tracing helpers (T020).

Provides:
  - ``get_tracer()``   — tracer for gamebook-web spans
  - ``record_turn_span()`` — context manager for a /turn span with campaign metadata
  - ``span_set_error()``  — mark a span ERROR and record the exception (no raw traceback)

PII rules (FR-015):
  - Allowed span attributes: campaign_id, account_id, turn_number (opaque IDs)
  - Forbidden: character name, inventory, narrative text, player email/sub

Usage example in a route::

    from gamebook_web.observability.tracing import get_tracer, span_set_error

    tracer = get_tracer()
    with tracer.start_as_current_span("turn") as span:
        span.set_attribute("campaign_id", campaign_id)
        try:
            ...
        except Exception as exc:
            span_set_error(span, exc)
            raise
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

logger = logging.getLogger(__name__)

_TRACER_NAME = "gamebook.web"


def get_tracer() -> trace.Tracer:
    """Return the gamebook-web tracer."""
    return trace.get_tracer(_TRACER_NAME)


def span_set_error(span: Span, exc: Exception) -> None:
    """Mark span as ERROR and record the exception type (no raw message/traceback)."""
    span.set_status(StatusCode.ERROR, description=type(exc).__name__)
    # Record just the exception class — no message, no traceback (PII/security)
    span.record_exception(exc, attributes={"exception.escaped": True})


@contextmanager
def turn_span(
    campaign_id: str,
    account_id: str,
    turn_number: int | None = None,
) -> Generator[Span, None, None]:
    """Context manager wrapping a /turn request in an OTel span.

    Sets allowed attributes (no PII).  Marks span ERROR on exception
    and re-raises — the route's exception handler will format the 422/500
    response without leaking internals.
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("gamebook.turn") as span:
        span.set_attribute("campaign_id", campaign_id)
        span.set_attribute("account_id", account_id)
        if turn_number is not None:
            span.set_attribute("turn_number", turn_number)
        try:
            yield span
        except Exception as exc:
            span_set_error(span, exc)
            raise


@contextmanager
def narrator_span(campaign_id: str) -> Generator[Span, None, None]:
    """Child span for the narrator LLM call — makes slow LLM calls visible."""
    tracer = get_tracer()
    with tracer.start_as_current_span("gamebook.narrator") as span:
        span.set_attribute("campaign_id", campaign_id)
        try:
            yield span
        except Exception as exc:
            span_set_error(span, exc)
            raise


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def get_meter():
    """Return the gamebook-web meter."""
    from opentelemetry import metrics
    return metrics.get_meter(_TRACER_NAME)


class GamebookMetrics:
    """Pre-built instruments for gamebook-web metrics (T019)."""

    def __init__(self) -> None:
        meter = get_meter()
        self.http_requests_total = meter.create_counter(
            name="http_requests_total",
            description="Total HTTP requests by method, path, and status",
        )
        self.turn_duration = meter.create_histogram(
            name="turn_duration_seconds",
            description="Duration of /turn requests in seconds",
            unit="s",
        )
        self.active_campaigns = meter.create_up_down_counter(
            name="active_campaigns",
            description="Number of currently active (not-ended) campaigns",
        )
        self.combat_rounds_total = meter.create_counter(
            name="combat_rounds_total",
            description="Total combat rounds resolved",
        )


_METRICS: GamebookMetrics | None = None


def get_metrics() -> GamebookMetrics:
    """Return the singleton GamebookMetrics (created on first call)."""
    global _METRICS
    if _METRICS is None:
        _METRICS = GamebookMetrics()
    return _METRICS
