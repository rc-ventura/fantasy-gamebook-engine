"""Play loop endpoints (FR-001/003/004/006/008).

Routes:
  POST   /campaigns                  — create a new campaign
  GET    /campaigns                  — list caller's campaigns
  GET    /campaigns/{id}             — full campaign state (resume point, FR-003)
  DELETE /campaigns/{id}             — delete a campaign
  POST   /campaigns/{id}/character   — create the hero (engine rolls stats via MCP)
  GET    /campaigns/{id}/character   — read character sheet (real engine state)
  POST   /campaigns/{id}/turn        — take a turn (narrator → validated Scene → effects applied)
  GET    /campaigns/{id}/scene       — re-fetch the current scene (resume/refresh)
  POST   /campaigns/{id}/save        — checkpoint progress

All writes go through the engine via ``call_engine()``; the narrator is the
only source of ``Scene`` objects and they are validated before any effect is
applied (FR-007/014).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from pydantic_ai.mcp import MCPToolset

from gamebook_web.api.limiter import TURN_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.harness.base import NarratorBackend, NarratorContext, get_narrator
from gamebook_web.harness.scene import EFFECT_TO_MCP_TOOL, Scene
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
    choice: str | int | None = None   # player choice (index or free text)


class TurnResponse(BaseModel):
    scene: dict[str, Any]            # validated Scene as dict
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None
    effects_applied: list[dict[str, Any]] = []


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


# Effects whose params are forwarded as the ``changes`` arg (matches MCP tool signature).
_CHANGES_WRAPPED: frozenset[str] = frozenset({"update_character", "update_world"})


def _build_tool_args(effect: Any) -> dict[str, Any]:
    """Transform Scene Effect params into MCP tool arguments.

    ``update_character`` and ``update_world`` tools take a single ``changes``
    dict (CONTRACTS.md §6). The Effect contract expresses those as flat params
    ``{ field, delta|set }`` / ``{ location?, flags? }`` — wrap them here.
    """
    if effect.type in _CHANGES_WRAPPED:
        return {"changes": effect.params}
    return dict(effect.params)


async def _apply_scene_effects(
    effects: list[Any],
    toolset: MCPToolset,
    registry: CampaignRegistry,
    campaign_id: str,
) -> list[dict[str, Any]]:
    """Apply ``Scene.effects[]`` through the engine MCP tools.

    Returns a list of ``{type, result}`` dicts with the MCP tool outcomes
    (all numbers are from the engine — never narrator-fabricated, SC-002).
    """
    results: list[dict[str, Any]] = []
    for effect in effects:
        tool_name = EFFECT_TO_MCP_TOOL[effect.type]
        tool_args = _build_tool_args(effect)
        try:
            result = await call_engine(toolset, tool_name, **tool_args)
        except Exception as exc:
            logger.warning("Effect %r failed: %s", effect.type, exc)
            results.append({"type": effect.type, "error": str(exc)})
            continue

        # Track combat state in the campaign registry
        if effect.type == "start_combat" and isinstance(result, dict):
            combat_id = result.get("combat_id")
            if combat_id:
                registry.set_combat(campaign_id, combat_id)

        if effect.type == "end_combat":
            registry.set_combat(campaign_id, None)

        results.append({"type": effect.type, "result": result})

    return results


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
        # Map known errors to a stable code; never forward raw engine messages.
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
    """Take a turn: narrator produces a ``Scene``, effects are applied via MCP.

    Flow (CONTRACTS.md §10):
    1. Read engine state (character, world, summary, events).
    2. Call narrator → ``Scene`` (Pydantic-validated; FR-007).
    3. If the Scene is invalid → 422 (FR-014; never persisted).
    4. Apply ``Scene.effects[]`` through MCP (engine produces all numbers).
    5. Return the Scene + updated state.
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

    # 2. Narrator → Scene (structured output, Pydantic-validated)
    try:
        scene: Scene = await narrator.narrate(campaign_id, ctx)
    except Exception as exc:
        logger.exception("Narrator failed for campaign %s", campaign_id)
        # Do not leak internal exception details (paths, model config) to clients.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "invalid_scene", "message": "Narrator failed to produce a valid scene"}},
        ) from exc

    # 3. Validate (Scene model already validates; this is the belt-and-suspenders check)
    if not scene.narrative.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "invalid_scene", "message": "Scene narrative is empty"}},
        )

    # 4. Apply effects via MCP
    effects_applied = await _apply_scene_effects(
        scene.effects, toolset, registry, campaign_id
    )

    # Refresh state after effects
    try:
        character = await call_engine(toolset, "read_character_sheet")
    except Exception:
        pass
    try:
        world = await call_engine(toolset, "read_world")
    except Exception:
        pass

    # Check for terminal conditions against the refreshed post-effects state
    await _check_terminal_state(campaign_id, character, world, toolset, registry)

    # Store current scene for GET /scene
    scene_dict = scene.model_dump()
    registry.set_scene(campaign_id, scene_dict)

    return TurnResponse(
        scene=scene_dict,
        character=character,
        world=world,
        effects_applied=effects_applied,
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
        # Hero died — archive and end
        try:
            await call_engine(toolset, "archive_character", destination="graveyard")
        except Exception as exc:
            logger.warning("archive_character failed: %s", exc)
        registry.set_ended(campaign_id)
        return

    # Victory condition: check world flags for module victory flag
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
