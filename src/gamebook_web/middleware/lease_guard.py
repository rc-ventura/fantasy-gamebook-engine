"""Session-lease guard middleware (T007).

Intercepts all state-changing HTTP requests to campaign endpoints and
validates the ``X-Session-Lease`` header against the active lease.

Mutating methods: POST, DELETE, PATCH, PUT
Exempted paths (no lease required):
  - /health
  - GET any path (read-only)
  - POST /campaigns  (create campaign — no lease yet)
  - POST /campaigns/{id}/session*  (lease endpoints themselves)
  - POST /campaigns/{id}/character  (initial character creation; no lease yet)
  - DELETE /campaigns/{id}  (campaign deletion — handled by account layer)

All other POST/DELETE to ``/campaigns/{id}/**`` require ``X-Session-Lease``.

DATABASE_URL not set → middleware passes through (dev/test with InMemoryStorage).
"""

from __future__ import annotations

import json
import logging
import os
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Paths that are exempt from lease checking (even if mutating)
_EXEMPT_EXACT: frozenset[str] = frozenset({"/campaigns"})
_EXEMPT_SUFFIX_PATTERNS: list[re.Pattern] = [
    re.compile(r"^/campaigns/[^/]+/session(/takeover)?$"),
    re.compile(r"^/campaigns/[^/]+/character$"),
    re.compile(r"^/campaigns/[^/]+$"),  # DELETE /campaigns/{id} — campaign deletion
    re.compile(r"^/me.*$"),             # /me, /me/export
]

# Campaign ID extraction from path
_CAMPAIGN_ID_RE = re.compile(r"^/campaigns/([^/]+)(/.*)?$")

# Mutating methods that require a lease
_MUTATING_METHODS = frozenset({"POST", "DELETE", "PATCH", "PUT"})


def _is_exempt(path: str, method: str) -> bool:
    """Return True if this request does not need a lease check."""
    if method == "GET":
        return True
    if method == "OPTIONS":
        return True
    if path == "/campaigns":
        return True
    for pattern in _EXEMPT_SUFFIX_PATTERNS:
        if pattern.match(path):
            return True
    return False


def _error_response(code: str, message: str, status_code: int = 409) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


class LeaseGuardMiddleware(BaseHTTPMiddleware):
    """Validate X-Session-Lease on all state-changing campaign requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        # Read DATABASE_URL per request (not cached at construction): this
        # middleware is registered at import time, before the lifespan loads
        # the environment, so caching it here would permanently disable lease
        # enforcement whenever the URL is set later at runtime (auth bypass).
        if not os.getenv("DATABASE_URL"):
            # Skip if no DATABASE_URL (InMemoryStorage / test mode without Postgres)
            return await call_next(request)

        # Skip non-mutating methods (GET, HEAD, OPTIONS, etc.) — only the
        # state-changing methods require a lease.
        if method not in _MUTATING_METHODS:
            return await call_next(request)

        # Skip exempt paths
        if _is_exempt(path, method):
            return await call_next(request)

        # Only mutating methods require a lease (HEAD and other read-only or
        # non-standard methods pass through untouched).
        if method not in _MUTATING_METHODS:
            return await call_next(request)

        # Extract campaign_id from path
        match = _CAMPAIGN_ID_RE.match(path)
        if not match:
            return await call_next(request)

        campaign_id = match.group(1)

        # Read the lease token header
        lease_token = request.headers.get("X-Session-Lease")
        if not lease_token:
            return _error_response(
                "not_session_holder",
                "X-Session-Lease header is required for state-changing operations.",
                status_code=409,
            )

        # Validate with LeaseService
        try:
            from gamebook_web.sessions.lease import get_lease_service
            lease_svc = get_lease_service()
            await lease_svc.validate(campaign_id, lease_token)
        except Exception as exc:
            # HTTPException from validate() carries the right status/body
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                detail = exc.detail
                if isinstance(detail, dict):
                    return JSONResponse(status_code=exc.status_code, content=detail)
                return _error_response("not_session_holder", str(detail), status_code=exc.status_code)
            logger.exception("Lease validation error for campaign %s: %s", campaign_id, exc)
            return _error_response("internal_error", "Session validation failed.", status_code=500)

        response = await call_next(request)

        # Renew lease TTL on successful state change
        if response.status_code < 400:
            try:
                from gamebook_web.sessions.lease import get_lease_service
                lease_svc = get_lease_service()
                await lease_svc.renew(campaign_id, lease_token)
            except Exception:
                # Non-fatal — lease renewal failure doesn't break the response
                pass

        return response
