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

from fastapi import APIRouter, Depends, HTTPException, status

from gamebook_web.auth.dev_auth import Account, get_current_account

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])


def _has_database() -> bool:
    return bool(os.getenv("DATABASE_URL"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/me")
async def get_me(
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Return the authenticated account's identity (no PII beyond opaque sub)."""
    if not _has_database():
        return {
            "account_id": account.account_id,
            "sub": account.account_id,  # dev stub: sub == account_id
            "created_at": None,
        }

    from gamebook_web.accounts import get_account_repository
    repo = get_account_repository()
    acc = await repo.get_account_by_id(account.account_id)
    if acc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Account not found"}},
        )
    return acc


@router.get("/me/export")
async def export_me(
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
async def delete_me(
    account: Account = Depends(get_current_account),
) -> None:
    """Cascade-delete the account and all owned campaigns and engine rows (GDPR erasure)."""
    if not _has_database():
        logger.info("DEV MODE: delete_me called for %s (no-op)", account.account_id)
        return

    from gamebook_web.accounts import get_account_repository
    repo = get_account_repository()
    await repo.delete_account(account.account_id)
