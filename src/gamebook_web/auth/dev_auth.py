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
  All routes use ``Depends(get_current_account)``.  Slice 004 installs a FastAPI
  dependency override so those calls route to ``oidc_auth.get_current_account``
  in production — the play loop is untouched.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import NoReturn

from fastapi import Header, HTTPException, Request, status

logger = logging.getLogger(__name__)

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
# ``tests/server/test_constants.py``.
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
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Account:
    """Dev auth stub: authenticate the caller and return an Account.

    Fail-closed: when ``GAMEBOOK_DEV_MODE`` is not explicitly enabled this
    dependency rejects EVERY request with ``401`` — including ``Bearer
    dev-token``.  In dev mode it accepts ``Bearer dev-token`` or no token.
    """
    if not _dev_mode_enabled():
        _unauthenticated("Authentication is not configured", request)

    if authorization is None:
        return Account(account_id=DEV_ACCOUNT_ID)

    if not authorization.startswith("Bearer "):
        _unauthenticated("Authorization header must be 'Bearer <token>'", request)

    token = authorization[len("Bearer "):]
    if token != _DEV_TOKEN_VALUE:
        _unauthenticated("Invalid token", request)

    return Account(account_id=DEV_ACCOUNT_ID)


def _unauthenticated(message: str, request: Request | None = None) -> NoReturn:
    from gamebook_web.observability.audit import audit_event

    path = request.url.path if request is not None else "unknown"
    logger.warning("auth failed: reason=%s path=%s", message, path)
    audit_event("auth.failed", level=logging.WARNING, reason=message.replace(" ", "_"))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthenticated", "message": message}},
    )
