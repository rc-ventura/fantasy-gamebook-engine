"""Dev auth stub — single development account (replaced by OIDC in slice 004).

Accepts (ONLY when ``GAMEBOOK_DEV_MODE`` is explicitly enabled):
  - ``Authorization: Bearer dev-token`` header → dev account
  - No token at all → dev account

Fail-closed default:
  ``GAMEBOOK_DEV_MODE`` defaults to OFF.  When it is not explicitly enabled this
  stub rejects EVERY request with ``401`` — including ``Bearer dev-token`` — so
  a deploy that reaches production before OIDC (slice 004) is configured has no
  reachable credential.  The lifespan additionally refuses to start in that
  configuration (see ``app._install_auth_override``).

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

DEV_ACCOUNT_ID = "dev-account"
DEV_CAMPAIGN_ID = "dev-campaign"   # default campaign for dev/test

# The magic dev credential is NOT a production constant (T031, ADR-022): it is
# only bound when ``GAMEBOOK_DEV_MODE`` is explicitly enabled.  In production the
# name ``DEV_TOKEN`` does not exist on this module, so no code path can compare a
# request against a hardcoded bearer string.  Tests import their own copy from
# ``tests/server/test_constants.py`` instead of relying on this attribute.
_DEV_TOKEN_VALUE = "dev-token"


def _dev_mode_enabled() -> bool:
    """True only when GAMEBOOK_DEV_MODE is explicitly enabled (read live)."""
    return os.getenv("GAMEBOOK_DEV_MODE", "0") in ("1", "true", "True")


if _dev_mode_enabled():  # pragma: no cover - import-time env branch
    DEV_TOKEN = _DEV_TOKEN_VALUE


# ---------------------------------------------------------------------------
# FastAPI dependency (injected by Depends; overrideable in 004)
# ---------------------------------------------------------------------------

async def get_current_account(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Account:
    """Dev auth stub: authenticate the caller and return an Account.

    Fail-closed: when ``GAMEBOOK_DEV_MODE`` is not explicitly enabled this
    dependency rejects EVERY request with ``401`` — including ``Bearer
    dev-token`` — so a stray deploy without OIDC configured cannot be reached
    with the well-known dev credential.  In dev mode it accepts ``Bearer
    dev-token`` or no token at all.
    """
    if not _dev_mode_enabled():
        _unauthenticated("Authentication is not configured")

    if authorization is None:
        return Account(account_id=DEV_ACCOUNT_ID)

    if not authorization.startswith("Bearer "):
        _unauthenticated("Authorization header must be 'Bearer <token>'")

    token = authorization[len("Bearer "):]
    if token != _DEV_TOKEN_VALUE:
        _unauthenticated("Invalid token")

    return Account(account_id=DEV_ACCOUNT_ID)


def _unauthenticated(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthenticated", "message": message}},
    )
