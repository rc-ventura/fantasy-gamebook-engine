"""Campaign registry — transient per-session cache (DB is authoritative in 004).

When a database is configured, ``AccountRepository`` is the source of truth for
campaign existence, ownership, and status (FR-022, ADR-025): those survive a
restart.  This registry then only caches transient per-session state that need
not be durable — the latest narrator scene (for ``GET /scene``) and a cached
copy of status.  ``adopt()`` re-hydrates a transient shell for a DB-known
campaign that isn't cached yet (e.g. after a process restart).

Without a database (dev/test), the registry is authoritative on its own.

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

    def adopt(
        self,
        campaign_id: str,
        account_id: str,
        status: str = "active",
    ) -> CampaignState:
        """Cache a transient shell for a DB-known campaign (FR-022).

        Used when the DB confirms a campaign exists/owned but the in-memory
        cache has no entry (e.g. after a restart).  Status comes from the DB.
        """
        state = CampaignState(
            campaign_id=campaign_id,
            account_id=account_id,
            status="ended" if status == "ended" else "active",
        )
        self._campaigns[campaign_id] = state
        return state

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
