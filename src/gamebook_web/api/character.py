from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic_ai.mcp import MCPToolset

from gamebook_web.adventure_module import get_adventure_config
from gamebook_web.api.deps import assert_not_ended, get_active_campaign
from gamebook_web.api.schemas import CreateCharacterRequest
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, get_campaign_registry
from gamebook_web.sessions.lease import require_lease

logger = logging.getLogger(__name__)

router = APIRouter(tags=["character"])


@router.post("/me/game/character", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_lease)])
async def create_character(
    request: Request,
    body: CreateCharacterRequest | None = None,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    registry: CampaignRegistry = get_campaign_registry(request)
    state = await get_active_campaign(account.account_id, registry)
    assert_not_ended(state)

    toolset: MCPToolset = get_engine_toolset(request)
    campaign_id = state.campaign_id
    name = (body.name if body else None) or "Hero"

    try:
        character = await call_engine(toolset, "create_character", campaign_id=campaign_id, name=name)
        opening_location = get_adventure_config().opening_location
        if opening_location:
            await call_engine(toolset, "update_world", campaign_id=campaign_id,
                              changes={"current_location": opening_location})
    except Exception as exc:
        msg = str(exc)
        logger.warning("create_character failed for campaign %s: %s", campaign_id, msg)
        if "living character" in msg or "already exists" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": {"code": "character_exists", "message": "A living character already exists for this campaign"}},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "engine_error", "message": "Character creation failed"}},
        ) from exc
    return character


@router.get("/me/game/character")
async def read_character(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    registry: CampaignRegistry = get_campaign_registry(request)
    state = await get_active_campaign(account.account_id, registry)
    toolset: MCPToolset = get_engine_toolset(request)
    campaign_id = state.campaign_id

    character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "No character created yet"}},
        )
    return character


@router.get("/me/game/scene")
async def get_scene(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    registry: CampaignRegistry = get_campaign_registry(request)
    state = await get_active_campaign(account.account_id, registry)
    return {"scene": state.current_scene}
