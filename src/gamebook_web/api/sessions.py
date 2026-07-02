"""Session-lease endpoints — D1 backend-scoped routes (ADR-017, ADR-023).

Routes:
  POST   /me/game/session           — acquire the write lease
  POST   /me/game/session/takeover  — force-take the lease from another holder
  DELETE /me/game/session           — release the write lease

These routes are stub implementations for slice 006 (correct D1 routes).
Slice 004 replaces the bodies with real DB-backed lease semantics
(pg advisory locks + expiry, ``takeover`` validates current_token, etc.).

The frontend gates calls behind ``VITE_SESSION_LEASE=true`` (T022); by
default it skips these endpoints and plays without a lease.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request

from gamebook_web.auth.dev_auth import Account, get_current_account

router = APIRouter(tags=["sessions"])


class SessionLease:
    """Minimal response shape for session-lease endpoints."""

    def __init__(self, token: str, expires_at: str) -> None:
        self.session_token = token
        self.expires_at = expires_at

    def model_dump(self) -> dict[str, Any]:
        return {"session_token": self.session_token, "expires_at": self.expires_at}


def _new_lease() -> dict[str, str]:
    token = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    return {"session_token": token, "expires_at": expires_at}


# ---------------------------------------------------------------------------
# Routes (D1 — /me/game/session, replacing /campaigns/{id}/session)
# ---------------------------------------------------------------------------

@router.post("/me/game/session")
async def acquire_session(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, str]:
    """Acquire the play-session write lease for the caller's active campaign.

    Slice 004 implements real lease semantics (exclusive lock per campaign,
    takeover validation, DB persistence).  This stub returns a token
    unconditionally so the frontend session-lease flow can be exercised
    end-to-end in dev mode.
    """
    return _new_lease()


@router.post("/me/game/session/takeover")
async def takeover_session(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, str]:
    """Force-take the write lease, invalidating the previous holder's token.

    Slice 004 validates ``current_token`` from the request body against the
    stored holder before issuing a new lease (ADR-023).  This stub accepts
    any request and returns a fresh token.
    """
    return _new_lease()


@router.delete("/me/game/session", status_code=204)
async def release_session(
    request: Request,
    account: Account = Depends(get_current_account),
) -> None:
    """Release the write lease.  Slice 004 marks the lease as released in the DB."""
