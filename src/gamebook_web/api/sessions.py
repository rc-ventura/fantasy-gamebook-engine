"""Session-lease endpoints — D1 backend-scoped routes (ADR-017, ADR-023).

Routes:
  POST   /me/game/session           — acquire the write lease
  POST   /me/game/session/takeover  — force-take the lease (validates current_token)
  DELETE /me/game/session           — release the write lease

The lease is scoped to the caller's active campaign (resolved from the account,
D1).  Without ``DATABASE_URL`` (dev/test) a stub token is returned so the SPA
session-lease flow works without Postgres; with a database, real DB-backed lease
semantics apply (``LeaseService`` — pg row locks + expiry, ``takeover``
validates ``current_token`` per ADR-023/FR-027).

The SPA gates these behind ``VITE_SESSION_LEASE=true`` (T022); by default it
plays without a lease.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from gamebook_web.api.limiter import SESSION_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.observability.audit import audit_event
from gamebook_web.sessions.campaign import get_campaign_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


class TakeoverRequest(BaseModel):
    # Required in the DB path (FR-027): takeover validates this against the
    # current holder's token; a wrong/missing token → 409.  Optional-typed so the
    # dev fallback (no DB, non-enforcing) still accepts an empty body.
    current_token: str | None = None


def _has_database() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def _stub_lease() -> dict[str, str]:
    """Non-enforcing dev token (SPA-compatible ``session_token`` shape)."""
    token = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    return {"session_token": token, "expires_at": expires_at}


def _to_session_response(result: dict[str, Any]) -> dict[str, str]:
    """LeaseService returns ``lease_token``; the SPA expects ``session_token``."""
    return {"session_token": result["lease_token"], "expires_at": result["expires_at"]}


async def _active_campaign_id(request: Request, account: Account) -> str:
    """Resolve the account's active campaign_id (D1), or 404 if none."""
    registry = get_campaign_registry(request)
    state = await registry.get_active_for_account(account.account_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "no_active_campaign",
                    "message": "No active game found for this account.",
                }
            },
        )
    return state.campaign_id


# ---------------------------------------------------------------------------
# Routes (D1 — /me/game/session)
# ---------------------------------------------------------------------------

@router.post("/me/game/session")
@limiter.limit(SESSION_RATE)
async def acquire_session(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, str]:
    """Acquire the play-session write lease for the caller's active campaign."""
    if not _has_database():
        audit_event("session.acquired", account_id=account.account_id)
        return _stub_lease()

    campaign_id = await _active_campaign_id(request, account)
    from gamebook_web.sessions.lease import get_lease_service

    result = await get_lease_service().acquire(campaign_id, account.account_id)
    audit_event("session.acquired", account_id=account.account_id, campaign_id=campaign_id)
    return _to_session_response(result)


@router.post("/me/game/session/takeover")
@limiter.limit(SESSION_RATE)
async def takeover_session(
    request: Request,
    body: TakeoverRequest | None = None,
    account: Account = Depends(get_current_account),
) -> dict[str, str]:
    """Force-take the write lease, invalidating the previous holder's token.

    In the DB path this validates ``current_token`` against the stored holder
    (ADR-023/FR-027): a wrong/missing token → 409.
    """
    if not _has_database():
        audit_event("session.takeover", account_id=account.account_id)
        return _stub_lease()

    campaign_id = await _active_campaign_id(request, account)
    from gamebook_web.sessions.lease import get_lease_service

    current_token = body.current_token if body else None
    result = await get_lease_service().takeover(campaign_id, account.account_id, current_token or "")
    audit_event("session.takeover", account_id=account.account_id, campaign_id=campaign_id)
    return _to_session_response(result)


@router.delete("/me/game/session", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(SESSION_RATE)
async def release_session(
    request: Request,
    x_session_lease: str | None = Header(default=None, alias="X-Session-Lease"),
    account: Account = Depends(get_current_account),
) -> None:
    """Release the write lease."""
    if not _has_database():
        audit_event("session.released", account_id=account.account_id)
        return

    campaign_id = await _active_campaign_id(request, account)
    if not x_session_lease:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "missing_token", "message": "X-Session-Lease header required"}},
        )
    from gamebook_web.sessions.lease import get_lease_service

    await get_lease_service().release(campaign_id, account.account_id, x_session_lease)
    audit_event("session.released", account_id=account.account_id, campaign_id=campaign_id)
