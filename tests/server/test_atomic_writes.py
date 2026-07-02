"""Atomic-write safety (T008 / FR-004, SC-002; rewritten in 006 T078 / FR-043, SC-024).

Proves that a simulated failure mid-write leaves the last committed state intact
and no corruption occurs.  Both ``JSONStorage`` (existing) and ``PostgresStorage``
(live Postgres only) are covered here.

For ``PostgresStorage`` the failure is injected AFTER the real SQL statement has
executed inside the open transaction (not before — the earlier version raised
before any ``session.execute()`` ran, which proved nothing about rollback).
The patched ``AsyncSession.execute`` runs the real INSERT/UPDATE/DELETE, then
raises; SQLAlchemy must roll the transaction back, discarding the executed but
uncommitted write.
"""

from __future__ import annotations

import os
import uuid

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
# PostgresStorage atomic-write tests (006 T078 — FR-043, SC-024)
# Skipped when DATABASE_URL is not set.
# ===========================================================================

_WRITE_PREFIXES = ("INSERT", "UPDATE", "DELETE")


def _is_write(statement) -> bool:
    return str(statement).lstrip().upper().startswith(_WRITE_PREFIXES)


@pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set — skipping Postgres atomic tests")
class TestPostgresAtomicWrites:
    """PostgresStorage: a crash AFTER a real execute leaves the previous state intact.

    The failure is injected by patching ``AsyncSession.execute``: the real
    statement runs inside the open transaction, THEN the simulated crash is
    raised. Rollback must discard the executed-but-uncommitted write.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from gamebook.storage.postgres import PostgresStorage

        campaign_id = str(uuid.uuid4())
        self.storage = PostgresStorage(DATABASE_URL, campaign_id)
        yield
        # Deterministic lifecycle (T074 / ADR-027): dispose engine + stop loop.
        self.storage.close()

    def _crash_after_write(self, monkeypatch, crash_on_write_number: int = 1) -> dict:
        """Patch AsyncSession.execute: run the real statement, crash after the Nth write.

        Returns a counter dict so tests can assert the write really executed
        before the crash (the whole point of T078).
        """
        from sqlalchemy.ext.asyncio import AsyncSession

        counts = {"writes_executed": 0}
        real_execute = AsyncSession.execute

        async def execute_then_crash(session_self, statement, *args, **kwargs):
            result = await real_execute(session_self, statement, *args, **kwargs)
            if _is_write(statement):
                counts["writes_executed"] += 1
                if counts["writes_executed"] >= crash_on_write_number:
                    raise RuntimeError("simulated crash after write executed")
            return result

        monkeypatch.setattr(AsyncSession, "execute", execute_then_crash)
        return counts

    def test_crash_after_executed_upsert_rolls_back_character(
        self, sample_character, monkeypatch
    ) -> None:
        """The character UPSERT executes for real, then crashes → old row survives."""
        self.storage.save_character(sample_character)
        assert self.storage.load_character() == sample_character

        newer = sample_character.model_copy(update={"gold": 999})
        with monkeypatch.context() as m:
            counts = self._crash_after_write(m)
            with pytest.raises(RuntimeError, match="simulated crash after write executed"):
                self.storage.save_character(newer)

        # The write DID execute inside the transaction before the crash…
        assert counts["writes_executed"] >= 1
        # …and rollback discarded it: previous committed state intact.
        assert self.storage.load_character() == sample_character

    def test_crash_after_executed_insert_rolls_back_event(
        self, sample_events, monkeypatch
    ) -> None:
        """The event INSERT executes for real, then crashes → log unchanged."""
        for event in sample_events:
            self.storage.append_event(event)
        assert self.storage.load_events() == sample_events

        from gamebook.domain.models import Event

        extra = Event(turn=99, type="boom", data={}, timestamp="2026-06-27T00:00:00Z")
        with monkeypatch.context() as m:
            counts = self._crash_after_write(m)
            with pytest.raises(RuntimeError):
                self.storage.append_event(extra)

        assert counts["writes_executed"] >= 1
        assert self.storage.load_events() == sample_events

    def test_crash_after_executed_write_rolls_back_world(
        self, sample_world, monkeypatch
    ) -> None:
        self.storage.save_world(sample_world)
        assert self.storage.load_world() == sample_world

        from gamebook.domain.models import World

        bad_world = World(current_location="corrupt_zone", turn=999)
        with monkeypatch.context() as m:
            counts = self._crash_after_write(m)
            with pytest.raises(RuntimeError):
                self.storage.save_world(bad_world)

        assert counts["writes_executed"] >= 1
        assert self.storage.load_world() == sample_world

    def test_crash_mid_multi_statement_restore_commits_nothing(
        self, sample_character, sample_world, monkeypatch
    ) -> None:
        """load_slot's restore runs many statements; crashing on the 2nd write
        must leave the pre-restore state fully intact — no half-restored mix."""
        # State A → snapshot
        self.storage.save_character(sample_character)
        self.storage.save_world(sample_world)
        self.storage.save_slot("checkpoint")

        # Mutate to state B (post-snapshot progress)
        richer = sample_character.model_copy(update={"gold": 777})
        self.storage.save_character(richer)
        from gamebook.domain.models import World

        later_world = World(current_location="summit", turn=42)
        self.storage.save_world(later_world)

        # Restore crashes after the 2nd real write statement executed.
        with monkeypatch.context() as m:
            counts = self._crash_after_write(m, crash_on_write_number=2)
            with pytest.raises(RuntimeError):
                self.storage.load_slot("checkpoint")

        assert counts["writes_executed"] >= 2
        # No partial restore: state B is fully intact (all-or-nothing).
        assert self.storage.load_character() == richer
        assert self.storage.load_world() == later_world

    def test_campaign_resumes_at_last_consistent_state_after_failure(
        self, sample_character, sample_world, monkeypatch
    ) -> None:
        """After a crash-after-execute, reopening the campaign sees last good state."""
        from gamebook.storage.postgres import PostgresStorage

        self.storage.save_character(sample_character)
        self.storage.save_world(sample_world)

        newer = sample_character.model_copy(update={"gold": 0})
        with monkeypatch.context() as m:
            self._crash_after_write(m)
            with pytest.raises(RuntimeError):
                self.storage.save_character(newer)

        # Reopen the same campaign (simulating process restart)
        s2 = PostgresStorage(DATABASE_URL, self.storage._campaign_id)
        try:
            assert s2.load_character() == sample_character
            assert s2.load_world() == sample_world
        finally:
            s2.close()
