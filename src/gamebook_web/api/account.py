"""Account identity endpoint (FR-007).

GET /me returns the caller's account identity only — game state lives under
/me/game (D1 backend-scoped routes). This is the dev-stub shape; slice 004
adds real OIDC identity plus account metadata (email, created_at) without
changing the route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gamebook_web.auth.dev_auth import Account, get_current_account

router = APIRouter(tags=["account"])


class AccountResponse(BaseModel):
    id: str


@router.get("/me")
async def get_me(account: Account = Depends(get_current_account)) -> AccountResponse:
    """Return the authenticated account's identity."""
    return AccountResponse(id=account.account_id)
