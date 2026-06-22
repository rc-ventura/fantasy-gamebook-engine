"""Storage abstraction (swap point #1).

`StorageBackend` is the only thing the rest of the engine is allowed to depend
on for persistence. Concrete implementations (``InMemoryStorage``,
``JSONStorage``, a future ``PostgresStorage``) are injected at the composition
root (``mcp.server.main``); no other module constructs them.

This module depends solely on ``gamebook.domain`` types, and only for typing
(imports are guarded behind ``TYPE_CHECKING``), keeping the contract free of any
runtime coupling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from gamebook.domain.models import (
        ArchiveRecord,
        CharacterSheet,
        Combat,
        Event,
        World,
    )


@runtime_checkable
class StorageBackend(Protocol):
    """Persists every piece of state that survives between sessions.

    Guarantees required of every implementation:

    * **Atomic writes** — a crash mid-write must never corrupt previously
      persisted state.
    * **Consistent reads** — a load reflects the last fully-committed write.
    * **JSON round-trip parity** — ``load_*`` returns a value equal to the one
      passed to the matching ``save_*``.
    """

    # --- Character -----------------------------------------------------------
    def load_character(self) -> CharacterSheet | None:
        """Return the persisted character, or ``None`` if none exists yet."""
        ...

    def save_character(self, character: CharacterSheet) -> None:
        """Persist (replace) the character sheet."""
        ...

    # --- World ---------------------------------------------------------------
    def load_world(self) -> World:
        """Return the persisted world, or a fresh default ``World`` if none."""
        ...

    def save_world(self, world: World) -> None:
        """Persist (replace) the world state."""
        ...

    # --- Events (append-only chronology) ------------------------------------
    def append_event(self, event: Event) -> None:
        """Append one event; existing events are never mutated or reordered."""
        ...

    def load_events(self) -> list[Event]:
        """Return all events in insertion order (empty list if none)."""
        ...

    # --- Narrative summary ---------------------------------------------------
    def load_summary(self) -> str:
        """Return the narrative summary, or an empty string if none."""
        ...

    def save_summary(self, text: str) -> None:
        """Persist (replace) the narrative summary."""
        ...

    # --- In-progress combat --------------------------------------------------
    def load_combat(self, combat_id: str) -> Combat | None:
        """Return the in-progress combat with this id, or ``None``."""
        ...

    def save_combat(self, combat: Combat) -> None:
        """Persist (replace) an in-progress combat keyed by its ``combat_id``."""
        ...

    def remove_combat(self, combat_id: str) -> None:
        """Delete an in-progress combat; a no-op if it does not exist."""
        ...

    # --- End states ----------------------------------------------------------
    def archive(
        self,
        record: ArchiveRecord,
        destination: Literal["graveyard", "hall_of_fame"],
    ) -> None:
        """Append a final-state record to the given archive (append-only)."""
        ...

    # --- Save slots ----------------------------------------------------------
    def save_slot(self, name: str) -> None:
        """Snapshot the full current state under a named slot."""
        ...

    def load_slot(self, name: str) -> None:
        """Restore the full current state from a named slot.

        Raises ``FileNotFoundError`` if the slot does not exist.
        """
        ...
