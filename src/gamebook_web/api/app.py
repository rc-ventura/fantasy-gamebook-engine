from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gamebook_web.api.errors import register_error_handlers
from gamebook_web.api.limiter import limiter
from gamebook_web.api.lifespan import (
    lifespan,
    _check_production_dev_mode_clash,
    _configure_narrator,
    _resolve_api_key,
)
from gamebook_web.middleware.http_metrics import http_metrics_middleware
from gamebook_web.middleware.lease_guard import LeaseGuardMiddleware
from gamebook_web.middleware.security_headers import security_headers_middleware
from gamebook_web.observability.log_setup import setup_logging

setup_logging()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_is_production = os.getenv("ENV", "").lower() == "production"

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
# Rate limiting (CWE-770)
# ---------------------------------------------------------------------------
app.state.limiter = limiter

# ---------------------------------------------------------------------------
# CORS — restrictive by default (CWE-942)
# ---------------------------------------------------------------------------
_cors_origins = [
    o.strip()
    for o in os.getenv("GAMEBOOK_CORS_ORIGINS", "").split(",")
    if o.strip()
]
if _cors_origins:
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
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(LeaseGuardMiddleware)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(http_metrics_middleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from gamebook_web.api.account import router as account_router        
from gamebook_web.api.character import router as character_router    
from gamebook_web.api.game import router as game_router              
from gamebook_web.api.sessions import router as sessions_router      
from gamebook_web.api.turn import router as turn_router              

app.include_router(account_router)
app.include_router(game_router)
app.include_router(character_router)
app.include_router(turn_router)
app.include_router(sessions_router)

# ---------------------------------------------------------------------------
# Error handlers (CONTRACTS.md §9)
# ---------------------------------------------------------------------------
register_error_handlers(app)

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Engine health check — returns ``{status: ok, version: ...}``."""
    return {"status": "ok", "version": app.version}
