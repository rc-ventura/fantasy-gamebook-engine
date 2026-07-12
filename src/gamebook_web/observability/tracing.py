
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
    """Mark span as ERROR recording ONLY the exception class name (FR-031).

    Deliberately does NOT call ``span.record_exception(exc)``: that captures
    ``exception.message`` and ``exception.stacktrace`` as span-event attributes,
    which can echo player input (PII) or internal paths (traceback).  We record
    the type name via ``set_status`` description and a single attribute instead.
    """
    type_name = type(exc).__name__
    span.set_status(StatusCode.ERROR, description=type_name)
    span.set_attribute("exception.type", type_name)


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


@contextmanager
def classify_intent_span(
    campaign_id: str,
    location: str,
    num_candidates: int,
) -> Generator[Span, None, None]:
    """Span for ClassifyIntent node — records routing decision."""
    tracer = get_tracer()
    with tracer.start_as_current_span("gamebook.dispatch.classify") as span:
        span.set_attribute("campaign_id", campaign_id)
        span.set_attribute("location", location)
        span.set_attribute("num_candidates", num_candidates)
        try:
            yield span
        except Exception as exc:
            span_set_error(span, exc)
            raise


@contextmanager
def mechanical_dispatch_span(
    campaign_id: str,
    action: str,
    template: str,
) -> Generator[Span, None, None]:
    """Span for MechanicalDispatch node — records template execution."""
    tracer = get_tracer()
    with tracer.start_as_current_span("gamebook.dispatch.mechanical") as span:
        span.set_attribute("campaign_id", campaign_id)
        span.set_attribute("action", action)
        span.set_attribute("template", template)
        try:
            yield span
        except Exception as exc:
            span_set_error(span, exc)
            raise


@contextmanager
def combat_round_span(
    campaign_id: str,
    combat_id: str,
    round_n: int,
) -> Generator[Span, None, None]:
    """Span for one CombatRound cycle."""
    tracer = get_tracer()
    with tracer.start_as_current_span("gamebook.dispatch.combat_round") as span:
        span.set_attribute("campaign_id", campaign_id)
        span.set_attribute("combat_id", combat_id)
        span.set_attribute("round_n", round_n)
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


def reset_metrics() -> None:
    """Drop the metrics singleton so instruments rebind to the current
    MeterProvider (tests install an in-memory reader before asserting)."""
    global _METRICS
    _METRICS = None
