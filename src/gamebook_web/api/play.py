"""Play loop endpoints (FR-001/003/004/006/008).

Routes:
  POST   /campaigns                  — create a new campaign
  GET    /campaigns                  — list caller's campaigns
  GET    /campaigns/{id}             — full campaign state (resume point, FR-003)
  DELETE /campaigns/{id}             — delete a campaign
  POST   /campaigns/{id}/character   — create the hero (engine rolls stats via MCP)
  GET    /campaigns/{id}/character   — read character sheet (real engine state)
  POST   /campaigns/{id}/turn        — take a turn (narrator calls MCP tools, returns Scene)
  GET    /campaigns/{id}/scene       — re-fetch the current scene (resume/refresh)
  POST   /campaigns/{id}/save        — checkpoint progress

The narrator calls MCP tools directly during narrate() — all state changes
happen inside the narrator's agent.run() call (ADR-029, Principle I).
The API re-reads state after the turn to reflect updates before responding.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from pydantic_ai.mcp import MCPToolset

from gamebook_web.api.limiter import TURN_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.harness.base import NarratorBackend, NarratorContext, get_narrator
from gamebook_web.harness.scene import Scene
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, get_campaign_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["play"])

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CreateCampaignRequest(BaseModel):
    name: str | None = None     # optional adventure run name


class CampaignResponse(BaseModel):
    campaign_id: str
    status: str
    name: str | None = None


class CreateCharacterRequest(BaseModel):
    name: str = "Hero"          # hero name


class TurnRequest(BaseModel):
    # max_length caps adversarial payload size before it reaches the narrator LLM.
    choice: str | int | None = Field(default=None, max_length=500)


class TurnResponse(BaseModel):
    scene: dict[str, Any]            # validated Scene as dict
    status: str                      # campaign status after the turn (active | ended)
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None


class SaveResponse(BaseModel):
    ok: bool
    slot: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _campaign_or_404(registry: CampaignRegistry, campaign_id: str, account: Account) -> Any:
    state = registry.get(campaign_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": f"Campaign {campaign_id!r} not found"}},
        )
    if state.account_id != account.account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "forbidden", "message": "Campaign not owned by caller"}},
        )
    return state


def _assert_not_ended(state: Any) -> None:
    if state.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "run_ended", "message": "This campaign has already ended"}},
        )


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CreateCampaignRequest | None = None,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> CampaignResponse:
    """Start a new campaign. Returns campaign_id for all subsequent calls."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = registry.create(account.account_id)

    # Persist the campaign row with its owning account_id when a database is
    # configured.  This must happen before any engine-side bootstrap so that
    # ownership checks (e.g. the session-lease guard) resolve correctly; the
    # engine's own campaign upsert uses ON CONFLICT (id) DO NOTHING and will
    # not overwrite the account_id we set here.
    import os

    if os.getenv("DATABASE_URL"):
        from gamebook_web.accounts import get_account_repository

        repo = get_account_repository()
        await repo.create_campaign(account.account_id, state.campaign_id)

    return CampaignResponse(campaign_id=state.campaign_id, status=state.status)


