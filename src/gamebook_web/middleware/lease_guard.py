"""Database-misconfiguration guard middleware (T007, amended by ADR-031).

Originally this middleware also validated ``X-Session-Lease`` on mutating
requests, extracting ``campaign_id`` straight from the URL under the
``/campaigns/{id}/**`` route scheme. The D1 redesign (``/me/game/**``)
resolves ``campaign_id`` from the caller's *account*, not the URL — which
needs the auth dependency to have already run through FastAPI's (overridable)
DI graph. Plain ASGI middleware cannot do that safely (calling
``get_current_account`` directly, rather than via ``Depends()``, bypasses
``app.dependency_overrides`` and would always resolve to the dev stub — a
silent auth bypass). Real per-request lease enforcement now lives in the
route-level ``require_lease`` dependency (``sessions/lease.py``), applied
directly to each mutating ``/me/game/**`` route — see ADR-031.

What this middleware still does: fail closed if OIDC is configured but
``DATABASE_URL`` is missing. That combination means lease state cannot be
tracked at all in a deployment that expects real auth, which is a
misconfiguration serious enough to reject every mutating request outright
rather than silently disable the lease.
"""

from __future__ import annotations

import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_MUTATING_METHODS = frozenset({"POST", "DELETE", "PATCH", "PUT"})


def _error_response(code: str, message: str, status_code: int = 503) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


class LeaseGuardMiddleware(BaseHTTPMiddleware):
    """Fail closed on mutating requests when OIDC is configured but the
    database (and therefore lease state) is not."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        if method in _MUTATING_METHODS and not os.getenv("DATABASE_URL") and os.getenv("OIDC_JWKS_URI"):
            # Read DATABASE_URL per request (not cached at construction): this
            # middleware is registered at import time, before the lifespan
            # loads the environment, so caching would permanently disable the
            # guard whenever the URL is set later at runtime (CWE-636).
            return _error_response(
                "auth_unavailable",
                "Session enforcement is unavailable (database not configured).",
                status_code=503,
            )
        return await call_next(request)
