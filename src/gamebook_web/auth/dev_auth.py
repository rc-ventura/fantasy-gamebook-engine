"""Dev auth stub — single development account (replaced by OIDC in slice 004).

Accepts:
  - ``Authorization: Bearer dev-token`` header → dev account
  - No token at all in dev mode (``GAMEBOOK_DEV_MODE=1``) → dev account

The seam:
  All routes use ``Depends(get_current_account)``.  Slice 004 replaces this
  module (swap ``dev_auth.py`` → ``oidc_auth.py``) and the play loop is
  untouched.  No play-loop endpoint imports a concrete auth implementation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

# ---------------------------------------------------------------------------
# Account type — shared between auth impls (004 uses the same dataclass)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Account:
    account_id: str


# ---------------------------------------------------------------------------
# Shared dev constants
# ---------------------------------------------------------------------------

DEV_TOKEN = "dev-token"
DEV_ACCOUNT_ID = "dev-account"
DEV_CAMPAIGN_ID = "dev-campaign"   # default campaign for dev/test

# ---------------------------------------------------------------------------
# FastAPI dependency (injected by Depends; overrideable in 004)
# ---------------------------------------------------------------------------

async def get_current_account(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Account:
    """Dev auth stub: authenticate the caller and return an Account.

    Accepts ``Bearer dev-token`` or (in dev mode) no token at all.
    Returns an :class:`Account` on success; raises ``401`` on failure.
    """
    dev_mode = os.getenv("GAMEBOOK_DEV_MODE", "1") not in ("0", "false", "False")

    if authorization is None:
        if dev_mode:
            return Account(account_id=DEV_ACCOUNT_ID)
        _unauthenticated("Missing Authorization header")

    if not authorization.startswith("Bearer "):
        _unauthenticated("Authorization header must be 'Bearer <token>'")

    token = authorization[len("Bearer "):]
    if token != DEV_TOKEN:
        _unauthenticated("Invalid token")

    return Account(account_id=DEV_ACCOUNT_ID)


def _unauthenticated(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthenticated", "message": message}},
    )
