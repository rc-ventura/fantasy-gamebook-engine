from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic_ai.mcp import MCPToolset

from gamebook_web.adventure_module import get_adventure_config
from gamebook_web.api.limiter import TURN_RATE, limiter
from gamebook_web.api.deps import assert_not_ended, count_new_combat_events, get_active_campaign
from gamebook_web.api.schemas import TurnRequest, TurnResponse
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.harness.narrator import (
    NarratorBackend,
    NarratorContext,
    StreamingNarratorBackend,
    get_narrator,
)
from gamebook_web.harness.scene import Scene
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, CampaignState, get_campaign_registry
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
    """Take a turn: narrator calls MCP tools and returns a validated Scene.

    Flow (CONTRACTS.md §10, ADR-029):
    1. Read engine state (character, world, summary, events).
    2. Call narrator → Scene.
    3. Structural validation (non-empty narrative — belt-and-suspenders).
    4. Re-read state (narrator may have updated character/world via tool calls).
    5. Check terminal conditions (death / victory).
    6. Store scene and return TurnResponse.
    """
    from gamebook_web.observability.tracing import get_metrics, turn_span

    registry: CampaignRegistry = get_campaign_registry(request)
    state = await get_active_campaign(account.account_id, registry)
    assert_not_ended(state)

    campaign_id = state.campaign_id
    toolset: MCPToolset = get_engine_toolset(request)
    narrator: NarratorBackend = get_narrator(request)
    choice = (body.choice if body else None)

    metrics = get_metrics()
    started = time.perf_counter()

    # T046 (FR-030): wrap the whole turn in a span (campaign_id/account_id only,
    # no PII); turn_span marks ERROR on exception.
    with turn_span(campaign_id, account.account_id) as span:
        # M-QA-1: record turn_duration in a finally so narrator-failure latency
        # is captured too — the histogram must not have a blind spot for exactly
        # the failure cases where latency matters most.
        try:
            ctx, events_before = await _read_turn_context(toolset, campaign_id, state, choice)
            if isinstance(ctx.world, dict) and ctx.world.get("turn") is not None:
                span.set_attribute("turn_number", ctx.world["turn"])

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

            response = await _finalize_turn(
                campaign_id, scene, toolset, registry, state,
                pre_narrator_character=ctx.character,
                events_before=events_before,
                metrics=metrics,
            )
        finally:
            # Metrics must not break a turn (ADR-024) — wrap in try/except so
            # a metrics backend failure doesn't mask the original exception.
            try:
                metrics.turn_duration.record(
                    time.perf_counter() - started, attributes={"campaign_id": campaign_id}
                )
            except Exception:  # pragma: no cover — metrics must never break a turn
                logger.warning("turn_duration metric failed for campaign %s", campaign_id, exc_info=True)
    return response


@router.post("/me/game/turn/stream")
@limiter.limit(TURN_RATE)
async def take_turn_stream(
    request: Request,
    body: TurnRequest | None = None,
    account: Account = Depends(get_current_account),
    _lease: None = Depends(require_lease),
) -> StreamingResponse:
    """SSE variant of ``POST /me/game/turn`` (issue #20).

    Streams the narrator's narrative text as it's generated (``event: delta``,
    ``data: {"text": "..."}``), then a final ``event: done`` carrying the exact
    same JSON body ``POST /me/game/turn`` returns — same pre/post-narration
    engine work (``_read_turn_context``/``_finalize_turn``), same terminal-state
    handling, same metrics. Choices only ever arrive via the ``done`` event,
    never a partial one — the frontend renders growing prose during ``delta``
    events and swaps in the full authoritative state on ``done``.

    Graceful degradation, by design (not a special case per narrator type):
    - A narrator without streaming support (``StreamingNarratorBackend``) still
      produces a valid stream — one ``delta`` with the whole narrative, then
      ``done`` — via ``narrate()``, so this endpoint works for every configured
      narrator.
    - Any failure (narrator error, empty-narrative validation, an unhandled
      exception) emits ``event: error`` with the standard
      ``{"error": {"code", "message"}}`` envelope rather than an unhandled 500
      — the HTTP status is already committed as 200 once SSE headers are sent,
      so errors must travel inside the stream. The frontend falls back to
      ``POST /me/game/turn`` on an ``error`` event or a stream that ends
      without ``done``.
    """
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

    async def _events() -> AsyncIterator[bytes]:
        with turn_span(campaign_id, account.account_id) as span:
            try:
                ctx, events_before = await _read_turn_context(toolset, campaign_id, state, choice)
                if isinstance(ctx.world, dict) and ctx.world.get("turn") is not None:
                    span.set_attribute("turn_number", ctx.world["turn"])

                scene: Scene | None = None
                if isinstance(narrator, StreamingNarratorBackend):
                    async for event in narrator.narrate_stream(campaign_id, ctx):
                        if isinstance(event, Scene):
                            scene = event
                        else:
                            yield _sse_event("delta", {"text": event})
                else:
                    scene = await narrator.narrate(campaign_id, ctx)

                if scene is None:
                    raise RuntimeError(f"narrator produced no output for campaign {campaign_id}")

                response = await _finalize_turn(
                    campaign_id, scene, toolset, registry, state,
                    pre_narrator_character=ctx.character,
                    events_before=events_before,
                    metrics=metrics,
                )
                yield _sse_event("done", response.model_dump())
            except HTTPException as exc:
                logger.error("Streaming turn failed (HTTP %s) for campaign %s", exc.status_code, campaign_id)
                detail = exc.detail if isinstance(exc.detail, dict) else {
                    "error": {"code": "http_error", "message": str(exc.detail)}
                }
                yield _sse_event("error", detail)
            except Exception as exc:
                logger.error(
                    "Streaming turn failed for campaign %s: %s: %s",
                    campaign_id, type(exc).__name__, exc, exc_info=True,
                )
                yield _sse_event(
                    "error",
                    {"error": {"code": "stream_failed", "message": "Narrator failed to produce a valid scene"}},
                )
            finally:
                try:
                    metrics.turn_duration.record(
                        time.perf_counter() - started, attributes={"campaign_id": campaign_id}
                    )
                except Exception:  # pragma: no cover — metrics must never break a turn
                    logger.warning("turn_duration metric failed for campaign %s", campaign_id, exc_info=True)

    return StreamingResponse(_events(), media_type="text/event-stream")


