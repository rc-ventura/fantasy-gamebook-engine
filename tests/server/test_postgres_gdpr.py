"""Live-Postgres GDPR export/erasure tests (T059, SC-014/SC-017, FR-026/FR-035).

Skipped unless ``DATABASE_URL`` is set.  Writes a full campaign (character,
world, events, save slot) via ``PostgresStorage`` and proves the export payload
includes it — including ``save_slots`` — and that erasure removes every row.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from gamebook.domain.models import Attribute, CharacterSheet, Event, World

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


def _storage(campaign_id: str, account_id: str):
    from gamebook.storage.postgres import PostgresStorage

    return PostgresStorage(DATABASE_URL, campaign_id, account_id)


def _seed(storage) -> None:
    storage.save_character(
        CharacterSheet(
            name="Aldric",
            skill=Attribute(initial=11, current=10),
            stamina=Attribute(initial=20, current=16),
            luck=Attribute(initial=9, current=8),
            inventory=["sword"],
            gold=12,
            provisions=2,
            conditions=[],
            alive=True,
        )
    )
    storage.save_world(
        World(current_location="grey_gate", visited_locations=["start", "grey_gate"], turn=4)
    )
    storage.append_event(
        Event(turn=1, type="enter_zone", data={"zone": "foothills"}, timestamp="2026-07-02T10:00:00Z")
    )
    storage.save_slot("checkpoint-1")


@pytest.mark.asyncio
async def test_export_includes_campaign_and_save_slots():
    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    aid = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]
    cid = str(uuid.uuid4())
    _seed(_storage(cid, aid))

    export = await repo.export_account(aid)

    assert export["account"]["account_id"] == aid
    campaign = next(c for c in export["campaigns"] if c["campaign_id"] == cid)
    assert campaign["character"]["name"] == "Aldric"
    assert campaign["world"]["current_location"] == "grey_gate"
    assert campaign["events"], "events should be exported"
    slot_names = {s["name"] for s in campaign["save_slots"]}
    assert "checkpoint-1" in slot_names


@pytest.mark.asyncio
async def test_erasure_removes_all_rows():
    from gamebook_web.accounts import AccountRepository

    repo = AccountRepository(DATABASE_URL)
    aid = (await repo.get_or_create(f"oidc|{uuid.uuid4()}"))["account_id"]
    cid = str(uuid.uuid4())
    _seed(_storage(cid, aid))

    await repo.delete_account(aid)

    engine = create_async_engine(DATABASE_URL)
    async with AsyncSession(engine) as session:
        for table in ("account", "campaign", "character_sheet", "world", "event", "save_slot"):
            col = "id" if table in ("account", "campaign") else "campaign_id"
            key = aid if table == "account" else cid
            row = await session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :key"), {"key": key}
            )
            assert row.scalar_one() == 0, f"{table} still has rows after erasure"
