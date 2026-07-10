from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic_ai.mcp import MCPToolset

from gamebook_web.api.deps import assert_not_ended, get_active_campaign
from gamebook_web.api.schemas import CreateGameRequest, GameResponse, GraveyardEntry, SaveResponse
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, get_campaign_registry
from gamebook_web.sessions.lease import require_lease

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game"])


@router.post("/me/game", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_lease)])
async def create_game(
    request: Request,
    body: CreateGameRequest | None = None,
    account: Account = Depends(get_current_account),
) -> GameResponse:
    from gamebook_web.observability.tracing import get_metrics

    registry: CampaignRegistry = get_campaign_registry(request)
    existing = registry.get_active_for_account(account.account_id)
    if existing is not None:
        registry.set_ended(existing.campaign_id)
        get_metrics().active_campaigns.add(-1)
    name = (body.name if body else None)
    state = registry.create(account.account_id, name=name)
    get_metrics().active_campaigns.add(1)
    return GameResponse(status=state.status, campaign_id=state.campaign_id, name=state.name)


@router.get("/me/game")
async def get_game(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    registry: CampaignRegistry = get_campaign_registry(request)
    state = get_active_campaign(account.account_id, registry)
    campaign_id = state.campaign_id
    toolset: MCPToolset = get_engine_toolset(request)

    character = None
    try:
        character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
    except Exception:
        pass

    world = await call_engine(toolset, "read_world", campaign_id=campaign_id)
    summary = await call_engine(toolset, "read_summary", campaign_id=campaign_id)
    events = await call_engine(toolset, "read_events", campaign_id=campaign_id)

    return {
        "status": state.status,
        "name": state.name,
        "character": character,
        "world": world,
        "summary": summary,
        "events": events,
        "current_scene": state.current_scene,
    }


@router.delete("/me/game", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_lease)])
async def delete_game(
    request: Request,
    account: Account = Depends(get_current_account),
) -> None:
    from gamebook_web.observability.tracing import get_metrics

    registry: CampaignRegistry = get_campaign_registry(request)
    state = get_active_campaign(account.account_id, registry)
    was_active = state.status != "ended"
    registry.set_ended(state.campaign_id)
    if was_active:
        get_metrics().active_campaigns.add(-1)


@router.post("/me/game/save", dependencies=[Depends(require_lease)])
async def save_game(
    request: Request,
    account: Account = Depends(get_current_account),
) -> SaveResponse:
    registry: CampaignRegistry = get_campaign_registry(request)
    state = get_active_campaign(account.account_id, registry)
    assert_not_ended(state)
    toolset: MCPToolset = get_engine_toolset(request)
    campaign_id = state.campaign_id

    result = await call_engine(toolset, "save_progress", campaign_id=campaign_id, slot=None)
    return SaveResponse(ok=True, slot=result.get("slot") if isinstance(result, dict) else None)


@router.get("/me/graveyard")
async def get_graveyard(
    request: Request,
    account: Account = Depends(get_current_account),
) -> list[GraveyardEntry]:
    registry: CampaignRegistry = get_campaign_registry(request)
    ended = registry.list_ended_for_account(account.account_id)
    return [
        GraveyardEntry(
            campaign_id=c.campaign_id,
            status="ended",
            name=c.name,
            created_at=c.created_at,
            ended_at=c.ended_at,
            ended_reason=c.ended_reason,
        )
        for c in ended
    ]
