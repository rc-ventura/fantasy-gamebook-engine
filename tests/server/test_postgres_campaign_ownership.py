"""Live-Postgres campaign ownership tests (T057, SC-010/SC-017, FR-035, ADR-025).

Skipped unless ``DATABASE_URL`` is set.  Proves campaign rows carry their owning
``account_id`` (not NULL), duplicate ids are rejected 409, and list/delete work
against the database rather than any in-memory cache.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


def _repo():
    from gamebook_web.accounts import AccountRepository

    return AccountRepository(DATABASE_URL)


async def _account_id(repo) -> str:
    acc = await repo.get_or_create(f"oidc|{uuid.uuid4()}")
    return acc["account_id"]


@pytest.mark.asyncio
async def test_create_campaign_sets_account_id_not_null():
    repo = _repo()
    aid = await _account_id(repo)
    cid = str(uuid.uuid4())
    await repo.create_campaign(aid, cid)

    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        row = await session.execute(
            text("SELECT account_id FROM campaign WHERE id = :id"), {"id": cid}
        )
        account_id = row.scalar_one()
    assert account_id == aid


@pytest.mark.asyncio
async def test_duplicate_campaign_id_is_409():
    repo = _repo()
    aid = await _account_id(repo)
    cid = str(uuid.uuid4())
    await repo.create_campaign(aid, cid)

    with pytest.raises(HTTPException) as exc:
        await repo.create_campaign(aid, cid)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_list_campaigns_reads_from_db():
    repo = _repo()
    aid = await _account_id(repo)
    ids = {str(uuid.uuid4()) for _ in range(3)}
    for cid in ids:
        await repo.create_campaign(aid, cid)

    listed = {c["campaign_id"] for c in await repo.get_campaigns(aid)}
    assert ids <= listed


@pytest.mark.asyncio
async def test_delete_campaign_removes_row():
    repo = _repo()
    aid = await _account_id(repo)
    cid = str(uuid.uuid4())
    await repo.create_campaign(aid, cid)

    assert await repo.delete_campaign(aid, cid) is True
    assert await repo.get_campaign(aid, cid) is None
