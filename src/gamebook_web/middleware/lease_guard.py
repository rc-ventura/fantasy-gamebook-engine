"""Session-lease guard middleware (T007).

Validates the ``X-Session-Lease`` header on state-changing requests against the
active lease.  Originally written for the ``/campaigns/{id}/**`` route scheme;
the app now uses D1 backend-scoped routes (``/me/game/**``) where the lease is
scoped to the account's *active* campaign rather than a URL campaign_id.

D1 note (deferred):
  Enforcing a per-account lease in ASGI middleware needs the account resolved
  (auth) and its active campaign looked up — which the route-level dependency
  does, but the middleware cannot do cheaply for OIDC tokens.  For now every
  ``/me/**`` route is exempt (pass-through); lease acquire/takeover/release and
  ``LeaseService`` remain fully functional via ``sessions.py`` (called directly
  by the SPA when ``VITE_SESSION_LEASE=true``).  Per-request middleware
  enforcement on D1 is a follow-up.

Mutating methods: POST, DELETE, PATCH, PUT
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

# Paths exempt from lease checking (even if mutating).  All D1 routes live under
# ``/me`` and are currently exempt (see the D1 note above).
_EXEMPT_SUFFIX_PATTERNS: list[re.Pattern] = [
    re.compile(r"^/me.*$"),   # all D1 backend-scoped routes (/me/game/**, /me/**)
]

# Legacy campaign-id extraction (retained for the not-yet-wired D1 enforcement).
_CAMPAIGN_ID_RE = re.compile(r"^/campaigns/([^/]+)(/.*)?$")

# Mutating methods that require a lease
_MUTATING_METHODS = frozenset({"POST", "DELETE", "PATCH", "PUT"})


def _is_exempt(path: str, method: str) -> bool:
    """Return True if this request does not need a lease check."""
    if method in ("GET", "OPTIONS", "HEAD"):
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
            # No DATABASE_URL means the in-memory backend is in use.  In a
            # production deployment (signalled by an OIDC config being present)
            # a missing DATABASE_URL is a misconfiguration, not a valid dev
            # setup — fail closed so lease enforcement never silently vanishes
            # (CWE-636).  Otherwise pass through for InMemoryStorage / tests.
            if os.getenv("OIDC_JWKS_URI"):
                return _error_response(
                    "auth_unavailable",
                    "Session enforcement is unavailable (database not configured).",
                    status_code=503,
                )
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

        from gamebook_web.observability.audit import audit_event

        # Read the lease token header
        lease_token = request.headers.get("X-Session-Lease")
        if not lease_token:
            audit_event("lease.denied", level=logging.WARNING, campaign_id=campaign_id, reason="missing_token")
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
                audit_event("lease.denied", level=logging.WARNING, campaign_id=campaign_id, reason="validate_failed")
                detail = exc.detail
                if isinstance(detail, dict):
                    return JSONResponse(status_code=exc.status_code, content=detail)
                return _error_response("not_session_holder", str(detail), status_code=exc.status_code)
            # No traceback in logs (FR-031) — log only the exception type.
            logger.error("Lease validation error for campaign %s: %s", campaign_id, type(exc).__name__)
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
