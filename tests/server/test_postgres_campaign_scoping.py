"""Live-Postgres campaign scoping tests (T060, SC-002/SC-017, FR-035).

Skipped unless ``DATABASE_URL`` is set.  Two ``PostgresStorage`` instances with
different ``campaign_id`` values must not see each other's engine state — the
per-campaign ``WHERE campaign_id = :cid`` scoping makes cross-campaign leakage
structurally impossible on a shared database.
"""

from __future__ import annotations

import os
import uuid

import pytest

from gamebook.domain.models import Attribute, CharacterSheet, World

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set — skipping live Postgres tests"
)


def _storage(campaign_id: str):
    from gamebook.storage.postgres import PostgresStorage

    return PostgresStorage(DATABASE_URL, campaign_id)


def _character(name: str, location: str):
    return CharacterSheet(
        name=name,
        skill=Attribute(initial=11, current=11),
        stamina=Attribute(initial=20, current=20),
        luck=Attribute(initial=9, current=9),
    )


def test_two_campaigns_do_not_see_each_others_state():
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())
    storage_a = _storage(cid_a)
    storage_b = _storage(cid_b)

    storage_a.save_character(_character("Aria", "north_gate"))
    storage_a.save_world(World(current_location="north_gate", turn=7))

    storage_b.save_character(_character("Borin", "south_road"))
    storage_b.save_world(World(current_location="south_road", turn=2))

    # Each storage reads only its own campaign's rows.
    char_a = storage_a.load_character()
    char_b = storage_b.load_character()
    assert char_a is not None and char_a.name == "Aria"
    assert char_b is not None and char_b.name == "Borin"

    assert storage_a.load_world().current_location == "north_gate"
    assert storage_b.load_world().current_location == "south_road"
    assert storage_a.load_world().turn == 7
    assert storage_b.load_world().turn == 2


def test_reading_absent_campaign_is_empty_not_cross_leaked():
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())
    storage_a = _storage(cid_a)
    storage_a.save_character(_character("Aria", "north_gate"))

    # A fresh campaign has no character even though another campaign does.
    assert _storage(cid_b).load_character() is None
