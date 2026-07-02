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

def _trusted_proxy() -> bool:
    # Read lazily so tests (and container restarts) see the current env value.
    return os.getenv("GAMEBOOK_TRUSTED_PROXY", "0") in ("1", "true", "True")


def rate_limit_key(request: Request) -> str:
    """Key authenticated traffic on the account; unauthenticated on the IP.

    The dev auth stub maps the single valid token to the dev account; slice 004
    (real OIDC) swaps this to key on the validated token's ``sub`` claim.  An
    *invalid* bearer token must NOT get its own bucket (that would let an
    attacker mint fresh buckets per request), so anything unverified falls
    back to the IP key.
    """
    # Import here (not module top) to keep the auth seam swappable without a
    # circular import once oidc_auth replaces dev_auth in slice 004.
    from gamebook_web.auth.dev_auth import DEV_ACCOUNT_ID, DEV_TOKEN

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer ") and authorization[len("Bearer "):] == DEV_TOKEN:
        return f"account:{DEV_ACCOUNT_ID}"

    if _trusted_proxy():
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Left-most entry is the original client when the proxy appends.
            return forwarded.split(",")[0].strip()

    return get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key)
