"""In-memory ``StorageBackend`` implementation.

Holds all state in process memory. It exists to prove that every other module
works without touching disk (the point of swap point #1) and to give fast,
isolated unit tests for ``combat`` and ``mcp``.

Every value is deep-copied on the way in and on the way out, so a stored object
can never be mutated through an aliased reference held by a caller. This makes
the in-memory backend observationally identical to ``JSONStorage``, which
snapshots via serialization.
"""

from __future__ import annotations

from typing import Any, Literal

from gamebook.domain.models import (
    ArchiveRecord,
    CharacterSheet,
    Combat,
    Event,
    World,
)


class InMemoryStorage:
    """A ``StorageBackend`` backed by plain Python containers."""

    def __init__(self) -> None:
        self._character: CharacterSheet | None = None
        self._world: World | None = None
        self._events: list[Event] = []
        self._summary: str = ""
        self._combats: dict[str, Combat] = {}
        self._archives: dict[str, list[ArchiveRecord]] = {
            "graveyard": [],
            "hall_of_fame": [],
        }
        self._slots: dict[str, dict[str, Any]] = {}

    # --- Character -----------------------------------------------------------
    def load_character(self) -> CharacterSheet | None:
        return None if self._character is None else self._character.model_copy(deep=True)

    def save_character(self, character: CharacterSheet) -> None:
        self._character = character.model_copy(deep=True)

    # --- World ---------------------------------------------------------------
    def load_world(self) -> World:
        return World() if self._world is None else self._world.model_copy(deep=True)

    def save_world(self, world: World) -> None:
        self._world = world.model_copy(deep=True)

    # --- Events --------------------------------------------------------------
    def append_event(self, event: Event) -> None:
        self._events.append(event.model_copy(deep=True))

    def load_events(self) -> list[Event]:
        return [event.model_copy(deep=True) for event in self._events]

    # --- Narrative summary ---------------------------------------------------
    def load_summary(self) -> str:
        return self._summary

    def save_summary(self, text: str) -> None:
        self._summary = text

    # --- In-progress combat --------------------------------------------------
    def load_combat(self, combat_id: str) -> Combat | None:
        combat = self._combats.get(combat_id)
        return None if combat is None else combat.model_copy(deep=True)

    def save_combat(self, combat: Combat) -> None:
        self._combats[combat.combat_id] = combat.model_copy(deep=True)

    def remove_combat(self, combat_id: str) -> None:
        self._combats.pop(combat_id, None)

    # --- End states ----------------------------------------------------------
    def archive(
        self,
        record: ArchiveRecord,
        destination: Literal["graveyard", "hall_of_fame"],
    ) -> None:
        if destination not in self._archives:
            raise ValueError(f"unknown archive destination: {destination!r}")
        self._archives[destination].append(record.model_copy(deep=True))

    # --- Save slots ----------------------------------------------------------
    def save_slot(self, name: str) -> None:
        self._slots[name] = self._snapshot()

    def load_slot(self, name: str) -> None:
        if name not in self._slots:
            raise FileNotFoundError(f"save slot not found: {name!r}")
        self._restore(self._slots[name])

    # --- Internal snapshot helpers ------------------------------------------
    def _snapshot(self) -> dict[str, Any]:
        return {
            "character": None if self._character is None else self._character.model_copy(deep=True),
            "world": None if self._world is None else self._world.model_copy(deep=True),
            "events": [event.model_copy(deep=True) for event in self._events],
            "summary": self._summary,
            "combats": {key: value.model_copy(deep=True) for key, value in self._combats.items()},
            "archives": {
                key: [record.model_copy(deep=True) for record in value]
                for key, value in self._archives.items()
            },
        }

    def _restore(self, snapshot: dict[str, Any]) -> None:
        character: CharacterSheet | None = snapshot["character"]
        world: World | None = snapshot["world"]
        self._character = None if character is None else character.model_copy(deep=True)
        self._world = None if world is None else world.model_copy(deep=True)
        self._events = [event.model_copy(deep=True) for event in snapshot["events"]]
        self._summary = snapshot["summary"]
        self._combats = {
            key: value.model_copy(deep=True) for key, value in snapshot["combats"].items()
        }
        self._archives = {
            key: [record.model_copy(deep=True) for record in value]
            for key, value in snapshot["archives"].items()
        }
