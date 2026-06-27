"""Atomic-write safety (T008 / FR-004, SC-002).

Proves that a simulated failure mid-write leaves the last committed state intact
and no corruption occurs.  Both ``JSONStorage`` (existing) and ``PostgresStorage``
(new, live Postgres only) are covered here.

For ``PostgresStorage``, atomicity comes from SQL transactions — a rollback
leaves the previous committed row in place.  We simulate failure by raising
inside the async helper, which causes SQLAlchemy to roll back the transaction.
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from gamebook.storage import json_storage as json_storage_module

# ---------------------------------------------------------------------------
# DATABASE_URL sentinel — Postgres tests are skipped when absent
# ---------------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _temp_leftovers(estado_dir) -> list[str]:
    return [p.name for p in estado_dir.iterdir() if p.name.endswith(".tmp")]


# ===========================================================================
# JSONStorage atomic-write tests (pre-existing, preserved here)
# ===========================================================================


def test_json_save_leaves_no_temp_files(json_storage, sample_character, tmp_path) -> None:
    json_storage.save_character(sample_character)
    estado = tmp_path / "estado"
    assert (estado / "character.json").is_file()
    assert _temp_leftovers(estado) == []


def test_json_replace_failure_preserves_previous_state(
    json_storage, sample_character, monkeypatch, tmp_path
) -> None:
    # Establish a known-good committed state.
    json_storage.save_character(sample_character)
    assert json_storage.load_character() == sample_character

    def boom(src, dst):  # pragma: no cover - trivial stub
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(json_storage_module.os, "replace", boom)

    newer = sample_character.model_copy(update={"gold": 999})
    with pytest.raises(OSError):
        json_storage.save_character(newer)

    monkeypatch.undo()

    # Previous state intact and still loadable; no temp file left behind.
    estado = tmp_path / "estado"
    assert json_storage.load_character() == sample_character
    assert _temp_leftovers(estado) == []


def test_json_append_event_replace_failure_preserves_events(
    json_storage, sample_events, monkeypatch, tmp_path
) -> None:
    for event in sample_events:
        json_storage.append_event(event)
    assert json_storage.load_events() == sample_events

    def boom(src, dst):  # pragma: no cover - trivial stub
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(json_storage_module.os, "replace", boom)

    from gamebook.domain.models import Event
    extra = Event(turn=77, type="test", data={}, timestamp="2026-06-27T00:00:00Z")
    with pytest.raises(OSError):
        json_storage.append_event(extra)

    monkeypatch.undo()

    estado = tmp_path / "estado"
    assert json_storage.load_events() == sample_events
    assert _temp_leftovers(estado) == []


# ===========================================================================
# PostgresStorage atomic-write tests (T008, FR-004, SC-002)
# Skipped when DATABASE_URL is not set.
# ===========================================================================


@pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set — skipping Postgres atomic tests")
class TestPostgresAtomicWrites:
    """PostgresStorage: failures mid-transaction leave the previous state intact."""

    @pytest.fixture(autouse=True)
    def setup(self):
        from gamebook.storage.postgres import PostgresStorage

        campaign_id = str(uuid.uuid4())
        self.storage = PostgresStorage(DATABASE_URL, campaign_id)

    def test_failed_save_character_preserves_previous(self, sample_character) -> None:
        """A raised exception inside _save_character rolls back; old data survives."""
        # Write known-good state
        self.storage.save_character(sample_character)
        assert self.storage.load_character() == sample_character

        newer = sample_character.model_copy(update={"gold": 999})

        # Patch the async helper to raise after beginning the transaction
        original = self.storage._save_character

        async def boom(character):
            # Start the session/transaction then raise to simulate mid-write crash
            from sqlalchemy import text
            async with self.storage._session() as session:
                async with session.begin():
                    raise RuntimeError("simulated mid-write failure")

        with patch.object(self.storage, "_save_character", side_effect=boom):
            with pytest.raises(RuntimeError, match="simulated mid-write failure"):
                self.storage.save_character(newer)

        # Previous state must be intact
        assert self.storage.load_character() == sample_character

    def test_failed_append_event_preserves_previous_events(
        self, sample_events
    ) -> None:
        """A failed event append does not corrupt the existing event log."""
        for event in sample_events:
            self.storage.append_event(event)
        assert self.storage.load_events() == sample_events

        from gamebook.domain.models import Event
        extra = Event(turn=99, type="boom", data={}, timestamp="2026-06-27T00:00:00Z")

        async def boom(event):
            async with self.storage._session() as session:
                async with session.begin():
                    raise RuntimeError("simulated mid-write failure")

        with patch.object(self.storage, "_append_event", side_effect=boom):
            with pytest.raises(RuntimeError):
                self.storage.append_event(extra)

        # Event log must be unchanged
        assert self.storage.load_events() == sample_events

    def test_failed_save_world_preserves_previous_world(self, sample_world) -> None:
        """A failed world save does not corrupt the stored world."""
        self.storage.save_world(sample_world)
        assert self.storage.load_world() == sample_world

        from gamebook.domain.models import World
        bad_world = World(current_location="corrupt_zone", turn=999)

        async def boom(world):
            async with self.storage._session() as session:
                async with session.begin():
                    raise RuntimeError("simulated mid-write failure")

        with patch.object(self.storage, "_save_world", side_effect=boom):
            with pytest.raises(RuntimeError):
                self.storage.save_world(bad_world)

        assert self.storage.load_world() == sample_world

    def test_campaign_resumes_at_last_consistent_state_after_failure(
        self, sample_character, sample_world
    ) -> None:
        """After a write failure, reopening the same campaign sees last good state."""
        from gamebook.storage.postgres import PostgresStorage

        # Write good state
        self.storage.save_character(sample_character)
        self.storage.save_world(sample_world)

        # Simulate a failed write
        newer = sample_character.model_copy(update={"gold": 0})

        async def boom(character):
            async with self.storage._session() as session:
                async with session.begin():
                    raise RuntimeError("simulated crash")

        with patch.object(self.storage, "_save_character", side_effect=boom):
            with pytest.raises(RuntimeError):
                self.storage.save_character(newer)

        # Reopen the same campaign (simulating process restart)
        s2 = PostgresStorage(DATABASE_URL, self.storage._campaign_id)
        assert s2.load_character() == sample_character
        assert s2.load_world() == sample_world
