"""Live-Postgres account tests (T056, SC-017, FR-035, ADR-025).

Skipped unless ``DATABASE_URL`` is set.  Exercises ``AccountRepository`` against
a real database: upsert on first access, resolution from the OIDC ``sub``, and
cascade deletion.
"""

from __future__ import annotations

import os
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


def _repo():
    from gamebook_web.accounts import AccountRepository

    return AccountRepository(DATABASE_URL)


@pytest.mark.asyncio
async def test_get_or_create_is_idempotent_per_sub():
    repo = _repo()
    sub = f"oidc|{uuid.uuid4()}"

    first = await repo.get_or_create(sub)
    second = await repo.get_or_create(sub)

    assert first["account_id"] == second["account_id"]
    assert first["sub"] == sub


@pytest.mark.asyncio
async def test_distinct_subs_resolve_to_distinct_accounts():
    repo = _repo()
    a = await repo.get_or_create(f"oidc|{uuid.uuid4()}")
    b = await repo.get_or_create(f"oidc|{uuid.uuid4()}")
    assert a["account_id"] != b["account_id"]

    # Resolution by id returns the same row.
    fetched = await repo.get_account_by_id(a["account_id"])
    assert fetched is not None
    assert fetched["account_id"] == a["account_id"]


@pytest.mark.asyncio
async def test_ensure_account_provisions_a_fixed_id_row():
    """issue #15: the dev-stub account has no OIDC login to provision its row.

    Without this, the first campaign/lease write for GAMEBOOK_DEV_MODE's
    fixed account_id foreign-key-violates against a real database — found via
    live two-tab session-lease testing.
    """
    repo = _repo()
    account_id = f"dev-account-test-{uuid.uuid4()}"

    await repo.ensure_account(account_id)
    fetched = await repo.get_account_by_id(account_id)
    assert fetched is not None
    assert fetched["account_id"] == account_id


@pytest.mark.asyncio
async def test_ensure_account_is_idempotent():
    repo = _repo()
    account_id = f"dev-account-test-{uuid.uuid4()}"

    await repo.ensure_account(account_id)
    await repo.ensure_account(account_id)  # must not raise (ON CONFLICT DO NOTHING)

    fetched = await repo.get_account_by_id(account_id)
    assert fetched is not None


@pytest.mark.asyncio
async def test_delete_account_cascades_campaigns():
    repo = _repo()
    account = await repo.get_or_create(f"oidc|{uuid.uuid4()}")
    aid = account["account_id"]
    cid = str(uuid.uuid4())
    await repo.create_campaign(aid, cid)

    assert await repo.get_campaign(aid, cid) is not None

    await repo.delete_account(aid)

    assert await repo.get_account_by_id(aid) is None
    assert await repo.get_campaign(aid, cid) is None
