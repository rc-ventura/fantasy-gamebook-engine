"""GenAI telemetry privacy (issue #22, ADR-030 §4).

``setup_telemetry`` must instrument pydantic-ai agents with
``InstrumentationSettings(include_content=False)`` so prompts, completions,
and tool arguments — player narrative plus the full narrator system prompt —
never land in span attributes.  Dev/eval runs may opt in via
``OTEL_GENAI_INCLUDE_CONTENT=1``; production refuses the override (same
posture as the ``OTLP_INSECURE`` guard).

``Agent.instrument_all(settings)`` stores the settings as the class-level
``Agent._instrument_default``, which is what these tests assert on.
"""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.instrumented import InstrumentationSettings

from gamebook_web.observability.setup import reset_telemetry, setup_telemetry


@pytest.fixture(autouse=True)
def clean_telemetry(monkeypatch):
    """Fresh telemetry state and a content-safe env for every test."""
    monkeypatch.delenv("OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_GENAI_INCLUDE_CONTENT", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    reset_telemetry()
    yield
    reset_telemetry()


def test_setup_instruments_agents_with_content_excluded():
    setup_telemetry()

    settings = Agent._instrument_default
    assert isinstance(settings, InstrumentationSettings)
    assert settings.include_content is False


def test_env_var_opts_into_content_outside_production(monkeypatch):
    monkeypatch.setenv("OTEL_GENAI_INCLUDE_CONTENT", "1")

    setup_telemetry()

    settings = Agent._instrument_default
    assert isinstance(settings, InstrumentationSettings)
    assert settings.include_content is True


def test_production_refuses_content_export(monkeypatch):
    monkeypatch.setenv("OTEL_GENAI_INCLUDE_CONTENT", "1")
    monkeypatch.setenv("ENV", "production")

    with pytest.raises(RuntimeError, match="OTEL_GENAI_INCLUDE_CONTENT"):
        setup_telemetry()


def test_reset_turns_instrumentation_back_off():
    setup_telemetry()
    reset_telemetry()

    assert Agent._instrument_default is False
