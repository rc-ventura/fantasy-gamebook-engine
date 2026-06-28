"""Combat endpoints (FR-005) — explicit stepwise combat control.

Routes:
  POST /campaigns/{id}/combat/round  — resolve one round (optional luck test)
  POST /campaigns/{id}/combat/flee   — attempt to flee the combat

Context (CONTRACTS.md §9):
  Combat is normally driven inside a turn by the narrator's combat subagent.
  These routes exist for explicit/stepwise control (e.g. from the SPA or
  external API clients that want fine-grained round control).

  The active ``combat_id`` is stored in ``CampaignState.current_combat_id``
  (set when a ``start_combat`` effect is applied in a turn; cleared after
  ``end_combat``).

All numbers are engine-authoritative: the MCP ``resolve_combat_round`` tool
computes attack strengths, damage, and luck outcomes.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from pydantic_ai.mcp import MCPToolset

from gamebook_web.api.limiter import COMBAT_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, get_campaign_registry

from gamebook_web.api.play import _campaign_or_404, _assert_not_ended

logger = logging.getLogger(__name__)

router = APIRouter(tags=["combat"])

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CombatRoundRequest(BaseModel):
    test_luck: bool = False          # whether to test luck this round


class CombatRoundResponse(BaseModel):
    outcome: dict[str, Any]          # RoundOutcome from the engine
    final_result: dict[str, Any] | None = None   # FinalResult if combat ended
    character: dict[str, Any] | None = None
    campaign_ended: bool = False     # True if hero died


class FleeCombatResponse(BaseModel):
    result: dict[str, Any]           # FleeResult from the engine
    character: dict[str, Any] | None = None
    campaign_ended: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _active_combat_or_409(registry: CampaignRegistry, campaign_id: str) -> str:
    state = registry.get(campaign_id)
    combat_id = state.current_combat_id if state else None
    if not combat_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "no_active_combat",
                    "message": "No active combat for this campaign",
                }
            },
        )
    return combat_id


async def _read_character(toolset: MCPToolset) -> dict[str, Any] | None:
    try:
        return await call_engine(toolset, "read_character_sheet")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/combat/round")
@limiter.limit(COMBAT_RATE)
async def combat_round(
    campaign_id: str,
    body: CombatRoundRequest | None = None,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> CombatRoundResponse:
    """Resolve one combat round.

    The engine computes attack strengths, hits, damage, and optional luck
    modifier — all numbers are engine-authoritative (SC-002, FR-005).

    If the round ends combat (``outcome.ended == True``), automatically calls
    ``end_combat`` and (if the hero died) ``archive_character``.
    """
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    _assert_not_ended(state)

    combat_id = _active_combat_or_409(registry, campaign_id)
    toolset: MCPToolset = get_engine_toolset(request)
    test_luck = (body.test_luck if body else False) or False

    # Resolve the round via MCP
    outcome: dict[str, Any] = await call_engine(
        toolset,
        "resolve_combat_round",
        combat_id=combat_id,
        use_luck=test_luck,
    )

    character = await _read_character(toolset)
    final_result = None
    campaign_ended = False

    if outcome.get("ended"):
        # Combat over — finalise
        final_result = await call_engine(toolset, "end_combat", combat_id=combat_id)
        registry.set_combat(campaign_id, None)

        character = await _read_character(toolset)

        # Hero died?
        if (
            final_result.get("winner") == "enemy"
            or (character and not character.get("alive", True))
        ):
            try:
                await call_engine(toolset, "archive_character", destination="graveyard")
            except Exception as exc:
                logger.warning("archive_character failed after combat: %s", exc)
            registry.set_ended(campaign_id)
            campaign_ended = True
            character = await _read_character(toolset)

    return CombatRoundResponse(
        outcome=outcome,
        final_result=final_result,
        character=character,
        campaign_ended=campaign_ended,
    )


@router.post("/campaigns/{campaign_id}/combat/flee")
@limiter.limit(COMBAT_RATE)
async def flee_combat(
    campaign_id: str,
    request: Request = None,
    account: Account = Depends(get_current_account),
) -> FleeCombatResponse:
    """Attempt to flee the active combat.

    Costs 2 stamina (engine-computed).  Only allowed if ``flee_allowed`` on
    the active combat.  If the flee damage kills the hero, archives and ends
    the campaign.
    """
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _campaign_or_404(registry, campaign_id, account)
    _assert_not_ended(state)

    combat_id = _active_combat_or_409(registry, campaign_id)
    toolset: MCPToolset = get_engine_toolset(request)

    flee_result: dict[str, Any] = await call_engine(
        toolset, "flee_combat", combat_id=combat_id
    )
    registry.set_combat(campaign_id, None)

    character = await _read_character(toolset)
    campaign_ended = False

    if not flee_result.get("hero_alive", True):
        # Fatal flee
        try:
            await call_engine(toolset, "archive_character", destination="graveyard")
        except Exception as exc:
            logger.warning("archive_character failed after fatal flee: %s", exc)
        registry.set_ended(campaign_id)
        campaign_ended = True
        character = await _read_character(toolset)

    return FleeCombatResponse(
        result=flee_result,
        character=character,
        campaign_ended=campaign_ended,
    )
