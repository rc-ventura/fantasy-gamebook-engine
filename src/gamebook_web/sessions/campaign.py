"""Campaign registry — DB-backed when a repository is configured (ADR-025).

Campaign existence, ownership, status, and end-state metadata live in the
``campaign`` table via ``AccountRepository`` (issues #14/#25, spec-006 T037):
reads are DB-first, so a backend restart or a second replica sharing the same
database resolves the caller's active campaign instead of losing it.  The
in-memory dict remains for two things only:

  * transient per-campaign state that is deliberately not durable — the
    latest narrator Scene (``current_scene``, re-derivable by taking a turn);
  * the whole store, when no repository is configured (pure in-memory
    dev/test runs without ``DATABASE_URL``).

``CampaignState`` object identity is stable per campaign_id within a process:
DB reads merge into the cached instance rather than replacing it, so a route
that fetched the state and then ends the campaign observes the mutation on
the object it already holds.

The registry is stored in ``app.state.campaign_registry`` so it is:
  - Isolated per app instance (each TestClient call gets its own registry via
    the lifespan fixture).
  - Accessible from routes via ``Depends(get_campaign_registry)``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class CampaignState:
    """Mutable per-campaign state tracked by the API layer."""

    campaign_id: str
    account_id: str
    status: Literal["active", "ended"] = "active"
    name: str | None = None                       # optional run name (from POST /me/game body.name)
    current_scene: dict[str, Any] | None = None   # latest narrator Scene (for GET /scene) — transient
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: str | None = None
    ended_reason: Literal["death", "victory"] | None = None


class CampaignRegistry:
    """Campaign store — durable via ``AccountRepository`` when provided.

    Without a repository this is the same in-memory store as before (used by
    hermetic tests and DATABASE_URL-less dev runs).  With one, the database is
    the source of truth for existence/status and memory only carries the
    transient scene cache.
    """

    def __init__(self, repository: Any | None = None) -> None:
        self._campaigns: dict[str, CampaignState] = {}
        self._repository = repository

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, account_id: str, name: str | None = None, campaign_id: str | None = None) -> CampaignState:
        cid = campaign_id or str(uuid.uuid4())
        if self._repository is not None:
            # Durable row first (owned by account_id — issue #19); a failure
            # here must not leave a memory-only campaign the DB knows nothing
            # about.
            await self._repository.create_campaign(account_id, cid, name=name)
        state = CampaignState(campaign_id=cid, account_id=account_id, name=name)
        self._campaigns[cid] = state
        return state

    async def get_active_for_account(self, account_id: str) -> CampaignState | None:
        """Return the single active campaign for this account, or None.

        DB-first when a repository is configured: this is what lets a fresh
        process (restart, second replica) resolve campaigns it never created.
        """
        if self._repository is not None:
            row = await self._repository.get_active_campaign(account_id)
            if row is None:
                return None
            return self._merge_row(account_id, row)
        for c in self._campaigns.values():
            if c.account_id == account_id and c.status == "active":
                return c
        return None

    async def list_ended_for_account(self, account_id: str) -> list[CampaignState]:
        """Return all ended campaigns for this account (graveyard)."""
        if self._repository is not None:
            rows = await self._repository.list_ended_campaigns(account_id)
            return [self._merge_row(account_id, r) for r in rows]
        return [c for c in self._campaigns.values() if c.account_id == account_id and c.status == "ended"]

    def get(self, campaign_id: str) -> CampaignState | None:
        return self._campaigns.get(campaign_id)

    def list_for_account(self, account_id: str) -> list[CampaignState]:
        return [c for c in self._campaigns.values() if c.account_id == account_id]

    def delete(self, campaign_id: str) -> bool:
        return self._campaigns.pop(campaign_id, None) is not None

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    async def set_ended(self, campaign_id: str, reason: Literal["death", "victory"] | None = None) -> None:
        state = self._campaigns.get(campaign_id)
        if state is not None:
            state.status = "ended"
            state.ended_at = datetime.now(timezone.utc).isoformat()
            state.ended_reason = reason
        if self._repository is not None:
            if state is None:
                # Every route fetches the active campaign (which caches it)
                # before ending it, so this indicates a logic error — refuse
                # to guess the owner rather than update unscoped.
                logger.warning(
                    "set_ended(%s) without cached state — DB status not updated", campaign_id
                )
                return
            await self._repository.end_campaign(state.account_id, campaign_id, reason=reason)

    def set_scene(self, campaign_id: str, scene_dict: dict[str, Any] | None) -> None:
        if s := self._campaigns.get(campaign_id):
            s.current_scene = scene_dict

    def clear(self) -> None:
        """Reset in-memory state (tests; also simulates a process restart —
        with a repository configured, campaigns remain resolvable from the DB)."""
        self._campaigns.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _merge_row(self, account_id: str, row: dict[str, Any]) -> CampaignState:
        """Fold a repository row into the cached CampaignState (stable identity).

        The cached instance keeps its transient fields (``current_scene``);
        durable fields are refreshed from the row.
        """
        cid = row["campaign_id"]
        state = self._campaigns.get(cid)
        if state is None:
            state = CampaignState(campaign_id=cid, account_id=account_id)
            self._campaigns[cid] = state
        state.status = row.get("status", "active")
        state.name = row.get("name")
        if row.get("created_at"):
            state.created_at = row["created_at"]
        state.ended_at = row.get("ended_at")
        state.ended_reason = row.get("ended_reason")
        return state


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
