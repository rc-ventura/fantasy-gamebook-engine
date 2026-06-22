"""File-backed ``StorageBackend`` implementation (Phase-1 default).

One file per entity under a base directory (default ``estado/``):

* ``character.json``       — the single ``CharacterSheet`` (absent if none)
* ``world.json``           — the single ``World`` (absent => default ``World``)
* ``events.json``          — JSON array of ``Event`` (append-only)
* ``summary.md``           — plain-text narrative summary
* ``combat_<id>.json``     — one in-progress ``Combat`` per file
* ``graveyard.json`` /
  ``hall_of_fame.json``    — JSON arrays of ``ArchiveRecord``
* ``slots/<name>/``        — full snapshot of the above for a named save slot

**Atomicity.** Every write goes to a temp file in the *same directory* as its
target and is then moved into place with :func:`os.replace`, which is atomic on
a single filesystem. If the move fails (simulated crash), the previous file is
left untouched and the temp file is removed — state is never half-written.
fsync is intentionally skipped in Phase 1 (atomicity, not durability, is the
requirement); see the related ADR.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from gamebook.domain.models import (
    ArchiveRecord,
    CharacterSheet,
    Combat,
    Event,
    World,
)

_TEMP_SUFFIX = ".tmp"
_ARCHIVE_FILES: dict[str, str] = {
    "graveyard": "graveyard.json",
    "hall_of_fame": "hall_of_fame.json",
}


class JSONStorage:
    """A ``StorageBackend`` that persists each entity as a file on disk."""

    def __init__(self, base_dir: str | os.PathLike[str] = "estado") -> None:
        self._base = Path(base_dir)
        self._character_path = self._base / "character.json"
        self._world_path = self._base / "world.json"
        self._events_path = self._base / "events.json"
        self._summary_path = self._base / "summary.md"
        self._slots_dir = self._base / "slots"

    # --- Character -----------------------------------------------------------
    def load_character(self) -> CharacterSheet | None:
        text = self._read_text(self._character_path)
        return None if text is None else CharacterSheet.model_validate_json(text)

    def save_character(self, character: CharacterSheet) -> None:
        self._atomic_write(self._character_path, character.model_dump_json())

    # --- World ---------------------------------------------------------------
    def load_world(self) -> World:
        text = self._read_text(self._world_path)
        return World() if text is None else World.model_validate_json(text)

    def save_world(self, world: World) -> None:
        self._atomic_write(self._world_path, world.model_dump_json())

    # --- Events --------------------------------------------------------------
    def append_event(self, event: Event) -> None:
        events = self.load_events()
        events.append(event)
        payload = json.dumps([item.model_dump(mode="json") for item in events])
        self._atomic_write(self._events_path, payload)

    def load_events(self) -> list[Event]:
        text = self._read_text(self._events_path)
        if text is None:
            return []
        return [Event.model_validate(item) for item in json.loads(text)]

    # --- Narrative summary ---------------------------------------------------
    def load_summary(self) -> str:
        text = self._read_text(self._summary_path)
        return "" if text is None else text

    def save_summary(self, text: str) -> None:
        self._atomic_write(self._summary_path, text)

    # --- In-progress combat --------------------------------------------------
    def load_combat(self, combat_id: str) -> Combat | None:
        text = self._read_text(self._combat_path(combat_id))
        return None if text is None else Combat.model_validate_json(text)

    def save_combat(self, combat: Combat) -> None:
        self._atomic_write(self._combat_path(combat.combat_id), combat.model_dump_json())

    def remove_combat(self, combat_id: str) -> None:
        try:
            self._combat_path(combat_id).unlink()
        except FileNotFoundError:
            pass

    # --- End states ----------------------------------------------------------
    def archive(
        self,
        record: ArchiveRecord,
        destination: Literal["graveyard", "hall_of_fame"],
    ) -> None:
        filename = _ARCHIVE_FILES.get(destination)
        if filename is None:
            raise ValueError(f"unknown archive destination: {destination!r}")
        path = self._base / filename
        existing_text = self._read_text(path)
        records = (
            []
            if existing_text is None
            else [ArchiveRecord.model_validate(item) for item in json.loads(existing_text)]
        )
        records.append(record)
        payload = json.dumps([item.model_dump(mode="json") for item in records])
        self._atomic_write(path, payload)

    # --- Save slots ----------------------------------------------------------
    def save_slot(self, name: str) -> None:
        self._check_name(name)
        self._base.mkdir(parents=True, exist_ok=True)
        destination = self._slots_dir / name
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for item in self._base.iterdir():
            if item.is_file() and not item.name.startswith("."):
                shutil.copy2(item, destination / item.name)

    def load_slot(self, name: str) -> None:
        self._check_name(name)
        source = self._slots_dir / name
        if not source.is_dir():
            raise FileNotFoundError(f"save slot not found: {name!r}")
        # Clear current top-level state files, then restore the snapshot.
        for item in self._base.iterdir():
            if item.is_file():
                item.unlink()
        for item in source.iterdir():
            if item.is_file() and not item.name.startswith("."):
                self._atomic_write(self._base / item.name, item.read_text(encoding="utf-8"))

    # --- Internal helpers ----------------------------------------------------
    def _combat_path(self, combat_id: str) -> Path:
        self._check_name(combat_id)
        return self._base / f"combat_{combat_id}.json"

    @staticmethod
    def _check_name(value: str) -> None:
        """Reject ids/slot names that could escape the base directory."""
        if not value or "/" in value or "\\" in value or ".." in value or value in {".", ""}:
            raise ValueError(f"invalid identifier: {value!r}")

    @staticmethod
    def _read_text(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        """Write ``text`` to ``path`` atomically (temp file + ``os.replace``)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=_TEMP_SUFFIX
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_name, path)
        except BaseException:
            # Move failed (or write errored): leave the previous file intact
            # and clean up the temp artifact.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
