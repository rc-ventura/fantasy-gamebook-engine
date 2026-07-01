"""FastAPI application — skeleton, error envelope, /health, OpenAPI (T004).

Lifespan:
  1. Setup OpenTelemetry (OTLP if configured, in-memory otherwise).
  2. Install OIDC auth dependency override (unless GAMEBOOK_DEV_MODE=1).
  3. Start the engine MCPToolset (subprocess or in-process via test override).
  4. Instantiate the narrator (PydanticNarrator if ANTHROPIC_API_KEY is set,
     else FakeNarrator as a dev fallback).
  5. Create a fresh CampaignRegistry.
  6. All are stored in ``app.state``; routes read them via ``Request``.

Auth seam (slice 004):
  Routes in play.py/combat.py import ``get_current_account`` from
  ``gamebook_web.auth.dev_auth``.  In production (GAMEBOOK_DEV_MODE != 1)
  the lifespan installs a FastAPI dependency override so all those
  ``Depends(dev_auth.get_current_account)`` transparently route to
  ``oidc_auth.get_current_account`` — no route code changes needed.

Error envelope (CONTRACTS.md §9):
  All HTTP errors use  ``{"error": {"code": "<code>", "message": "<msg>"}}``.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from gamebook_web.api.limiter import limiter
from gamebook_web.mcp_host import engine_toolset_lifespan
from gamebook_web.sessions.campaign import CampaignRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the engine toolset and initialize shared app state."""

    # 1. OpenTelemetry setup (idempotent; no-op if already done by tests)
    _setup_telemetry()

    # 2. Auth dependency override (prod: OIDC; dev/test: keep dev stub)
    _install_auth_override(app)

    # Allow tests to pre-set app.state.engine_toolset (skips subprocess start)
    if getattr(app.state, "engine_toolset", None) is None:
        campaign_id = os.getenv("GAMEBOOK_CAMPAIGN_ID")
        async with engine_toolset_lifespan(campaign_id) as toolset:
            app.state.engine_toolset = toolset
            _init_app_state(app)
            yield
            # Cleanup on shutdown
            app.state.engine_toolset = None
    else:
        # Test path: engine_toolset already injected by fixture
        _init_app_state(app)
        yield


def _setup_telemetry() -> None:
    """Initialize OTel (idempotent; safe to call multiple times)."""
    try:
        from gamebook_web.observability.setup import setup_telemetry
        setup_telemetry()
    except Exception as exc:
        logger.warning("OTel setup failed (non-fatal): %s", exc)


def _install_auth_override(app: FastAPI) -> None:
    """Route dev_auth.get_current_account → oidc_auth.get_current_account in prod."""
    dev_mode = os.getenv("GAMEBOOK_DEV_MODE", "0") in ("1", "true", "True")
    oidc_uri = os.getenv("OIDC_JWKS_URI", "")

    if not dev_mode and oidc_uri:
        # Production: real OIDC
        from gamebook_web.auth.dev_auth import get_current_account as _dev_dep
        from gamebook_web.auth.oidc_auth import get_current_account as _oidc_dep
        app.dependency_overrides[_dev_dep] = _oidc_dep
        logger.info("Auth: OIDC enabled (JWKS=%s)", oidc_uri)
    else:
        logger.info("Auth: dev stub active (GAMEBOOK_DEV_MODE=1 or OIDC_JWKS_URI not set)")


def _init_app_state(app: FastAPI) -> None:
    """Initialize campaign registry and narrator if not already set by tests."""
    if getattr(app.state, "campaign_registry", None) is None:
        app.state.campaign_registry = CampaignRegistry()

    if getattr(app.state, "narrator", None) is None:
        _configure_narrator(app)


def _configure_narrator(app: FastAPI) -> None:
    """Choose narrator implementation based on environment."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("NARRATOR_MODEL", "anthropic:claude-opus-4-8")

    if api_key:
        # Production: use PydanticAI narrator with the active engine toolset
        from gamebook_web.harness.agent import PydanticNarrator
        app.state.narrator = PydanticNarrator(
            model=model,
            toolset=app.state.engine_toolset,
        )
        logger.info("Narrator: PydanticNarrator (model=%s)", model)
    else:
        # Dev / test fallback: FakeNarrator (no LLM required)
        from gamebook_web.harness.base import FakeNarrator
        app.state.narrator = FakeNarrator()
        logger.info("Narrator: FakeNarrator (no ANTHROPIC_API_KEY — dev mode)")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Gamebook Web API",
    version="0.1.0",
    description=(
        "Fantasy gamebook engine web backend — narrator-driven play loop "
        "with engine-authoritative numbers (no narrator-fabricated values)."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# Rate limiting (CWE-770) — protects the expensive /turn (LLM) and combat
# endpoints, plus auth, from abuse / DoS / credit exhaustion.
# ---------------------------------------------------------------------------
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return rate-limit errors in the standard error envelope (CONTRACTS.md §9)."""
    return JSONResponse(
        status_code=429,
        content=_error_body("rate_limited", "Too many requests; please slow down."),
    )


# ---------------------------------------------------------------------------
# CORS — restrictive by default (CWE-942)
# ---------------------------------------------------------------------------
_cors_origins = [
    o.strip()
    for o in os.getenv("GAMEBOOK_CORS_ORIGINS", "").split(",")
    if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ---------------------------------------------------------------------------
# Session-lease guard middleware (T007)
# ---------------------------------------------------------------------------
from gamebook_web.middleware.lease_guard import LeaseGuardMiddleware  # noqa: E402

app.add_middleware(LeaseGuardMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from gamebook_web.api.play import router as play_router        # noqa: E402
from gamebook_web.api.sessions import router as sessions_router  # noqa: E402
from gamebook_web.api.account import router as account_router  # noqa: E402

app.include_router(play_router)
app.include_router(sessions_router)
app.include_router(account_router)


# ---------------------------------------------------------------------------
# Error handlers — consistent envelope (CONTRACTS.md §9)
# ---------------------------------------------------------------------------

def _error_body(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap FastAPI HTTPExceptions in the standard error envelope."""
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        # Already wrapped (raised by our code)
        body = detail
    else:
        body = _error_body("http_error", str(detail))
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from opentelemetry import trace

    from gamebook_web.observability.tracing import span_set_error

    # Annotate the active request span (created by FastAPI auto-instrumentation)
    # so the error correlates with the request trace, rather than creating a
    # detached root span.  get_current_span() returns a no-op span if none is
    # active, so this is always safe.
    span = trace.get_current_span()
    if span is not None and span.is_recording():
        span_set_error(span, exc)
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content=_error_body("internal_error", "An internal server error occurred."),
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Engine health check — returns ``{status: ok, version: ...}``."""
    return {"status": "ok", "version": app.version}
