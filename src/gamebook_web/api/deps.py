from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from gamebook_web.sessions.campaign import CampaignRegistry, CampaignState


def get_active_campaign(account_id: str, registry: CampaignRegistry) -> CampaignState:
    state = registry.get_active_for_account(account_id)
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


def assert_not_ended(state: CampaignState) -> None:
    if state.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "run_ended", "message": "This campaign has already ended"}},
        )


def count_new_combat_events(events: Any, before_count: int) -> int:
    if not isinstance(events, list) or len(events) <= before_count:
        return 0
    new = events[before_count:]
    return sum(
        1
        for e in new
        if isinstance(e, dict) and str(e.get("type", "")).startswith("combat")
    )
