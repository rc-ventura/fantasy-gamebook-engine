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
    holds an unexpired lease, raises ``409 not_session_holder`` — the caller
    must use ``takeover`` (which validates the current holder's token) to
    force a reassignment.  There is no unauthenticated force-acquire path.

``validate(campaign_id, account_id, lease_token)``
    Raises ``409 not_session_holder`` if the token does not match the current
    holder's token, or if ``account_id`` does not match the current holder's
    account, or ``409 lease_expired`` if the lease has expired.  Binding to
    ``account_id`` (not just the opaque token) means a leaked lease token
    cannot be replayed by a different account (H-02).

``renew(campaign_id, lease_token)``
    Extends the TTL of an unexpired lease.  Called on every successful
    state-changing request.

``release(campaign_id, account_id, lease_token)``
    Deletes the lease row — only the current holder (matching account *and*
    token) may release; a mismatch is a silent no-op (nothing to release from
    the caller's point of view).

``takeover(campaign_id, account_id, current_token)``
    Atomically replaces the holder; old token is invalidated.  The caller
    MUST present the currently-held token — this is the only supported path
    to force-reassign an unexpired lease.
"""

from __future__ import annotations

import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from gamebook_web.db import pg_engine_kwargs

logger = logging.getLogger(__name__)

# Default lease TTL: 30 minutes
DEFAULT_LEASE_TTL_SECONDS = 30 * 60


def _tokens_match(a: str, b: str) -> bool:
    """Constant-time token comparison (CWE-208 — avoid timing side-channels)."""
    return hmac.compare_digest(a, b)


def _accounts_match(a: str, b: str) -> bool:
    """Constant-time account_id comparison (L-TIMING — avoid timing oracle
    on whether the supplied account is the current lease holder)."""
    return hmac.compare_digest(a, b)

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
        # TLS (ADR-026) + bounded pool (L-POOL), shared with AccountRepository
        # via pg_engine_kwargs() — lease tokens must not travel plaintext.
        self._engine = create_async_engine(url, **pg_engine_kwargs())
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
    ) -> dict[str, Any]:
        """Create or renew the lease for ``account_id`` on ``campaign_id``.

        Returns ``{"lease_token": ..., "expires_at": ...}``.
        Raises 409 if another account holds an unexpired lease. There is no
        force-override parameter (H-01) — an active lease can only be
        reassigned via ``takeover``, which validates the current holder's
        token first.
        """
        async with self._session() as session:
            async with session.begin():
                existing = await self._get_lease_for_update(session, campaign_id)
                now = datetime.now(tz=timezone.utc)

                if existing is not None:
                    db_token, db_holder, db_expires_at = existing
                    # A lease whose expiry is exactly now() is already expired (T043/FR-028).
                    is_expired = db_expires_at <= now
                    is_same_holder = db_holder == account_id

                    if not is_expired and not is_same_holder:
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

    async def validate(self, campaign_id: str, account_id: str, lease_token: str) -> None:
        """Assert the token AND account match the current unexpired lease.

        Binding to ``account_id`` (H-02) means a leaked lease token cannot be
        replayed by a different account — both the token and the holder's
        account must match.

        Uses ``SELECT ... FOR UPDATE`` (ADR-032) so the lease row is locked
        for the duration of this transaction, preventing a concurrent
        ``takeover`` from rotating the holder between validate and the
        protected mutation (TOCTOU).

        Raises:
            409 ``not_session_holder`` — token or account mismatch
            409 ``lease_expired`` — token matches but lease has expired
        """
        async with self._session() as session:
            async with session.begin():
                row = await session.execute(
                    text(
                        "SELECT lease_token, holder_account_id, expires_at FROM session_lease "
                        "WHERE campaign_id = :cid FOR UPDATE"
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

                db_token, db_holder, db_expires_at = result
                now = datetime.now(tz=timezone.utc)

                # Make expires_at timezone-aware if it isn't
                if db_expires_at.tzinfo is None:
                    db_expires_at = db_expires_at.replace(tzinfo=timezone.utc)

                # L-TIMING: evaluate both comparisons unconditionally (no
                # short-circuit) to avoid a timing oracle on account_id.
                holder_ok = _accounts_match(db_holder, account_id)
                token_ok = _tokens_match(db_token, lease_token)
                if not holder_ok or not token_ok:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "not_session_holder",
                                "message": "You do not hold the session lease for this campaign.",
                            }
                        },
                    )

                if db_expires_at <= now:
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

    async def validate_and_renew(
        self, campaign_id: str, account_id: str, lease_token: str
    ) -> None:
        """Atomically validate the lease AND renew its TTL in one transaction.

        This closes the TOCTOU window (ADR-032): ``require_lease`` previously
        called ``validate()`` and ``renew()`` in separate transactions.  A
        concurrent ``takeover`` could rotate the holder between the two,
        causing the mutation to proceed under an invalidated lease.  By
        combining both operations under a single ``FOR UPDATE`` lock, the
        lease row cannot change between validation and renewal.

        Raises the same 409 errors as ``validate()``.
        """
        async with self._session() as session:
            async with session.begin():
                row = await session.execute(
                    text(
                        "SELECT lease_token, holder_account_id, expires_at FROM session_lease "
                        "WHERE campaign_id = :cid FOR UPDATE"
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

                db_token, db_holder, db_expires_at = result
                now = datetime.now(tz=timezone.utc)
                if db_expires_at.tzinfo is None:
                    db_expires_at = db_expires_at.replace(tzinfo=timezone.utc)

                # L-TIMING: evaluate both unconditionally.
                holder_ok = _accounts_match(db_holder, account_id)
                token_ok = _tokens_match(db_token, lease_token)
                if not holder_ok or not token_ok:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "not_session_holder",
                                "message": "You do not hold the session lease for this campaign.",
                            }
                        },
                    )

                if db_expires_at <= now:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "lease_expired",
                                "message": "Your session lease has expired. Acquire a new one.",
                            }
                        },
                    )

                # Renew TTL within the same locked transaction.
                new_expires = self._new_expiry()
                await session.execute(
                    text(
                        "UPDATE session_lease SET expires_at = :expires "
                        "WHERE campaign_id = :cid"
                    ),
                    {"expires": new_expires, "cid": campaign_id},
                )

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
                if result is None or not _tokens_match(result[0], lease_token):
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

    async def release(self, campaign_id: str, account_id: str, lease_token: str) -> None:
        """Delete the lease row — only the current holder (account + token) may release.

        Binding to ``account_id`` (H-02) prevents a leaked token from another
        account releasing (and thereby hijacking) someone else's lease. A
        mismatch is a silent no-op: from the caller's perspective there is
        simply nothing of theirs to release.
        """
        async with self._session() as session:
            async with session.begin():
                row = await session.execute(
                    text(
                        "SELECT lease_token, holder_account_id FROM session_lease "
                        "WHERE campaign_id = :cid FOR UPDATE"
                    ),
                    {"cid": campaign_id},
                )
                result = row.fetchone()
                if result is None:
                    return  # nothing to release
                db_token, db_holder = result
                # L-TIMING: evaluate both unconditionally.
                holder_ok = _accounts_match(db_holder, account_id)
                token_ok = _tokens_match(db_token, lease_token)
                if not holder_ok or not token_ok:
                    return  # not the holder — no-op
                await session.execute(
                    text("DELETE FROM session_lease WHERE campaign_id = :cid"),
                    {"cid": campaign_id},
                )

    # ------------------------------------------------------------------
    # takeover
    # ------------------------------------------------------------------

    async def takeover(
        self, campaign_id: str, account_id: str, current_token: str
    ) -> dict[str, Any]:
        """Atomically rotate the lease, validating ``current_token`` first (FR-027).

        The caller MUST present the currently-held token.  A wrong or missing
        ``current_token`` is rejected ``409 not_session_holder`` — an active
        lease cannot be stolen by a session that never held it; the claimant
        must present the current token or wait for the lease to expire (after
        which ``acquire`` succeeds).  On a valid token the lease is replaced
        with a fresh token/holder in the same transaction, invalidating the old.

        If no lease exists yet there is nothing to take over → treated as a
        fresh acquire.
        """
        async with self._session() as session:
            async with session.begin():
                existing = await self._get_lease_for_update(session, campaign_id)
                new_token = str(uuid.uuid4())
                new_expires = self._new_expiry()

                if existing is None:
                    # No current holder to validate against — create the lease.
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

                db_token, _db_holder, _db_expires_at = existing
                if not current_token or not _tokens_match(current_token, db_token):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": {
                                "code": "not_session_holder",
                                "message": (
                                    "Takeover requires the current session token. Present the "
                                    "active token, or wait for the lease to expire."
                                ),
                            }
                        },
                    )

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
                "is_expired": db_expires_at <= datetime.now(tz=timezone.utc),
            }


# ---------------------------------------------------------------------------
# require_lease — route-level enforcement dependency (C-01, ADR-023, ADR-031)
# ---------------------------------------------------------------------------
#
# LeaseGuardMiddleware was originally written for the ``/campaigns/{id}/**``
# route scheme, extracting campaign_id straight from the URL. The D1 redesign
# (``/me/game/**``) resolves campaign_id from the caller's account instead of
# the URL, which requires the auth dependency to have already run — something
# plain ASGI middleware cannot do without bypassing FastAPI's dependency-
# override mechanism (calling ``get_current_account`` directly as a plain
# function from middleware would always hit the dev stub, since
# ``app.dependency_overrides`` only intercepts ``Depends()`` resolution).
# ``require_lease`` instead takes ``Depends(get_current_account)`` as its own
# parameter, so FastAPI resolves it through the normal (overridable) DI graph
# — it sees the real account in production and the dev account in tests. See
# ADR-031.

from fastapi import Depends, Header, Request  # noqa: E402

from gamebook_web.auth.dev_auth import Account, get_current_account  # noqa: E402


async def require_lease(
    request: Request,
    account: Account = Depends(get_current_account),
    x_session_lease: str | None = Header(default=None, alias="X-Session-Lease"),
) -> None:
    """Enforce the session lease on a mutating D1 route (ADR-023, FR-025).

    No-op when ``DATABASE_URL`` is unset (dev/test — lease state is not
    tracked without a database) or when the caller has no active campaign yet
    (nothing to protect) or when nobody has acquired a lease for it yet (the
    lease is opt-in: it only starts enforcing exclusivity once a session calls
    ``POST /me/game/session``). Once a lease exists, every mutating request
    must present the current holder's token via ``X-Session-Lease`` — a
    missing or stale token is rejected ``409``, and a successful request
    renews the lease TTL.

    ``account`` is resolved via ``Depends(get_current_account)`` — the same
    dependency object every route already uses — so FastAPI's
    ``app.dependency_overrides`` (dev stub → real OIDC in production) applies
    here exactly as it does everywhere else.
    """
    if not os.getenv("DATABASE_URL"):
        return

    # Import lazily to avoid a module-level cycle (sessions.campaign is only
    # needed when a database is actually configured).
    from gamebook_web.sessions.campaign import CampaignRegistry, get_campaign_registry

    registry: CampaignRegistry = get_campaign_registry(request)
    state = registry.get_active_for_account(account.account_id)
    if state is None:
        return  # no active campaign — the route itself will 404

    campaign_id = state.campaign_id
    lease_svc = get_lease_service()

    existing = await lease_svc.get_lease(campaign_id)
    if existing is None:
        return  # no lease acquired yet — nothing to enforce

    from gamebook_web.observability.audit import audit_event

    if not x_session_lease:
        audit_event(
            "lease.denied", level=logging.WARNING, campaign_id=campaign_id, reason="missing_token"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "not_session_holder",
                    "message": "X-Session-Lease header is required for state-changing operations.",
                }
            },
        )

    try:
        # ADR-032: validate + renew atomically in a single FOR UPDATE
        # transaction to close the TOCTOU window.  HTTPException from
        # validate_and_renew (not_session_holder / lease_expired) MUST
        # propagate — swallowing it would let a taken-over lease proceed.
        await lease_svc.validate_and_renew(campaign_id, account.account_id, x_session_lease)
    except HTTPException:
        audit_event(
            "lease.denied", level=logging.WARNING, campaign_id=campaign_id, reason="validate_failed"
        )
        raise
    except Exception:
        # Non-HTTP exceptions (DB connectivity, etc.) are non-fatal — the
        # request proceeds without lease renewal rather than failing hard
        # on an infrastructure blip.  This is intentionally narrower than
        # the previous ``except Exception: pass`` which also swallowed 409s.
        logger.warning("lease validate_and_renew error for campaign %s", campaign_id, exc_info=True)


# FastAPI dependency marker for routes: ``Depends(require_lease)``.
RequireLease = Depends(require_lease)
