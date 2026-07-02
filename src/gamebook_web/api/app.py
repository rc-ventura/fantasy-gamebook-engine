"""FastAPI application — skeleton, error envelope, /health, OpenAPI (T004).

Lifespan:
  1. Start the engine MCPToolset (subprocess or in-process via test override).
  2. Instantiate the narrator (PydanticNarrator if ANTHROPIC_API_KEY is set,
     else FakeNarrator as a dev fallback).
  3. Create a fresh CampaignRegistry.
  4. All three are stored in ``app.state``; routes read them via ``Request``.

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

    # Production safety guard (FR-008): refuse to start if dev mode is
    # explicitly enabled in a production environment — avoids a "dev door left
    # open" incident.  Both env vars must be checked at startup so the error
    # appears immediately in the process log, not on the first request.
    _check_production_dev_mode_clash()

    # OpenTelemetry setup (idempotent; no-op if already done by tests).
    _setup_telemetry(app)

    # Auth dependency override (prod: OIDC fail-closed; dev/test: keep dev stub).
    _install_auth_override(app)

    # Allow tests to pre-set app.state.engine_toolset (skips subprocess start)
    if getattr(app.state, "engine_toolset", None) is None:
        async with engine_toolset_lifespan() as toolset:
            app.state.engine_toolset = toolset
            _init_app_state(app)
            yield
            # Cleanup on shutdown
            app.state.engine_toolset = None
    else:
        # Test path: engine_toolset already injected by fixture
        _init_app_state(app)
        yield


def _check_production_dev_mode_clash() -> None:
    """Raise RuntimeError if ENV=production and GAMEBOOK_DEV_MODE=1.

    Guards against accidental deployment of a dev-only auth bypass
    in a production environment (FR-008).
    """
    env = os.getenv("ENV", "")
    dev_mode = os.getenv("GAMEBOOK_DEV_MODE", "0")
    if env == "production" and dev_mode in ("1", "true", "True"):
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
      - Neither → refuse to start.  Booting with no configured authentication
        would leave a public API reachable with the well-known dev credential,
        so we raise rather than silently serve.
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

    # T032 (FR-019): 'iss' is always verified, so OIDC_ISSUER must be configured.
    if not os.getenv("OIDC_ISSUER", ""):
        raise RuntimeError(
            "Refusing to start: OIDC is enabled but OIDC_ISSUER is not set. "
            "Configure the expected token issuer (iss)."
        )

    # Production: real OIDC
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

_is_production = os.getenv("ENV") == "production"

app = FastAPI(
    title="Gamebook Web API",
    version="0.1.0",
    description=(
        "Fantasy gamebook engine web backend — narrator-driven play loop "
        "with engine-authoritative numbers (no narrator-fabricated values)."
    ),
    lifespan=lifespan,
    # Disable interactive docs in production (FR-009 — no discovery surface)
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
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
# The SPA frontend (slice 005) will need cross-origin access.  Configure the
# allowed origins explicitly via ``GAMEBOOK_CORS_ORIGINS`` (comma-separated);
# never use a wildcard.  Empty (the default) disables cross-origin requests.
_cors_origins = [
    o.strip()
    for o in os.getenv("GAMEBOOK_CORS_ORIGINS", "").split(",")
    if o.strip()
]
if _cors_origins:
    # Reject wildcard origins when credentials are required — CORS spec forbids
    # allow_credentials=True with allow_origins=["*"] (T053, FR-034).
    if "*" in _cors_origins:
        raise RuntimeError(
            "GAMEBOOK_CORS_ORIGINS=* is not allowed with allow_credentials=True. "
            "Specify explicit origins instead."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

# ---------------------------------------------------------------------------
# Security headers (FR-060) — set on every response, including errors.
# ---------------------------------------------------------------------------

_SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


# ---------------------------------------------------------------------------
# HTTP request metrics (T048/FR-030) — count every request by method/status.
# No PII: only the route template (not the concrete path) and method/status.
# ---------------------------------------------------------------------------

@app.middleware("http")
async def http_metrics_middleware(request: Request, call_next):
    from gamebook_web.observability.tracing import get_metrics

    response = await call_next(request)
    try:
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)
        get_metrics().http_requests_total.add(
            1,
            attributes={
                "method": request.method,
                "path": path_template,
                "status": str(response.status_code),
            },
        )
    except Exception:  # pragma: no cover — metrics must never break a request
        pass
    return response


# ---------------------------------------------------------------------------
# Session-lease guard middleware (T007) — enforces X-Session-Lease on mutating
# /me/game requests when a database is configured.
# ---------------------------------------------------------------------------
from gamebook_web.middleware.lease_guard import LeaseGuardMiddleware  # noqa: E402

app.add_middleware(LeaseGuardMiddleware)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from gamebook_web.api.account import router as account_router        # noqa: E402
from gamebook_web.api.play import router as play_router              # noqa: E402
from gamebook_web.api.sessions import router as sessions_router      # noqa: E402

app.include_router(account_router)
app.include_router(play_router)
app.include_router(sessions_router)


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
    # Annotate the active request span with the error TYPE (no message/traceback,
    # FR-031) so the 500 correlates with the request trace.
    try:
        from opentelemetry import trace

        from gamebook_web.observability.tracing import span_set_error

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            span_set_error(span, exc)
    except Exception:  # pragma: no cover — tracing must never mask the 500
        pass
    logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url)
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
