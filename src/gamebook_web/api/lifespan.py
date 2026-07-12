
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from gamebook_web.mcp_host import engine_toolset_lifespan
from gamebook_web.sessions.campaign import CampaignRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the engine toolset and initialize shared app state."""

    _check_production_dev_mode_clash()
    _setup_telemetry(app)
    _install_auth_override(app)

    if getattr(app.state, "engine_toolset", None) is None:
        async with engine_toolset_lifespan() as toolset:
            app.state.engine_toolset = toolset
            _init_app_state(app)
            yield
            app.state.engine_toolset = None
    else:
        _init_app_state(app)
        yield


def _check_production_dev_mode_clash() -> None:
    """Raise RuntimeError if ENV=production and GAMEBOOK_DEV_MODE=1.

    Guards against accidental deployment of a dev-only auth bypass
    in a production environment (FR-008).
    """
    env = os.getenv("ENV", "")
    dev_mode = os.getenv("GAMEBOOK_DEV_MODE", "0")
    if env.lower() == "production" and dev_mode in ("1", "true", "True"):
        raise RuntimeError(
            "Refusing to start: ENV=production but GAMEBOOK_DEV_MODE is enabled. "
            "Unset GAMEBOOK_DEV_MODE before deploying to production."
        )


def _setup_telemetry(app: FastAPI) -> None:
    """Initialize OTel (idempotent; safe to call multiple times)."""
    try:
        from gamebook_web.observability.setup import setup_telemetry
        setup_telemetry(app=app)
    except Exception as exc:
        logger.warning("OTel setup failed (non-fatal): %s", exc)


def _install_auth_override(app: FastAPI) -> None:
    """Wire the auth dependency, failing closed (T030, ADR-022, FR-018).

    Three cases:
      - ``GAMEBOOK_DEV_MODE`` enabled → keep the dev stub (local dev / tests).
      - OIDC configured (``OIDC_JWKS_URI`` set) → override to real OIDC.
      - Neither → refuse to start.
    """
    dev_mode = os.getenv("GAMEBOOK_DEV_MODE", "0") in ("1", "true", "True")
    oidc_uri = os.getenv("OIDC_JWKS_URI", "")

    if dev_mode:
        logger.info("Auth: dev stub active (GAMEBOOK_DEV_MODE enabled)")
        return

    if not oidc_uri:
        raise RuntimeError(
            "Refusing to start: no authentication configured. "
            "Set OIDC_JWKS_URI to enable production OIDC, or GAMEBOOK_DEV_MODE=1 "
            "for local development."
        )

    if not os.getenv("OIDC_ISSUER", ""):
        raise RuntimeError(
            "Refusing to start: OIDC is enabled but OIDC_ISSUER is not set. "
            "Configure the expected token issuer (iss)."
        )

    from gamebook_web.auth.dev_auth import get_current_account as _dev_dep
    from gamebook_web.auth.oidc_auth import get_current_account as _oidc_dep
    app.dependency_overrides[_dev_dep] = _oidc_dep
    logger.info("Auth: OIDC enabled (JWKS=%s)", oidc_uri)


def _init_app_state(app: FastAPI) -> None:
    """Initialize campaign registry and narrator if not already set by tests."""
    if getattr(app.state, "campaign_registry", None) is None:
        app.state.campaign_registry = CampaignRegistry()

    if getattr(app.state, "narrator", None) is None:
        _configure_narrator(app)


_PROVIDER_KEY_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _resolve_api_key(model: str) -> str | None:
    """Return the API key for ``model``'s provider prefix, or None if unset/unknown."""
    provider = model.split(":", 1)[0]
    env_var = _PROVIDER_KEY_MAP.get(provider)
    return os.getenv(env_var) if env_var else None


def _configure_narrator(app: FastAPI) -> None:
    """Choose narrator implementation based on environment."""
    model = os.getenv("NARRATOR_MODEL", "anthropic:claude-opus-4-8")
    api_key = _resolve_api_key(model)

    if api_key:
        from gamebook_web.harness.graph import DispatcherNarrator
        adventure_dir = os.getenv("GAMEBOOK_ADVENTURE_DIR", "adventure_modules/ignarok")
        templates_path = os.getenv("GAMEBOOK_TEMPLATES_PATH", "adventure_modules/templates.yaml")
        app.state.narrator = DispatcherNarrator(
            model=model,
            toolset=app.state.engine_toolset,
            adventure_dir=Path(adventure_dir),
            templates_path=Path(templates_path),
        )
        logger.info(
            "Narrator: DispatcherNarrator (model=%s, adventure=%s)",
            model,
            adventure_dir,
        )
    else:
        from gamebook_web.harness.narrator import FakeNarrator
        app.state.narrator = FakeNarrator()
        logger.info(
            "Narrator: FakeNarrator (no API key configured for model=%s — dev mode)",
            model,
        )
