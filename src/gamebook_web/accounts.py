"""Account persistence and campaign ownership helpers (slice 004 — T004).

``AccountRepository`` wraps async SQLAlchemy to provide:
  - ``get_or_create(sub)`` — upsert account on first authenticated access
  - ``get_campaigns(account_id)`` — list campaigns owned by an account
  - ``get_campaign(account_id, campaign_id)`` — ownership-checked fetch (None if not owned)
  - ``delete_account(account_id)`` — cascade: session_lease → campaigns → account row
  - ``export_account(account_id)`` — portable data export (GDPR)

All queries include ``WHERE account_id = :account_id``; cross-account leakage is
structurally impossible at this layer.

PII stored: only ``sub`` (OIDC subject) + ``created_at`` — no email, no name.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton repository (one per process, keyed on DATABASE_URL)
# ---------------------------------------------------------------------------

_REPOSITORY: AccountRepository | None = None


def get_account_repository() -> AccountRepository:
    """Return the process-level AccountRepository (created on first call)."""
    global _REPOSITORY
    if _REPOSITORY is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set — AccountRepository cannot initialize")
        _REPOSITORY = AccountRepository(url)
    return _REPOSITORY


def set_account_repository(repo: AccountRepository | None) -> None:
    """Override the singleton (for testing)."""
    global _REPOSITORY
    _REPOSITORY = repo


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class AccountRepository:
    """Async SQLAlchemy-backed account and ownership queries."""

    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url, pool_pre_ping=True)

    def _session(self) -> AsyncSession:
        return AsyncSession(self._engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # Account lifecycle
    # ------------------------------------------------------------------

    async def get_or_create(self, sub: str) -> dict[str, Any]:
        """Upsert an account by OIDC subject; return ``{"account_id": ..., "sub": ..., "created_at": ...}``.

        Uses ``INSERT ... ON CONFLICT (sub) DO NOTHING`` so two concurrent
        first-logins for the same subject do not race on the UNIQUE constraint:
        one inserts, the other is a no-op, and both then read the same row.
        """
        async with self._session() as session:
            async with session.begin():
                # Atomic upsert — the candidate id is only used if no row exists.
                account_id = str(uuid.uuid4())
                await session.execute(
                    text(
                        "INSERT INTO account (id, sub, created_at) "
                        "VALUES (:id, :sub, NOW()) "
                        "ON CONFLICT (sub) DO NOTHING"
                    ),
                    {"id": account_id, "sub": sub},
                )
                # Read back by sub (the stable, unique key) so we return the
                # winning row regardless of which request created it.
                row = await session.execute(
                    text("SELECT id, sub, created_at FROM account WHERE sub = :sub"),
                    {"sub": sub},
                )
                created = row.fetchone()
                return {
                    "account_id": created[0],
                    "sub": created[1],
                    "created_at": created[2].isoformat() if created[2] else None,
                }

    async def get_account_by_id(self, account_id: str) -> dict[str, Any] | None:
        """Fetch account row by id."""
        async with self._session() as session:
            row = await session.execute(
                text("SELECT id, sub, created_at FROM account WHERE id = :id"),
                {"id": account_id},
            )
            result = row.fetchone()
            if result is None:
                return None
            return {
                "account_id": result[0],
                "sub": result[1],
                "created_at": result[2].isoformat() if result[2] else None,
            }

    async def delete_account(self, account_id: str) -> None:
        """Cascade-delete account and all owned campaigns/engine rows.

        Cascade order:
          session_lease (per campaign FK) → engine rows (FK ON DELETE CASCADE) →
          campaign rows → account row.

        The FK ON DELETE CASCADE on campaign_id handles engine rows automatically.
        We only need to delete session_lease explicitly if FK cascade isn't set up
        (it is in the 0002 migration, but we do it explicitly for safety).
        """
        async with self._session() as session:
            async with session.begin():
                # Get all campaigns for this account
                rows = await session.execute(
                    text("SELECT id FROM campaign WHERE account_id = :account_id"),
                    {"account_id": account_id},
                )
                campaign_ids = [r[0] for r in rows.fetchall()]

                # Delete session leases
                for cid in campaign_ids:
                    await session.execute(
                        text("DELETE FROM session_lease WHERE campaign_id = :cid"),
                        {"cid": cid},
                    )

                # Delete campaigns (cascades to all engine rows via FK)
                await session.execute(
                    text("DELETE FROM campaign WHERE account_id = :account_id"),
                    {"account_id": account_id},
                )

                # Delete account
                await session.execute(
                    text("DELETE FROM account WHERE id = :id"),
                    {"id": account_id},
                )

    # ------------------------------------------------------------------
    # Campaign ownership
    # ------------------------------------------------------------------

    async def get_campaigns(self, account_id: str) -> list[dict[str, Any]]:
        """List all campaigns owned by this account."""
        async with self._session() as session:
            rows = await session.execute(
                text(
                    "SELECT id, status, created_at, updated_at, summary_text "
                    "FROM campaign WHERE account_id = :account_id "
                    "ORDER BY created_at DESC"
                ),
                {"account_id": account_id},
            )
            return [
                {
                    "campaign_id": r[0],
                    "status": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                    "updated_at": r[3].isoformat() if r[3] else None,
                    "summary": r[4] or "",
                }
                for r in rows.fetchall()
            ]

    async def get_campaign(
        self, account_id: str, campaign_id: str
    ) -> dict[str, Any] | None:
        """Ownership-checked campaign fetch. Returns None if not found or not owned."""
        async with self._session() as session:
            row = await session.execute(
                text(
                    "SELECT id, status, account_id, created_at, updated_at, summary_text "
                    "FROM campaign "
                    "WHERE id = :cid AND account_id = :account_id"
                ),
                {"cid": campaign_id, "account_id": account_id},
            )
            result = row.fetchone()
            if result is None:
                return None
            return {
                "campaign_id": result[0],
                "status": result[1],
                "account_id": result[2],
                "created_at": result[3].isoformat() if result[3] else None,
                "updated_at": result[4].isoformat() if result[4] else None,
                "summary": result[5] or "",
            }

    async def create_campaign(self, account_id: str, campaign_id: str | None = None) -> dict[str, Any]:
        """Insert a new campaign row owned by account_id."""
        cid = campaign_id or str(uuid.uuid4())
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO campaign (id, account_id, status, created_at, updated_at, summary_text) "
                        "VALUES (:id, :account_id, 'active', NOW(), NOW(), '') "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": cid, "account_id": account_id},
                )
        return {"campaign_id": cid, "status": "active", "account_id": account_id}

    async def set_campaign_status(
        self, account_id: str, campaign_id: str, status: str
    ) -> bool:
        """Update campaign status (e.g. 'ended'), ownership-checked.

        The ``account_id`` filter makes cross-account status changes
        structurally impossible (CWE-639): a caller can only mutate a campaign
        it owns.  Returns True if a row was updated, False otherwise.
        """
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "UPDATE campaign SET status = :status, updated_at = NOW() "
                        "WHERE id = :cid AND account_id = :account_id "
                        "RETURNING id"
                    ),
                    {"status": status, "cid": campaign_id, "account_id": account_id},
                )
                return result.fetchone() is not None

    async def delete_campaign(self, account_id: str, campaign_id: str) -> bool:
        """Delete a campaign (ownership-checked). Returns True if deleted."""
        async with self._session() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        "DELETE FROM campaign "
                        "WHERE id = :cid AND account_id = :account_id "
                        "RETURNING id"
                    ),
                    {"cid": campaign_id, "account_id": account_id},
                )
                return result.fetchone() is not None

    # ------------------------------------------------------------------
    # GDPR export
    # ------------------------------------------------------------------

    async def export_account(self, account_id: str) -> dict[str, Any]:
        """Export all data owned by this account (GDPR portability)."""
        async with self._session() as session:
            # Account row
            acc_row = await session.execute(
                text("SELECT id, sub, created_at FROM account WHERE id = :id"),
                {"id": account_id},
            )
            acc = acc_row.fetchone()
            if acc is None:
                return {}

            # Campaigns
            camp_rows = await session.execute(
                text(
                    "SELECT id, status, created_at, summary_text "
                    "FROM campaign WHERE account_id = :account_id"
                ),
                {"account_id": account_id},
            )
            campaigns = []
            for camp in camp_rows.fetchall():
                cid = camp[0]
                campaign_data: dict[str, Any] = {
                    "campaign_id": cid,
                    "status": camp[1],
                    "created_at": camp[2].isoformat() if camp[2] else None,
                    "summary": camp[3] or "",
                }

                # Character
                char_row = await session.execute(
                    text("SELECT data FROM character_sheet WHERE campaign_id = :cid"),
                    {"cid": cid},
                )
                char_result = char_row.fetchone()
                campaign_data["character"] = (
                    char_result[0] if char_result else None
                )
                if isinstance(campaign_data["character"], str):
                    campaign_data["character"] = json.loads(campaign_data["character"])

                # World
                world_row = await session.execute(
                    text("SELECT data FROM world WHERE campaign_id = :cid"),
                    {"cid": cid},
                )
                world_result = world_row.fetchone()
                campaign_data["world"] = (
                    world_result[0] if world_result else None
                )
                if isinstance(campaign_data["world"], str):
                    campaign_data["world"] = json.loads(campaign_data["world"])

                # Events
                ev_rows = await session.execute(
                    text(
                        "SELECT payload FROM event WHERE campaign_id = :cid ORDER BY seq ASC"
                    ),
                    {"cid": cid},
                )
                events = []
                for (payload,) in ev_rows.fetchall():
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    events.append(payload)
                campaign_data["events"] = events

                # Archive records
                arc_rows = await session.execute(
                    text(
                        "SELECT destination, payload, archived_at "
                        "FROM archive_record WHERE campaign_id = :cid"
                    ),
                    {"cid": cid},
                )
                archive = []
                for arc in arc_rows.fetchall():
                    payload = arc[1]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    archive.append({
                        "destination": arc[0],
                        "data": payload,
                        "archived_at": arc[2].isoformat() if arc[2] else None,
                    })
                campaign_data["archive"] = archive

                campaigns.append(campaign_data)

            return {
                "account": {
                    "account_id": acc[0],
                    "sub": acc[1],
                    "created_at": acc[2].isoformat() if acc[2] else None,
                },
                "campaigns": campaigns,
            }
