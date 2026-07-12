"""Live-Postgres CampaignRegistry durability (issues #14/#25, ADR-025).

Skipped unless ``DATABASE_URL`` is set.  Same acceptance criteria as the
hermetic suite, but through the real ``AccountRepository`` and the real
``campaign`` table (migration 0003 adds name/ended_reason/ended_at).
"""

from __future__ import annotations

import os
import uuid

import pytest

from gamebook_web.sessions.campaign import CampaignRegistry

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


@pytest.mark.asyncio
async def test_registry_restart_and_replica_semantics_against_postgres():
    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    aid = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]

    try:
        # Process 1 creates the run.
        reg1 = CampaignRegistry(repository=repo)
        created = await reg1.create(aid, name="Durable Run")

        # "Restarted" process (fresh memory, same DB) resolves it.
        reg2 = CampaignRegistry(repository=AccountRepository(DATABASE_URL))
        resolved = await reg2.get_active_for_account(aid)
        assert resolved is not None
        assert resolved.campaign_id == created.campaign_id
        assert resolved.name == "Durable Run"

        # Replica 2 ends the run; replica 1 observes it, with metadata.
        await reg2.set_ended(resolved.campaign_id, reason="victory")
        assert await reg1.get_active_for_account(aid) is None
        ended = await reg1.list_ended_for_account(aid)
        assert [c.campaign_id for c in ended] == [created.campaign_id]
        assert ended[0].ended_reason == "victory"
        assert ended[0].ended_at is not None
    finally:
        await repo.delete_account(aid)


@pytest.mark.asyncio
async def test_end_campaign_is_ownership_scoped():
    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    owner = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]
    other = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]

    try:
        cid = (await repo.create_campaign(owner))["campaign_id"]
        assert await repo.end_campaign(other, cid, reason="death") is False
        assert (await repo.get_active_campaign(owner))["campaign_id"] == cid
        assert await repo.end_campaign(owner, cid, reason="death") is True
        assert await repo.get_active_campaign(owner) is None
    finally:
        await repo.delete_account(owner)
        await repo.delete_account(other)
