"""Play loop endpoints (D1 backend-scoped routes, ADR-017/ADR-029).

Routes:
  POST   /me/game                    — create a new game
  GET    /me/game                    — full game state (resume point, FR-003)
  DELETE /me/game                    — abandon current game
  POST   /me/game/character          — create the hero (engine rolls stats via MCP)
  GET    /me/game/character          — read character sheet (real engine state)
  POST   /me/game/turn               — take a turn (narrator calls MCP tools, returns Scene)
  GET    /me/game/scene              — re-fetch the current scene (resume/refresh)
  POST   /me/game/save               — checkpoint progress

  GET    /me/graveyard               — list all ended campaigns (death + victory)

The frontend never sees or manages a campaign_id. The backend resolves
`campaign_id` from `account → active campaign` for every route (D1).
The narrator calls MCP tools directly during narrate() — all state changes
happen inside the narrator's agent.run() call (ADR-029, Principle I).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from pydantic_ai.mcp import MCPToolset

from gamebook_web.adventure_module import get_adventure_config
from gamebook_web.api.limiter import TURN_RATE, limiter
from gamebook_web.auth.dev_auth import Account, get_current_account
from gamebook_web.harness.base import NarratorBackend, NarratorContext, get_narrator
from gamebook_web.harness.scene import Scene
from gamebook_web.mcp_host import call_engine, get_engine_toolset
from gamebook_web.sessions.campaign import CampaignRegistry, CampaignState, get_campaign_registry
from gamebook_web.sessions.lease import require_lease

logger = logging.getLogger(__name__)

router = APIRouter(tags=["play"])

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

def _strip_control_chars(value: str | None) -> str | None:
    """M-02 (A03): strip control characters (except common whitespace) from
    user-supplied name fields to prevent log injection and header splitting.

    Removes C0 control chars (0x00–0x1F) and DEL (0x7F), which include
    newlines (\\r, \\n), tabs (\\t), null bytes, and other non-printable
    characters.  Regular spaces (0x20) are preserved.
    """
    if value is None:
        return None
    return "".join(c for c in value if c == " " or (ord(c) > 0x20 and ord(c) != 0x7F))


class CreateGameRequest(BaseModel):
    # M-02 (A03): cap name length to prevent DoS / log injection; strip
    # control characters that enable log-injection / header-splitting.
    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str | None) -> str | None:
        return _strip_control_chars(v)


class GameResponse(BaseModel):
    status: str
    campaign_id: str            # returned for reference / debugging; SPA does not store it
    name: str | None = None     # optional run name (FR-006)


class CreateCharacterRequest(BaseModel):
    # M-02 (A03): same max_length + control-character guard as CreateGameRequest.
    name: str = Field(default="Hero", max_length=100)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        return _strip_control_chars(v) or "Hero"


class TurnRequest(BaseModel):
    # max_length caps adversarial payload size before it reaches the narrator LLM.
    choice: str | int | None = Field(default=None, max_length=500)


class TurnResponse(BaseModel):
    scene: dict[str, Any]
    status: str                       # campaign status after the turn (active | ended)
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None


class SaveResponse(BaseModel):
    ok: bool
    slot: str | None


class GraveyardEntry(BaseModel):
    campaign_id: str
    status: str = "ended"
    name: str | None = None
    created_at: str | None = None
    ended_at: str | None = None
    ended_reason: str | None = None   # "death" | "victory"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_campaign(account: Account, registry: CampaignRegistry) -> CampaignState:
    """Return the caller's single active campaign, or raise 404 with a structured code.

    The 404 code ``no_active_campaign`` is intercepted by the SPA to route the
    player to the start screen (where they POST /me/game to begin a new run).
    """
    state = registry.get_active_for_account(account.account_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "no_active_campaign",
                    "message": "No active game found for this account.",
                    "hint": "POST /me/game to start a new game",
                }
            },
        )
    return state


def _count_new_combat_events(events: Any, before_count: int) -> int:
    """Count combat-typed events appended since ``before_count`` (T048).

    Combat resolves inside the narrator's tool loop (ADR-029); newly-added
    events whose ``type`` starts with ``combat`` approximate the rounds resolved
    this turn.  Returns 0 if events are unavailable — never fabricates a count.
    """
    if not isinstance(events, list) or len(events) <= before_count:
        return 0
    new = events[before_count:]
    return sum(
        1
        for e in new
        if isinstance(e, dict) and str(e.get("type", "")).startswith("combat")
    )


def _assert_not_ended(state: CampaignState) -> None:
    if state.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "run_ended", "message": "This campaign has already ended"}},
        )


# ---------------------------------------------------------------------------
# Game (one active game per account)
# ---------------------------------------------------------------------------

@router.post("/me/game", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_lease)])
async def create_game(
    request: Request,
    body: CreateGameRequest | None = None,
    account: Account = Depends(get_current_account),
) -> GameResponse:
    """Start a new game. Returns status + campaign_id (for debugging; SPA ignores campaign_id)."""
    from gamebook_web.observability.tracing import get_metrics

    registry: CampaignRegistry = get_campaign_registry(request)
    # One active campaign per account — end any existing one first.
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
    """Full game state — character sheet + world + summary + events + current scene.

    Session-opening read (FR-003): call this before narrating so the narrator
    resumes from the exact recorded point. Returns 404 with ``no_active_campaign``
    if no game is active.
    """
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
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
    """Abandon the current game (marks ended, without archiving)."""
    from gamebook_web.observability.tracing import get_metrics

    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
    was_active = state.status != "ended"
    registry.set_ended(state.campaign_id)
    if was_active:
        get_metrics().active_campaigns.add(-1)


# ---------------------------------------------------------------------------
# Character
# ---------------------------------------------------------------------------

@router.post("/me/game/character", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_lease)])
async def create_character(
    request: Request,
    body: CreateCharacterRequest | None = None,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Create the hero — attributes rolled by the engine via MCP (FR-001)."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
    _assert_not_ended(state)

    toolset: MCPToolset = get_engine_toolset(request)
    campaign_id = state.campaign_id
    name = (body.name if body else None) or "Hero"

    try:
        character = await call_engine(toolset, "create_character", campaign_id=campaign_id, name=name)
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
    """Read the character sheet — real engine state (FR-021)."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
    toolset: MCPToolset = get_engine_toolset(request)
    campaign_id = state.campaign_id

    character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
    if character is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "No character created yet"}},
        )
    return character


