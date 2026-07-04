"""Shared rate limiter (CWE-770).

Defined in its own module so both ``api/app.py`` (which registers it on the app
and installs the exception handler) and the route modules (which apply
``@limiter.limit(...)`` decorators) can import it without a circular import.

Rate-limit key (FR-046):
  - Authenticated requests are keyed on the **account**, not the client IP, so
    a player behind a shared NAT/proxy is not throttled by neighbours and a
    single account cannot dodge limits by rotating IPs.
  - Unauthenticated requests fall back to the client IP.  ``X-Forwarded-For``
    is honoured only when ``GAMEBOOK_TRUSTED_PROXY=1`` is set (the header is
    trivially spoofable when the app is not behind a trusted reverse proxy).

Limits can be tuned via env vars:
  - ``GAMEBOOK_TURN_RATE``    (default ``"30/minute"``) — the expensive /turn
    endpoint, which triggers LLM calls in production.
  - ``GAMEBOOK_COMBAT_RATE``  (default ``"60/minute"``) — combat round / flee.

Set any limit to ``"1000000/minute"`` (or disable in config) to effectively
turn it off for trusted internal callers.
"""

from __future__ import annotations

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

TURN_RATE = os.getenv("GAMEBOOK_TURN_RATE", "30/minute")
COMBAT_RATE = os.getenv("GAMEBOOK_COMBAT_RATE", "60/minute")

# Session-lease lifecycle endpoints (acquire/takeover/release).  These perform
# DB writes (SELECT ... FOR UPDATE) and should be bounded to prevent abuse.
SESSION_RATE = os.getenv("GAMEBOOK_SESSION_RATE", "60/minute")

# Privacy endpoints.  Export runs an N+1 read across all owned campaigns and
# delete performs a cascade delete, so both get a strict limit (CWE-770).
PRIVACY_RATE = os.getenv("GAMEBOOK_PRIVACY_RATE", "5/minute")


def _trusted_proxy() -> bool:
    # Read lazily so tests (and container restarts) see the current env value.
    return os.getenv("GAMEBOOK_TRUSTED_PROXY", "0") in ("1", "true", "True")


def rate_limit_key(request: Request) -> str:
    """Key authenticated traffic on the account; unauthenticated on the IP.

    In dev mode the stub maps the single valid token to the dev account.  Under
    real OIDC we cannot cheaply verify the token here (the limiter key runs
    before auth), so anything that is not the recognised dev credential falls
    back to the IP key — an *invalid* bearer token must NOT get its own bucket
    (that would let an attacker mint fresh buckets per request).
    """
    # Import here (not module top) to keep the auth seam swappable without a
    # circular import.  DEV_TOKEN only exists on dev_auth in dev mode (it is
    # fail-closed in production), so read it defensively.
    from gamebook_web.auth import dev_auth

    dev_token = getattr(dev_auth, "DEV_TOKEN", None)
    authorization = request.headers.get("Authorization", "")
    if dev_token and authorization.startswith("Bearer ") and authorization[len("Bearer "):] == dev_token:
        return f"account:{dev_auth.DEV_ACCOUNT_ID}"

    if _trusted_proxy():
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Left-most entry is the original client when the proxy appends.
            return forwarded.split(",")[0].strip()

    return get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key)