def _sse_event(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


# ---------------------------------------------------------------------------
# Shared pre/post-narration logic (take_turn and take_turn_stream)
# ---------------------------------------------------------------------------

async def _read_turn_context(
    toolset: MCPToolset,
    campaign_id: str,
    state: CampaignState,
    choice: str | int | None,
) -> tuple[NarratorContext, int]:
    """Session-opening read (FR-003) + choice-label recovery.

    Returns ``(context, events_before)`` — ``events_before`` is the event
    count prior to narration, used to detect combat rounds resolved this turn.
    """
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

    # Recover the full label of the selected choice from the previous scene.
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
    return ctx, events_before


async def _finalize_turn(
    campaign_id: str,
    scene: Scene,
    toolset: MCPToolset,
    registry: CampaignRegistry,
    state: CampaignState,
    *,
    pre_narrator_character: dict | None,
    events_before: int,
    metrics: Any,
) -> TurnResponse:
    """Structural validation, post-narration re-read, terminal check, response build."""
    if not scene.narrative.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "invalid_scene", "message": "Scene narrative is empty"}},
        )

    character_reread_failed = False
    character = None
    try:
        character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
    except Exception:
        character_reread_failed = True
    world = None
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
        pre_narrator_character=pre_narrator_character,
    )

    scene_dict = scene.model_dump()
    registry.set_scene(campaign_id, scene_dict)

    return TurnResponse(
        scene=scene_dict,
        status=state.status,
        character=character,
        world=world,
    )


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
    """Archive and end campaign if hero is dead or victory condition is met.

    M-QA-2: if the post-turn ``read_character_sheet`` re-read failed
    (``re_read_failed=True``), ``character`` is stale/None.  In that case fall
    back to ``pre_narrator_character`` — the state read *before* the narrator
    ran.  This is conservative: if the pre-narrator character was alive, we
    can't confirm death, so we skip the death check (the campaign stays
    active and the next turn will re-check).  But if the pre-narrator
    character was *already* dead, we still archive.  The important fix is
    that a re-read failure no longer causes us to silently skip a death that
    the narrator caused: if ``pre_narrator_character`` was alive and
    ``character`` is None due to re-read failure, we retry the read once
    before giving up.
    """
    from gamebook_web.observability.tracing import get_metrics

    # M-QA-2: if the re-read failed, retry once before falling back.
    effective_character = character
    if effective_character is None and re_read_failed:
        try:
            effective_character = await call_engine(
                toolset, "read_character_sheet", campaign_id=campaign_id
            )
        except Exception:
            # Final fallback: use the pre-narrator snapshot.  If that was
            # alive, we can't confirm a narrator-caused death — leave the
            # campaign active and let the next turn re-check.
            effective_character = pre_narrator_character

    if effective_character and not effective_character.get("alive", True):
        try:
            await call_engine(toolset, "archive_character", campaign_id=campaign_id, destination="graveyard")
        except Exception as exc:
            logger.warning("archive_character failed: %s", exc)
        await registry.set_ended(campaign_id, reason="death")
        get_metrics().active_campaigns.add(-1)
        return

    if world:
        flags: dict = world.get("flags", {})
        if flags.get(get_adventure_config().victory_flag):
            try:
                await call_engine(toolset, "archive_character", campaign_id=campaign_id, destination="hall_of_fame")
            except Exception as exc:
                logger.warning("archive_character (victory) failed: %s", exc)
            await registry.set_ended(campaign_id, reason="victory")
            get_metrics().active_campaigns.add(-1)