# ---------------------------------------------------------------------------
# Play loop
# ---------------------------------------------------------------------------

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
    2. Call narrator → Scene (narrator calls MCP tools during generation;
       all state changes happen inside narrator.narrate()).
    3. Structural validation (non-empty narrative — belt-and-suspenders).
    4. Re-read state (narrator may have updated character/world via tool calls).
    5. Check terminal conditions (death / victory).
    6. Store scene and return TurnResponse.
    """
    import time

    from gamebook_web.observability.tracing import get_metrics, turn_span

    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
    _assert_not_ended(state)

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
            # 1. Read engine state (session-opening read per FR-003)
            character = None
            try:
                character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
            except Exception:
                pass

            world = await call_engine(toolset, "read_world", campaign_id=campaign_id)
            summary = await call_engine(toolset, "read_summary", campaign_id=campaign_id)
            events = await call_engine(toolset, "read_events", campaign_id=campaign_id)
            recent_events = events[-10:] if events else []
            events_before = len(events) if events else 0
            if isinstance(world, dict) and world.get("turn") is not None:
                span.set_attribute("turn_number", world["turn"])

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
                # Type only, no traceback (ADR-024, FR-031): a narrator exception can
                # carry the player's raw choice text; keep it out of the server log.
                logger.error("Narrator failed for campaign %s: %s", campaign_id, type(exc).__name__)
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
            # M-QA-2: track re-read failures explicitly — if the narrator killed the
            # hero via a tool call but the re-read throws, we must still check for
            # death using the pre-narrator state as a fallback.
            character_reread_failed = False
            try:
                character = await call_engine(toolset, "read_character_sheet", campaign_id=campaign_id)
            except Exception:
                character_reread_failed = True
            try:
                world = await call_engine(toolset, "read_world", campaign_id=campaign_id)
            except Exception:
                pass

            # combat_rounds_total (FR-030): combat resolves inside the narrator tool
            # loop (ADR-029), so count the combat-typed events it registered this turn.
            try:
                post_events = await call_engine(toolset, "read_events", campaign_id=campaign_id)
                rounds = _count_new_combat_events(post_events, events_before)
                if rounds:
                    metrics.combat_rounds_total.add(rounds, attributes={"campaign_id": campaign_id})
            except Exception:  # pragma: no cover — metrics must not break a turn
                pass

            # 5. Check terminal conditions against the post-turn state
            await _check_terminal_state(
                campaign_id, character, world, toolset, registry,
                re_read_failed=character_reread_failed,
                pre_narrator_character=ctx.character,
            )

            # 6. Store scene and return (status reflects any end-state set in step 5)
            scene_dict = scene.model_dump()
            registry.set_scene(campaign_id, scene_dict)

            response = TurnResponse(
                scene=scene_dict,
                status=state.status,
                character=character,
                world=world,
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


async def _check_terminal_state(
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


@router.get("/me/game/scene")
async def get_scene(
    request: Request,
    account: Account = Depends(get_current_account),
) -> dict[str, Any]:
    """Re-fetch the current scene (resume/refresh). Returns null if no turn yet."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
    return {"scene": state.current_scene}


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

@router.post("/me/game/save", dependencies=[Depends(require_lease)])
async def save_game(
    request: Request,
    account: Account = Depends(get_current_account),
) -> SaveResponse:
    """Checkpoint progress (durable, atomic — Principle V)."""
    registry: CampaignRegistry = get_campaign_registry(request)
    state = _get_active_campaign(account, registry)
    _assert_not_ended(state)
    toolset: MCPToolset = get_engine_toolset(request)
    campaign_id = state.campaign_id

    result = await call_engine(toolset, "save_progress", campaign_id=campaign_id, slot=None)
    return SaveResponse(ok=True, slot=result.get("slot") if isinstance(result, dict) else None)


# ---------------------------------------------------------------------------
# Graveyard (ended campaigns)
# ---------------------------------------------------------------------------

@router.get("/me/graveyard")
async def get_graveyard(
    request: Request,
    account: Account = Depends(get_current_account),
) -> list[GraveyardEntry]:
    """List all ended campaigns (death + victory) for the caller's account."""
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