@router.get("/campaigns")
async def list_campaigns(
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> list[CampaignResponse]:
    """List all campaigns belonging to the caller."""
    registry: CampaignRegistry = get_campaign_registry(request)
    campaigns = registry.list_for_account(account.account_id)
    return [CampaignResponse(campaign_id=c.campaign_id, status=c.status) for c in campaigns]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Full campaign state — character sheet + world + summary + events.

    This is the session-opening read (FR-003): load real engine state before
    narrating so the narrator can resume from the exact recorded point.
    """
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    toolset: MCPToolset = get_engine_toolset(request)

    character = None
    try:
        character = await call_engine(toolset, "read_character_sheet")
    except Exception:
        pass  # no character yet

    world = await call_engine(toolset, "read_world")
    summary = await call_engine(toolset, "read_summary")
    events = await call_engine(toolset, "read_events")

    return {
        "campaign_id": campaign_id,
        "status": state.status,
        "character": character,
        "world": world,
        "summary": summary,
        "events": events,
        "current_scene": state.current_scene,
    }


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> None:
    """Delete a campaign and its data."""
    registry: CampaignRegistry = get_campaign_registry(request)
    _campaign_or_404(registry, campaign_id, account)
    registry.delete(campaign_id)


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/character", status_code=status.HTTP_201_CREATED)
async def create_character(
    campaign_id: str,
    body: CreateCharacterRequest | None = None,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Create the hero — attributes rolled by the engine via MCP (FR-001).

    The engine rolls skill = 1d6+6, stamina = 2d6+12, luck = 1d6+6.
    No client-supplied stat values are accepted (CONTRACTS.md §6).
    """
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    _assert_not_ended(state)

    toolset: MCPToolset = get_engine_toolset(request)
    name = (body.name if body else None) or "Hero"

    try:
        character = await call_engine(toolset, "create_character", name=name)
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


@router.get("/campaigns/{campaign_id}/character")
async def read_character(
    campaign_id: str,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Read the character sheet — real engine state (FR-021)."""
    registry: CampaignRegistry = get_campaign_registry(request)
    _campaign_or_404(registry, campaign_id, account)
    toolset: MCPToolset = get_engine_toolset(request)

    character = await call_engine(toolset, "read_character_sheet")
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "No character created yet"}},
        )
    return character


# ---------------------------------------------------------------------------
# Play loop
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/turn")
@limiter.limit(TURN_RATE)
async def take_turn(
    campaign_id: str,
    body: TurnRequest | None = None,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> TurnResponse:
    """Take a turn: narrator calls MCP tools and returns a validated Scene.

    Flow (CONTRACTS.md §10, ADR-029):
    1. Read engine state (character, world, summary, events).
    2. Call narrator → Scene (narrator calls MCP tools during generation;
       all state changes happen inside narrator.narrate()).
    3. Structural validation (non-empty narrative — belt-and-suspenders).
    4. Re-read state (narrator may have updated character/world via tool calls).
    5. Check terminal conditions (death / victory).
    6. Store scene and return TurnResponse.
    """
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    _assert_not_ended(state)

    toolset: MCPToolset = get_engine_toolset(request)
    narrator: NarratorBackend = get_narrator(request)
    choice = (body.choice if body else None)

    # 1. Read engine state (session-opening read per FR-003)
    character = None
    try:
        character = await call_engine(toolset, "read_character_sheet")
    except Exception:
        pass

    world = await call_engine(toolset, "read_world")
    summary = await call_engine(toolset, "read_summary")
    events = await call_engine(toolset, "read_events")
    recent_events = events[-10:] if events else []

    ctx = NarratorContext(
        character=character,
        world=world,
        summary=summary,
        recent_events=recent_events,
        choice=choice,
    )

    # 2. Narrator → Scene (narrator calls MCP tools during generation)
    try:
        scene: Scene = await narrator.narrate(campaign_id, ctx)
    except Exception as exc:
        logger.exception("Narrator failed for campaign %s", campaign_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "invalid_scene", "message": "Narrator failed to produce a valid scene"}},
        ) from exc

    # 3. Structural validation (belt-and-suspenders; Scene model validates on construction)
    if not scene.narrative.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "invalid_scene", "message": "Scene narrative is empty"}},
        )

    # 4. Re-read state (narrator may have called tools that changed character/world)
    try:
        character = await call_engine(toolset, "read_character_sheet")
    except Exception:
        pass
    try:
        world = await call_engine(toolset, "read_world")
    except Exception:
        pass

    # 5. Check terminal conditions against the post-turn state
    await _check_terminal_state(campaign_id, character, world, toolset, registry)

    # 6. Store scene and return (status reflects any end-state set in step 5)
    scene_dict = scene.model_dump()
    registry.set_scene(campaign_id, scene_dict)

    return TurnResponse(
        scene=scene_dict,
        status=state.status,
        character=character,
        world=world,
    )


async def _check_terminal_state(
    campaign_id: str,
    character: dict | None,
    world: dict | None,
    toolset: MCPToolset,
    registry: CampaignRegistry,
) -> None:
    """Archive and end campaign if hero is dead or victory condition is met."""
    if character and not character.get("alive", True):
        try:
            await call_engine(toolset, "archive_character", destination="graveyard")
        except Exception as exc:
            logger.warning("archive_character failed: %s", exc)
        registry.set_ended(campaign_id)
        return

    if world:
        flags: dict = world.get("flags", {})
        if flags.get("malachar_defeated"):
            try:
                await call_engine(toolset, "archive_character", destination="hall_of_fame")
            except Exception as exc:
                logger.warning("archive_character (victory) failed: %s", exc)
            registry.set_ended(campaign_id)


@router.get("/campaigns/{campaign_id}/scene")
async def get_scene(
    campaign_id: str,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Re-fetch the current scene (resume/refresh).  Returns null if no turn yet."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    return {"scene": state.current_scene}


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/save")
async def save_campaign(
    campaign_id: str,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> SaveResponse:
    """Checkpoint progress (durable, atomic — Principle V)."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    _assert_not_ended(state)
    toolset: MCPToolset = get_engine_toolset(request)

    result = await call_engine(toolset, "save_progress", slot=None)
    return SaveResponse(ok=True, slot=result.get("slot") if isinstance(result, dict) else None)
