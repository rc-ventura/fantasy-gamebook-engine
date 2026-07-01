"""Session-lease endpoints (T009).

Routes:
  POST   /campaigns/{id}/session          — acquire lease
  POST   /campaigns/{id}/session/takeover — take over lease from another session
  DELETE /campaigns/{id}/session          — release lease

All endpoints require auth.  Ownership is checked before lease operations.
The X-Session-Lease header is NOT required to acquire (it IS required for
subsequent mutating ops, enforced by LeaseGuardMiddleware).

Database-only mode: if DATABASE_URL is not set, returns a static dev token
so the play loop works without Postgres in pure in-memory tests.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from gamebook_web.api.limiter import SESSION_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account

logger = logging.getLogger(__name__)

router = APIRouter(tags=["session"])

_DEV_FALLBACK_TOKEN = "dev-lease-token"


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class LeaseResponse(BaseModel):
    lease_token: str
    expires_at: str


class TakeoverRequest(BaseModel):
    current_token: str | None = None  # optional — takeover always replaces


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_database() -> bool:
    return bool(os.getenv("DATABASE_URL"))


async def _check_ownership(
    campaign_id: str,
    account: Account,
    request: Request,
) -> None:
    """Assert the account owns this campaign. Raises 404 if not found/not owned."""
    if not _has_database():
        # Dev/test: check in-memory registry
        from gamebook_web.sessions.campaign import get_campaign_registry
        registry = get_campaign_registry(request)
        state = registry.get(campaign_id)
        if state is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "not_found", "message": f"Campaign {campaign_id!r} not found"}},
            )
        if state.account_id != account.account_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": {"code": "not_found", "message": f"Campaign {campaign_id!r} not found"}},
            )
        return

    # Postgres path
    from gamebook_web.accounts import get_account_repository
    repo = get_account_repository()
    campaign = await repo.get_campaign(account.account_id, campaign_id)
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": f"Campaign {campaign_id!r} not found"}},
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/session", status_code=status.HTTP_201_CREATED)
@limiter.limit(SESSION_RATE)
async def acquire_session(
    campaign_id: str,
    request: Request,
    account: Account = Depends(get_current_account),
) -> LeaseResponse:
    """Acquire (or renew) the session lease for this campaign.

    If another account holds an unexpired lease, returns 409.
    To take over, use ``POST /campaigns/{id}/session/takeover``.
    """
    await _check_ownership(campaign_id, account, request)

    if not _has_database():
        # Dev/test fallback — return a static token
        from datetime import datetime, timedelta, timezone
        expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat()
        return LeaseResponse(lease_token=_DEV_FALLBACK_TOKEN, expires_at=expires)

    from gamebook_web.sessions.lease import get_lease_service
    svc = get_lease_service()
    result = await svc.acquire(campaign_id, account.account_id)
    return LeaseResponse(**result)


@router.post("/campaigns/{campaign_id}/session/takeover")
@limiter.limit(SESSION_RATE)
async def takeover_session(
    campaign_id: str,
    request: Request,
    body: TakeoverRequest | None = None,
    account: Account = Depends(get_current_account),
) -> LeaseResponse:
    """Take over the session lease from another session.

    Atomically replaces the current holder.  The old token is invalidated.
    """
    await _check_ownership(campaign_id, account, request)

    if not _has_database():
        from datetime import datetime, timedelta, timezone
        new_token = str(uuid.uuid4())
        expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=30)).isoformat()
        return LeaseResponse(lease_token=new_token, expires_at=expires)

    from gamebook_web.sessions.lease import get_lease_service
    svc = get_lease_service()
    current_token = body.current_token if body else None
    result = await svc.takeover(campaign_id, account.account_id, current_token or "")
    return LeaseResponse(**result)


@router.delete("/campaigns/{campaign_id}/session", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(SESSION_RATE)
async def release_session(
    campaign_id: str,
    request: Request,
    x_session_lease: str | None = Header(default=None, alias="X-Session-Lease"),
    account: Account = Depends(get_current_account),
) -> None:
    """Release the session lease.

    The X-Session-Lease header must match the current lease token.
    """
    await _check_ownership(campaign_id, account, request)

    if not _has_database():
        return  # no-op in dev mode

    if not x_session_lease:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "missing_token", "message": "X-Session-Lease header required"}},
        )

    from gamebook_web.sessions.lease import get_lease_service
    svc = get_lease_service()
    await svc.release(campaign_id, x_session_lease)
