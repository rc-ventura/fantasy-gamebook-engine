"""Test: concurrent campaigns across accounts stay isolated (T016 / SC-005).

Requires DATABASE_URL; skipped otherwise.

Scenario:
  Two concurrent asyncio.Task instances, each writing to their own campaign
  (scoped to separate accounts), run simultaneously.  After completion, each
  campaign is loaded and verified to contain only the expected data with no
  cross-campaign row contamination.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="Requires DATABASE_URL (Postgres) to run",
)


def _make_storage(url: str, campaign_id: str):
    from gamebook.storage.postgres import PostgresStorage
    return PostgresStorage(url, campaign_id)


def _make_character(name: str, stamina: int = 20):
    from gamebook.domain.models import Attribute, CharacterSheet
    return CharacterSheet(
        name=name,
        skill=Attribute(initial=10, current=10),
        stamina=Attribute(initial=stamina, current=stamina),
        luck=Attribute(initial=8, current=8),
        inventory=[name],  # unique marker
        gold=0,
        provisions=3,
        conditions=[],
        alive=True,
    )


def test_concurrent_campaigns_do_not_contaminate():
    """Two campaigns running concurrently in threads stay isolated."""
    import threading

    url = os.environ["DATABASE_URL"]
    cid_a = str(uuid.uuid4())
    cid_b = str(uuid.uuid4())

    storage_a = _make_storage(url, cid_a)
    storage_b = _make_storage(url, cid_b)

    errors = []

    def write_and_verify(storage, name: str, stamina: int) -> None:
        try:
            char = _make_character(name, stamina)
            storage.save_character(char)
        except Exception as exc:
            errors.append(exc)

    t_a = threading.Thread(target=write_and_verify, args=(storage_a, "HeroA", 18))
    t_b = threading.Thread(target=write_and_verify, args=(storage_b, "HeroB", 16))

    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    assert not errors, f"Errors during concurrent writes: {errors}"

    # Verify isolation: each campaign has only its own data
    char_a = storage_a.load_character()
    char_b = storage_b.load_character()

    assert char_a is not None and char_a.name == "HeroA", (
        f"Campaign A should have HeroA, got: {char_a}"
    )
    assert char_b is not None and char_b.name == "HeroB", (
        f"Campaign B should have HeroB, got: {char_b}"
    )
    assert char_a.stamina.current == 18
    assert char_b.stamina.current == 16

    # Confirm cross-campaign inventory isolation
    assert "HeroA" in char_a.inventory
    assert "HeroB" not in char_a.inventory
    assert "HeroB" in char_b.inventory
    assert "HeroA" not in char_b.inventory


def test_many_concurrent_campaigns():
    """N campaigns can run simultaneously without contamination."""
    import threading
    import random

    url = os.environ["DATABASE_URL"]
    N = 5
    campaign_ids = [str(uuid.uuid4()) for _ in range(N)]
    stamina_values = [random.randint(10, 20) for _ in range(N)]

    storages = [_make_storage(url, cid) for cid in campaign_ids]
    errors = []

    def worker(idx: int) -> None:
        try:
            char = _make_character(f"Hero{idx}", stamina_values[idx])
            storages[idx].save_character(char)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors: {errors}"

    for i in range(N):
        char = storages[i].load_character()
        assert char is not None
        assert char.name == f"Hero{i}", f"Expected Hero{i}, got {char.name}"
        assert char.stamina.current == stamina_values[i]
