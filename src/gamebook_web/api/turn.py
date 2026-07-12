from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic_ai.mcp import MCPToolset

from gamebook_web.adventure_module import get_adventure_config
from gamebook_web.api.limiter import TURN_RATE, limiter
from gamebook_web.api.deps import assert_not_ended, count_new_combat_events, get_active_campaign
from gamebook_web.api.schemas import TurnRequest, TurnResponse
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.harness.narrator import NarratorBackend, NarratorContext, get_narrator
from gamebook_web.harness.scene import Scene
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, get_campaign_registry
from gamebook_web.sessions.lease import require_lease

logger = logging.getLogger(__name__)

router = APIRouter(tags=["turn"])


@router.post("/me/game/turn")
@limiter.limit(TURN_RATE)
async def take_turn(
    request: Request,
    body: TurnRequest | None = None,
    account: Account = Depends(get_current_account),
    _lease: None = Depends(require_lease),
) -> TurnResponse:
    from gamebook_web.observability.tracing import get_metrics, turn_span

    registry: CampaignRegistry = get_campaign_registry(request)
    state = get_active_campaign(account.account_id, registry)
    assert_not_ended(state)

    campaign_id = state.campaign_id
    toolset: MCPToolset = get_engine_toolset(request)
    narrator: NarratorBackend = get_narrator(request)
    choice = (body.choice if body else None)

    metrics = get_metrics()
    started = time.perf_counter()

    with turn_span(campaign_id, account.account_id) as span:
        try:
            character = None
            try:
                character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
            except Exception as exc:
                logger.debug("read_character_sheet skipped (character may not exist yet): %s", exc)

            world = await call_engine(toolset, "read_world", campaign_id=campaign_id)
            summary = await call_engine(toolset, "read_summary", campaign_id=campaign_id)
            events = await call_engine(toolset, "read_events", campaign_id=campaign_id)
            recent_events = events[-10:] if events else []
            events_before = len(events) if events else 0
            if isinstance(world, dict) and world.get("turn") is not None:
                span.set_attribute("turn_number", world["turn"])

            # Recover the full label of the selected choice from the previous
            choice_label: str | None = None
            if choice is not None:
                prev = state.current_scene
                if prev:
                    for c in prev.get("choices", []):
                        if str(c.get("id")) == str(choice):
                            choice_label = c.get("label")
                            break

            ctx = NarratorContext(
                character=character,
                world=world,
                summary=summary,
                recent_events=recent_events,
                choice=choice,
                choice_label=choice_label,
            )

            try:
                scene: Scene = await narrator.narrate(campaign_id, ctx)
            except Exception as exc:
                logger.error(
                    "Narrator failed for campaign %s: %s: %s",
                    campaign_id, type(exc).__name__, exc,
                )
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": {"code": "invalid_scene", "message": "Narrator failed to produce a valid scene"}},
                ) from exc

            if not scene.narrative.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"error": {"code": "invalid_scene", "message": "Scene narrative is empty"}},
                )

            character_reread_failed = False
            try:
                character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
            except Exception:
                character_reread_failed = True
            try:
                world = await call_engine(toolset, "read_world", campaign_id=campaign_id)
            except Exception as exc:
                logger.warning("read_world (post-narration re-read) failed for %s: %s", campaign_id, exc)

            try:
                post_events = await call_engine(toolset, "read_events", campaign_id=campaign_id)
                rounds = count_new_combat_events(post_events, events_before)
                if rounds:
                    metrics.combat_rounds_total.add(rounds, attributes={"campaign_id": campaign_id})
            except Exception:  # pragma: no cover — metrics must not break a turn
                pass

            await check_terminal_state(
                campaign_id, character, world, toolset, registry,
                re_read_failed=character_reread_failed,
                pre_narrator_character=ctx.character,
            )

            scene_dict = scene.model_dump()
            registry.set_scene(campaign_id, scene_dict)

            response = TurnResponse(
                scene=scene_dict,
                status=state.status,
                character=character,
                world=world,
            )
        finally:
            try:
                metrics.turn_duration.record(
                    time.perf_counter() - started, attributes={"campaign_id": campaign_id}
                )
            except Exception:  # pragma: no cover — metrics must never break a turn
                logger.warning("turn_duration metric failed for campaign %s", campaign_id, exc_info=True)
    return response


async def check_terminal_state(
    campaign_id: str,
    character: dict | None,
    world: dict | None,
    toolset: MCPToolset,
    registry: CampaignRegistry,
    *,
    re_read_failed: bool = False,
    pre_narrator_character: dict | None = None,
) -> None:
    from gamebook_web.observability.tracing import get_metrics

    effective_character = character
    if effective_character is None and re_read_failed:
        try:
            effective_character = await call_engine(
                toolset, "read_character_sheet", campaign_id=campaign_id
            )
        except Exception:
            effective_character = pre_narrator_character

    if effective_character and not effective_character.get("alive", True):
        try:
            await call_engine(toolset, "archive_character", campaign_id=campaign_id, destination="graveyard")
        except Exception as exc:
            logger.warning("archive_character failed: %s", exc)
        registry.set_ended(campaign_id, reason="death")
        get_metrics().active_campaigns.add(-1)
        return

    if world:
        flags: dict = world.get("flags", {})
        if flags.get(get_adventure_config().victory_flag):
            try:
                await call_engine(toolset, "archive_character", campaign_id=campaign_id, destination="hall_of_fame")
            except Exception as exc:
                logger.warning("archive_character (victory) failed: %s", exc)
            registry.set_ended(campaign_id, reason="victory")
            get_metrics().active_campaigns.add(-1)
