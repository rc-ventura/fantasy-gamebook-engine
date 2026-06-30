"""Campaign registry — in-memory dev stub (persistence + lease enforcement in 004).

Tracks which campaigns exist, their status (active/ended), and transient
per-campaign state (active combat id, latest scene).  Slice 004 replaces this
with a database-backed store without touching the play loop.

The registry is stored in ``app.state.campaign_registry`` so it is:
  - Isolated per app instance (each TestClient call gets its own registry via
    the lifespan fixture).
  - Accessible from routes via ``Depends(get_campaign_registry)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class CampaignState:
    """Mutable per-campaign state tracked by the API layer."""

    campaign_id: str
    account_id: str
    status: Literal["active", "ended"] = "active"
    current_scene: dict[str, Any] | None = None  # latest narrator Scene (for GET /scene)


class CampaignRegistry:
    """In-memory campaign store (dev stub — 004 makes this durable)."""

    def __init__(self) -> None:
        self._campaigns: dict[str, CampaignState] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, account_id: str, campaign_id: str | None = None) -> CampaignState:
        cid = campaign_id or str(uuid.uuid4())
        state = CampaignState(campaign_id=cid, account_id=account_id)
        self._campaigns[cid] = state
        return state

    def get(self, campaign_id: str) -> CampaignState | None:
        return self._campaigns.get(campaign_id)

    def list_for_account(self, account_id: str) -> list[CampaignState]:
        return [c for c in self._campaigns.values() if c.account_id == account_id]

    def delete(self, campaign_id: str) -> bool:
        return self._campaigns.pop(campaign_id, None) is not None

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    def set_ended(self, campaign_id: str) -> None:
        if s := self._campaigns.get(campaign_id):
            s.status = "ended"

    def set_scene(self, campaign_id: str, scene_dict: dict[str, Any] | None) -> None:
        if s := self._campaigns.get(campaign_id):
            s.current_scene = scene_dict

    def clear(self) -> None:
        """Reset all state (used in tests for isolation)."""
        self._campaigns.clear()


# ---------------------------------------------------------------------------
# FastAPI dependency (override in tests via dependency_overrides)
# ---------------------------------------------------------------------------

def get_campaign_registry(request: Any) -> CampaignRegistry:  # noqa: ANN401
    """Return the active campaign registry from app state."""
    registry = getattr(request.app.state, "campaign_registry", None)
    if registry is None:
        raise RuntimeError(
            "Campaign registry not configured — check app lifespan or test fixture."
        )
    return registry
