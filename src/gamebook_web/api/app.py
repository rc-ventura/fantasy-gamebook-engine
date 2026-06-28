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

from gamebook_web.mcp_host import engine_toolset_lifespan
from gamebook_web.sessions.campaign import CampaignRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the engine toolset and initialize shared app state."""

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
# Routers
# ---------------------------------------------------------------------------

from gamebook_web.api.play import router as play_router        # noqa: E402
from gamebook_web.api.combat import router as combat_router    # noqa: E402

app.include_router(play_router)
app.include_router(combat_router)


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
