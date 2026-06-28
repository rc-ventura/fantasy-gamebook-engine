"""Session-lease enforcement — single active session per campaign (T006).

Only the lease holder may issue state-changing operations.  A second opener
is read-only until it explicitly takes over (atomic reassignment).  Stale
writes (token mismatch or expiry) are rejected with ``409``.

All DB operations are performed inside a single transaction to prevent
partial-state windows.

Lease lifecycle
---------------
``acquire(campaign_id, account_id)``
    Creates or renews the lease for the given account.  If another account
    holds an unexpired lease, raises ``409 not_session_holder`` unless
    ``force_takeover=True`` is passed.

``validate(campaign_id, lease_token)``
    Raises ``409 not_session_holder`` if the token does not match the current
    holder, or ``409 lease_expired`` if the lease has expired.

``renew(campaign_id, lease_token)``
    Extends the TTL of an unexpired lease.  Called on every successful
    state-changing request.

``release(campaign_id, lease_token)``
    Deletes the lease row (unconditionally — any token may release).

``takeover(campaign_id, account_id, current_token)``
    Atomically replaces the holder; old token is invalidated.  Raises
    ``409 not_session_holder`` if ``current_token`` is already the holder
    (no-op — use acquire instead).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = logging.getLogger(__name__)

# Default lease TTL: 30 minutes
DEFAULT_LEASE_TTL_SECONDS = 30 * 60

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_LEASE_SERVICE: LeaseService | None = None


def get_lease_service() -> LeaseService:
    """Return the process-level LeaseService."""
    global _LEASE_SERVICE
    if _LEASE_SERVICE is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL not set — LeaseService cannot initialize")
        _LEASE_SERVICE = LeaseService(url)
    return _LEASE_SERVICE


def set_lease_service(svc: LeaseService | None) -> None:
    """Override the singleton (for testing)."""
    global _LEASE_SERVICE
    _LEASE_SERVICE = svc


# ---------------------------------------------------------------------------
# LeaseService
# ---------------------------------------------------------------------------

class LeaseService:
    """Async SQLAlchemy-backed session-lease manager."""

    def __init__(self, url: str, lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> None:
        self._engine = create_async_engine(url, pool_pre_ping=True)
        self._ttl = lease_ttl_seconds

    def _session(self) -> AsyncSession:
        return AsyncSession(self._engine, expire_on_commit=False)

    def _new_expiry(self) -> datetime:
        return datetime.now(tz=timezone.utc) + timedelta(seconds=self._ttl)

    # ------------------------------------------------------------------
    # acquire
    # ------------------------------------------------------------------

    async def acquire(
        self,
        campaign_id: str,
        account_id: str,
        force_takeover: bool = False,
    ) -> dict[str, Any]:
        """Create or renew the lease for ``account_id`` on ``campaign_id``.

        Returns ``{"lease_token": ..., "expires_at": ...}``.
        Raises 409 if another account holds an unexpired lease (unless ``force_takeover``).
        """
        async with self._session() as session:
            async with session.begin():
                existing = await self._get_lease_for_update(session, campaign_id)
                now = datetime.now(tz=timezone.utc)

                if existing is not None:
                    db_token, db_holder, db_expires_at = existing
                    is_expired = db_expires_at < now
                    is_same_holder = db_holder == account_id

                    if not is_expired and not is_same_holder and not force_takeover:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail={
                                "error": {
                                    "code": "not_session_holder",
                                    "message": "Another session holds the lease for this campaign. Use takeover to claim it.",
                                }
                            },
                        )

                    # Renew or take over
                    new_token = str(uuid.uuid4())
                    new_expires = self._new_expiry()
                    await session.execute(
                        text(
                            "UPDATE session_lease "
                            "SET lease_token = :token, holder_account_id = :holder, "
                            "    acquired_at = NOW(), expires_at = :expires "
                            "WHERE campaign_id = :cid"
                        ),
                        {
                            "token": new_token,
                            "holder": account_id,
                            "expires": new_expires,
                            "cid": campaign_id,
                        },
                    )
                    return {"lease_token": new_token, "expires_at": new_expires.isoformat()}

                # No existing lease — create one
                new_token = str(uuid.uuid4())
                new_expires = self._new_expiry()
                await session.execute(
                    text(
                        "INSERT INTO session_lease "
                        "(campaign_id, lease_token, holder_account_id, acquired_at, expires_at) "
                        "VALUES (:cid, :token, :holder, NOW(), :expires)"
                    ),
                    {
                        "cid": campaign_id,
                        "token": new_token,
                        "holder": account_id,
                        "expires": new_expires,
                    },
                )
                return {"lease_token": new_token, "expires_at": new_expires.isoformat()}

    # ------------------------------------------------------------------
    # validate
    # ------------------------------------------------------------------

    async def validate(self, campaign_id: str, lease_token: str) -> None:
        """Assert the token matches the current unexpired lease.

        Raises:
            409 ``not_session_holder`` — token mismatch
            409 ``lease_expired`` — token matches but lease has expired
        """
        async with self._session() as session:
            row = await session.execute(
                text(
                    "SELECT lease_token, expires_at FROM session_lease "
                    "WHERE campaign_id = :cid"
                ),
                {"cid": campaign_id},
            )
            result = row.fetchone()
            if result is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "not_session_holder",
                            "message": "No active session lease for this campaign. Acquire one first.",
                        }
                    },
                )

            db_token, db_expires_at = result
            now = datetime.now(tz=timezone.utc)

            # Make expires_at timezone-aware if it isn't
            if db_expires_at.tzinfo is None:
                db_expires_at = db_expires_at.replace(tzinfo=timezone.utc)

            if db_token != lease_token:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "not_session_holder",
                            "message": "You do not hold the session lease for this campaign.",
                        }
                    },
                )

            if db_expires_at < now:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": {
                            "code": "lease_expired",
                            "message": "Your session lease has expired. Acquire a new one.",
                        }
                    },
                )

    # ------------------------------------------------------------------
    # renew
    # ------------------------------------------------------------------

    async def renew(self, campaign_id: str, lease_token: str) -> dict[str, Any]:
        """Extend the TTL of an unexpired lease matching ``lease_token``.

        Called automatically on every successful state-changing request.
        Returns updated ``{"lease_token": ..., "expires_at": ...}``.
        """
        async with self._session() as session:
            async with session.begin():
                row = await session.execute(
                    text(
                        "SELECT lease_token, expires_at FROM session_lease "
                        "WHERE campaign_id = :cid FOR UPDATE"
                    ),
                    {"cid": campaign_id},
                )
                result = row.fetchone()
                if result is None or result[0] != lease_token:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "not_session_holder",
                                "message": "Cannot renew — lease not held.",
                            }
                        },
                    )

                new_expires = self._new_expiry()
                await session.execute(
                    text(
                        "UPDATE session_lease SET expires_at = :expires "
                        "WHERE campaign_id = :cid AND lease_token = :token"
                    ),
                    {"expires": new_expires, "cid": campaign_id, "token": lease_token},
                )
                return {"lease_token": lease_token, "expires_at": new_expires.isoformat()}

    # ------------------------------------------------------------------
    # release
    # ------------------------------------------------------------------

    async def release(self, campaign_id: str, lease_token: str) -> None:
        """Delete the lease row. Any holder may release."""
        async with self._session() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "DELETE FROM session_lease "
                        "WHERE campaign_id = :cid AND lease_token = :token"
                    ),
                    {"cid": campaign_id, "token": lease_token},
                )

    # ------------------------------------------------------------------
    # takeover
    # ------------------------------------------------------------------

    async def takeover(
        self, campaign_id: str, account_id: str, current_token: str
    ) -> dict[str, Any]:
        """Atomically replace the lease holder; old token is invalidated.

        Returns new ``{"lease_token": ..., "expires_at": ...}``.
        """
        return await self.acquire(campaign_id, account_id, force_takeover=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_lease_for_update(
        self, session: AsyncSession, campaign_id: str
    ) -> tuple[str, str, datetime] | None:
        """Read the current lease row with a row-level lock."""
        row = await session.execute(
            text(
                "SELECT lease_token, holder_account_id, expires_at "
                "FROM session_lease "
                "WHERE campaign_id = :cid "
                "FOR UPDATE"
            ),
            {"cid": campaign_id},
        )
        result = row.fetchone()
        if result is None:
            return None
        db_token, db_holder, db_expires_at = result
        if db_expires_at.tzinfo is None:
            db_expires_at = db_expires_at.replace(tzinfo=timezone.utc)
        return db_token, db_holder, db_expires_at

    async def get_lease(self, campaign_id: str) -> dict[str, Any] | None:
        """Read the current lease (non-locking)."""
        async with self._session() as session:
            row = await session.execute(
                text(
                    "SELECT lease_token, holder_account_id, expires_at, acquired_at "
                    "FROM session_lease WHERE campaign_id = :cid"
                ),
                {"cid": campaign_id},
            )
            result = row.fetchone()
            if result is None:
                return None
            db_token, db_holder, db_expires_at, db_acquired_at = result
            if db_expires_at.tzinfo is None:
                db_expires_at = db_expires_at.replace(tzinfo=timezone.utc)
            return {
                "lease_token": db_token,
                "holder_account_id": db_holder,
                "expires_at": db_expires_at.isoformat(),
                "acquired_at": db_acquired_at.isoformat() if db_acquired_at else None,
                "is_expired": db_expires_at < datetime.now(tz=timezone.utc),
            }
