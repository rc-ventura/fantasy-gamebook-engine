"""Test: provider-aware narrator activation gate (issue #9, updated spec 009).

``_configure_narrator`` must activate ``DispatcherNarrator`` for any provider
prefix in ``NARRATOR_MODEL`` (anthropic/openai/openrouter) as long as that
provider's API key env var is set, and fall back to ``FakeNarrator``
otherwise — never hardcode the gate to ``ANTHROPIC_API_KEY``.

spec 009 (ADR-033): the narrator was upgraded from ``PydanticNarrator`` (free
tool-use loop) to ``DispatcherNarrator`` (deterministic dispatcher graph).
The activation gate logic (key present → real narrator, key absent → fake)
is unchanged; only the concrete class name is different.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from gamebook_web.api.app import _configure_narrator, _resolve_api_key


@pytest.fixture
def clean_narrator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear every provider key + NARRATOR_MODEL so tests start from a blank slate."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "NARRATOR_MODEL"):
        monkeypatch.delenv(var, raising=False)


def _stub_app() -> Any:
    """Minimal app-like object: only ``state.engine_toolset`` is read."""
    return SimpleNamespace(state=SimpleNamespace(engine_toolset=None))


# ---------------------------------------------------------------------------
# _resolve_api_key
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("clean_narrator_env")
def test_resolve_api_key_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert _resolve_api_key("anthropic:claude-opus-4-8") == "sk-ant-test"


@pytest.mark.usefixtures("clean_narrator_env")
def test_resolve_api_key_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    assert _resolve_api_key("openai:gpt-4o") == "sk-oai-test"


@pytest.mark.usefixtures("clean_narrator_env")
def test_resolve_api_key_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert _resolve_api_key("openrouter:anthropic/claude-opus-4-8") == "sk-or-test"


@pytest.mark.usefixtures("clean_narrator_env")
def test_resolve_api_key_missing_key_returns_none() -> None:
    assert _resolve_api_key("openai:gpt-4o") is None


@pytest.mark.usefixtures("clean_narrator_env")
def test_resolve_api_key_unknown_provider_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    assert _resolve_api_key("unknown-provider:some-model") is None


# ---------------------------------------------------------------------------
# _configure_narrator activation gate
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("clean_narrator_env")
def test_configure_narrator_no_keys_falls_back_to_fake() -> None:
    from gamebook_web.harness.narrator import FakeNarrator

    app = _stub_app()
    _configure_narrator(app)
    assert isinstance(app.state.narrator, FakeNarrator)


@pytest.mark.usefixtures("clean_narrator_env")
def test_configure_narrator_anthropic_key_activates_dispatcher_narrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gamebook_web.harness.graph import DispatcherNarrator

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    app = _stub_app()
    _configure_narrator(app)
    assert isinstance(app.state.narrator, DispatcherNarrator)


@pytest.mark.usefixtures("clean_narrator_env")
def test_configure_narrator_openai_model_requires_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setting NARRATOR_MODEL=openai:... with only ANTHROPIC_API_KEY set must NOT activate
    (regression guard for the bug this issue fixes: the old gate ignored the model prefix)."""
    from gamebook_web.harness.narrator import FakeNarrator

    monkeypatch.setenv("NARRATOR_MODEL", "openai:gpt-4o")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    app = _stub_app()
    _configure_narrator(app)
    assert isinstance(app.state.narrator, FakeNarrator)


@pytest.mark.usefixtures("clean_narrator_env")
def test_configure_narrator_openai_key_activates_dispatcher_narrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gamebook_web.harness.graph import DispatcherNarrator

    monkeypatch.setenv("NARRATOR_MODEL", "openai:gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
    app = _stub_app()
    _configure_narrator(app)
    assert isinstance(app.state.narrator, DispatcherNarrator)


@pytest.mark.usefixtures("clean_narrator_env")
def test_configure_narrator_openrouter_key_activates_dispatcher_narrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gamebook_web.harness.graph import DispatcherNarrator

    monkeypatch.setenv("NARRATOR_MODEL", "openrouter:anthropic/claude-opus-4-8")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    app = _stub_app()
    _configure_narrator(app)
    assert isinstance(app.state.narrator, DispatcherNarrator)
