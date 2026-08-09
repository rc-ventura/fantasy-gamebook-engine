"""Campaign-ownership wiring regression tests (issue #19).

``POST /me/game`` must persist account↔campaign ownership at the composition
root: the MCP tool contract carries only campaign_id (ADR-018), so
``PostgresStorage._ensure_campaign`` creates campaign rows lazily with
``account_id = NULL``.  Before this wiring, GDPR erasure and campaign listing
(``WHERE account_id = :account_id``) silently matched zero rows for every
campaign created through the web flow.

Two layers:
  * Route wiring — hermetic, via the RecordingAccountRepository in conftest.
  * Live Postgres — end to end: web-claimed row survives the engine's lazy
    upsert unowned-row path and is removed by GDPR erasure.
"""

from __future__ import annotations

import os
import uuid

import pytest

from gamebook_web.auth.dev_auth import DEV_ACCOUNT_ID

DATABASE_URL = os.environ.get("DATABASE_URL", "")

AUTH = {"Authorization": "Bearer dev-token"}


# ---------------------------------------------------------------------------
# Route wiring (hermetic)
# ---------------------------------------------------------------------------

def test_create_game_persists_campaign_ownership(api_client, account_repo):
    resp = api_client.post("/me/game", headers=AUTH)
    assert resp.status_code == 201, resp.text
    cid = resp.json()["campaign_id"]

    assert account_repo.created == [(DEV_ACCOUNT_ID, cid)]


def test_replacing_a_game_claims_the_new_campaign_too(api_client, account_repo):
    first = api_client.post("/me/game", headers=AUTH).json()["campaign_id"]
    second = api_client.post("/me/game", headers=AUTH).json()["campaign_id"]

    assert account_repo.created == [
        (DEV_ACCOUNT_ID, first),
        (DEV_ACCOUNT_ID, second),
    ]


# ---------------------------------------------------------------------------
# Live Postgres (skipped without DATABASE_URL)
# ---------------------------------------------------------------------------

pytestmark_live = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


@pytestmark_live
@pytest.mark.asyncio
async def test_claimed_campaign_survives_engine_writes_and_gdpr_erasure():
    """The full issue-#19 scenario against a real database.

    1. Web composition root claims the campaign for the account.
    2. The engine writes state WITHOUT an account_id (as the shared MCP
       subprocess does) — the claim must not be clobbered.
    3. GDPR erasure removes the campaign and its engine rows.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from gamebook.domain.models import Attribute, CharacterSheet
    from gamebook.storage.postgres import PostgresStorage
    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    aid = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]
    cid = str(uuid.uuid4())

    # 1. Composition-root claim (what create_game now does).
    await repo.create_campaign(aid, cid)

    # 2. Engine writes with NO account_id — triggers the unowned
    #    _ensure_campaign upsert path (ON CONFLICT DO NOTHING).
    storage = PostgresStorage(DATABASE_URL, cid)
    try:
        storage.save_character(
            CharacterSheet(
                name="Claimant",
                skill=Attribute(initial=10, current=10),
                stamina=Attribute(initial=18, current=18),
                luck=Attribute(initial=8, current=8),
                inventory=[],
                gold=0,
                provisions=0,
                conditions=[],
                alive=True,
            )
        )
    finally:
        storage.close()

    engine = create_async_engine(DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            row = await session.execute(
                text("SELECT account_id FROM campaign WHERE id = :cid"), {"cid": cid}
            )
            assert row.scalar() == aid, "engine write must not orphan the claimed campaign"

        # Ownership-scoped listing now sees the campaign (was zero rows pre-fix).
        campaigns = await repo.get_campaigns(aid)
        assert cid in {c["campaign_id"] for c in campaigns}

        # 3. GDPR erasure removes campaign + engine rows (the acceptance check).
        await repo.delete_account(aid)

        async with AsyncSession(engine) as session:
            row = await session.execute(
                text("SELECT count(*) FROM campaign WHERE id = :cid"), {"cid": cid}
            )
            assert row.scalar() == 0, "erasure must delete the claimed campaign"
            row = await session.execute(
                text("SELECT count(*) FROM character_sheet WHERE campaign_id = :cid"),
                {"cid": cid},
            )
            assert row.scalar() == 0, "erasure must cascade to engine rows"
    finally:
        await engine.dispose()


@pytestmark_live
@pytest.mark.asyncio
async def test_claim_does_not_reassign_an_owned_campaign():
    """create_campaign 409s instead of stealing another account's campaign."""
    from fastapi import HTTPException

    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    owner = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]
    thief = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]
    cid = str(uuid.uuid4())

    await repo.create_campaign(owner, cid)
    with pytest.raises(HTTPException):
        await repo.create_campaign(thief, cid)

    assert (await repo.get_campaign(owner, cid)) is not None
    await repo.delete_account(owner)
    await repo.delete_account(thief)
