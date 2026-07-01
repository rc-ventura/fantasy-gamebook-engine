"""Shared rate limiter (CWE-770).

Defined in its own module so both ``api/app.py`` (which registers it on the app
and installs the exception handler) and the route modules (which apply
``@limiter.limit(...)`` decorators) can import it without a circular import.

Limits can be tuned via env vars:
  - ``GAMEBOOK_TURN_RATE``    (default ``"30/minute"``) — the expensive /turn
    endpoint, which triggers LLM calls in production.
  - ``GAMEBOOK_COMBAT_RATE``  (default ``"60/minute"``) — combat round / flee.

Set any limit to ``"1000000/minute"`` (or disable in config) to effectively
turn it off for trusted internal callers.
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

TURN_RATE = os.getenv("GAMEBOOK_TURN_RATE", "30/minute")
COMBAT_RATE = os.getenv("GAMEBOOK_COMBAT_RATE", "60/minute")

# Session-lease lifecycle endpoints (acquire/takeover/release).  These perform
# DB writes (SELECT ... FOR UPDATE) and should be bounded to prevent abuse.
SESSION_RATE = os.getenv("GAMEBOOK_SESSION_RATE", "60/minute")

# Privacy endpoints.  Export runs an N+1 read across all owned campaigns and
# delete performs a cascade delete, so both get a strict limit (CWE-770).
PRIVACY_RATE = os.getenv("GAMEBOOK_PRIVACY_RATE", "5/minute")
