"""Privacy and account endpoints (T011).

Routes:
  GET    /me          — caller's account info (account_id, sub, created_at)
  GET    /me/export   — portable export of all owned game data (GDPR)
  DELETE /me          — cascade-delete account + all owned campaigns + engine rows

All require auth.  No cross-account data is returned.

Database-only mode: if DATABASE_URL is not set, returns dev stub responses.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from gamebook_web.api.limiter import PRIVACY_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])


class AccountResponse(BaseModel):
    """GET /me identity shape — matches the SPA's ``Account`` type (D1)."""

    id: str


class DeleteAccountRequest(BaseModel):
    """Erasure is irreversible, so it requires an explicit confirmation flag
    (FR-025): a request without ``confirmation: true`` is rejected 400."""

    confirmation: bool = False


def _has_database() -> bool:
    return bool(os.getenv("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/me")
async def get_me(
    account: Account = Depends(get_current_account),
) -> AccountResponse:
    """Return the authenticated account's identity (``{id}`` — SPA-compatible)."""
    return AccountResponse(id=account.account_id)


@router.get("/me/export")
@limiter.limit(PRIVACY_RATE)
async def export_me(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Export all data owned by the caller (GDPR data portability)."""
    if not _has_database():
        return {
            "account": {"account_id": account.account_id, "sub": account.account_id},
            "campaigns": [],
        }

    from gamebook_web.accounts import get_account_repository
    repo = get_account_repository()
    return await repo.export_account(account.account_id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(PRIVACY_RATE)
async def delete_me(
    request: Request,
    body: DeleteAccountRequest | None = None,
    account: Account = Depends(get_current_account),
) -> None:
    """Cascade-delete the account and all owned campaigns and engine rows (GDPR erasure).

    Requires ``{"confirmation": true}`` (FR-025); returns 404 if the account
    does not exist rather than a misleading 204.
    """
    if body is None or not body.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "confirmation_required",
                    "message": "Account deletion is irreversible; send {\"confirmation\": true}.",
                }
            },
        )

    from gamebook_web.observability.audit import audit_event

    if not _has_database():
        logger.info("DEV MODE: delete_me called for %s (no-op)", account.account_id)
        audit_event("account.deleted", account_id=account.account_id)
        return

    from gamebook_web.accounts import get_account_repository
    repo = get_account_repository()
    acc = await repo.get_account_by_id(account.account_id)
    if acc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Account not found"}},
        )
    await repo.delete_account(account.account_id)
    audit_event("account.deleted", account_id=account.account_id)
