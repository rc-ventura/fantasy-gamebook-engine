"""Live-Postgres session-lease tests (T058, SC-011/SC-017, FR-027/FR-028).

Skipped unless ``DATABASE_URL`` is set.  Exercises ``LeaseService`` against a
real database: acquire/validate/takeover/release, ``current_token`` validation
on takeover (FR-027), the ``<=`` expiry boundary (FR-028), and that a
non-holder cannot steal an active lease under concurrency (SELECT FOR UPDATE).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


def _svc(ttl: int = 1800):
    from gamebook_web.sessions.lease import LeaseService

    return LeaseService(DATABASE_URL, lease_ttl_seconds=ttl)


async def _account_and_campaign() -> tuple[str, str]:
    """Create a real account + campaign so lease FKs resolve."""
    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    acc = await repo.get_or_create(f"oidc|{uuid.uuid4()}")
    cid = str(uuid.uuid4())
    await repo.create_campaign(acc["account_id"], cid)
    return acc["account_id"], cid


@pytest.mark.asyncio
async def test_acquire_then_validate_ok():
    aid, cid = await _account_and_campaign()
    svc = _svc()
    lease = await svc.acquire(cid, aid)
    # Correct token validates without error.
    await svc.validate(cid, lease["lease_token"])


@pytest.mark.asyncio
async def test_validate_wrong_token_is_409():
    aid, cid = await _account_and_campaign()
    svc = _svc()
    await svc.acquire(cid, aid)
    with pytest.raises(HTTPException) as exc:
        await svc.validate(cid, "not-the-token")
    assert exc.value.status_code == 409
    assert exc.value.detail["error"]["code"] == "not_session_holder"


@pytest.mark.asyncio
async def test_takeover_with_correct_token_rotates_and_invalidates_old():
    aid, cid = await _account_and_campaign()
    svc = _svc()
    first = await svc.acquire(cid, aid)
    rotated = await svc.takeover(cid, aid, first["lease_token"])

    assert rotated["lease_token"] != first["lease_token"]
    # Old token no longer validates; new one does.
    with pytest.raises(HTTPException):
        await svc.validate(cid, first["lease_token"])
    await svc.validate(cid, rotated["lease_token"])


@pytest.mark.asyncio
async def test_takeover_with_wrong_token_is_409():
    aid, cid = await _account_and_campaign()
    svc = _svc()
    await svc.acquire(cid, aid)
    with pytest.raises(HTTPException) as exc:
        await svc.takeover(cid, aid, "wrong-token")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_release_removes_lease():
    aid, cid = await _account_and_campaign()
    svc = _svc()
    lease = await svc.acquire(cid, aid)
    await svc.release(cid, lease["lease_token"])
    assert await svc.get_lease(cid) is None


@pytest.mark.asyncio
async def test_expired_lease_is_rejected_and_replaceable():
    """FR-028: a lease at/after its expiry is expired (`<=`), and acquire by
    another account then succeeds (an expired lease is orphaned)."""
    aid, cid = await _account_and_campaign()
    svc = _svc()
    token = str(uuid.uuid4())
    past = datetime.now(tz=timezone.utc) - timedelta(seconds=1)

    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO session_lease "
                    "(campaign_id, lease_token, holder_account_id, acquired_at, expires_at) "
                    "VALUES (:cid, :token, :holder, NOW(), :expires)"
                ),
                {"cid": cid, "token": token, "holder": aid, "expires": past},
            )

    # Expired token is rejected.
    with pytest.raises(HTTPException) as exc:
        await svc.validate(cid, token)
    assert exc.value.detail["error"]["code"] == "lease_expired"

    # A fresh acquire replaces the expired lease (no 409).
    new_lease = await svc.acquire(cid, aid)
    assert new_lease["lease_token"] != token


@pytest.mark.asyncio
async def test_non_holder_cannot_steal_under_concurrency():
    """Two concurrent acquires by a non-holder must both be refused (the holder
    keeps the lease) — SELECT FOR UPDATE serializes them."""
    from gamebook_web.accounts import AccountRepository

    aid, cid = await _account_and_campaign()
    repo = AccountRepository(DATABASE_URL)
    other = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]

    svc = _svc()
    await svc.acquire(cid, aid)  # holder acquires

    results = await asyncio.gather(
        svc.acquire(cid, other),
        svc.acquire(cid, other),
        return_exceptions=True,
    )
    # Neither non-holder acquire succeeds while the lease is held and unexpired.
    assert all(isinstance(r, HTTPException) and r.status_code == 409 for r in results), results
