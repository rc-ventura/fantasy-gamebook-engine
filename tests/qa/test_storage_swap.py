"""Swap boundary #1 -- proven through `combate`, not through raw save/load.

``tests/server/test_storage_parity.py`` already proves ``InMemoryStorage`` and
``JSONStorage`` are observationally identical at the *raw* CRUD level. This test
complements it one layer up: it drives a full ``CombatService`` fight (the real
consumer of ``StorageBackend``) against three *different* backends and asserts
the observable game behaviour is byte-for-byte identical.

If swapping the storage implementation changed the outcome of a fight, the
boundary would be violated. The third backend is a tiny, in-test ``MockStorage``
(a plain dict-backed ``StorageBackend``) -- if a brand-new, independent
implementation produces the same results, the engine genuinely depends on the
*interface* and nothing more.

Determinism: each run gets a fresh ``random.Random(SEED)``, so the rules consume
an identical random stream regardless of which backend persists state. Only the
random ``combat_id`` differs between runs, so it is excluded from comparison.
"""

from __future__ import annotations

import copy
import random
from typing import Any, Literal

import pytest

from gamebook.combat.implementation import CombatService
from gamebook.domain.models import (
    ArchiveRecord,
    Attribute,
    CharacterSheet,
    Combat,
    Enemy,
    Event,
    World,
)
from gamebook.storage.in_memory import InMemoryStorage
from gamebook.storage.interfaces import StorageBackend
from gamebook.storage.json_storage import JSONStorage

SEED = 1234


# --------------------------------------------------------------------------- a third backend
class MockStorage:
    """A minimal, independent dict-backed ``StorageBackend`` implementation.

    Deep-copies on the way in and out (like ``InMemoryStorage``) so a stored
    object can never be mutated through an aliased reference -- the contract every
    faithful backend must honour. Implements the full protocol so it structurally
    satisfies ``StorageBackend`` even though ``combate`` only exercises a subset.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {"summary": ""}
        self._combats: dict[str, Combat] = {}
        self._events: list[Event] = []
        self._archives: dict[str, list[ArchiveRecord]] = {"graveyard": [], "hall_of_fame": []}
        self._slots: dict[str, Any] = {}

    # Character
    def load_character(self) -> CharacterSheet | None:
        c = self._store.get("character")
        return None if c is None else c.model_copy(deep=True)

    def save_character(self, character: CharacterSheet) -> None:
        self._store["character"] = character.model_copy(deep=True)

    # World
    def load_world(self) -> World:
        w = self._store.get("world")
        return World() if w is None else w.model_copy(deep=True)

    def save_world(self, world: World) -> None:
        self._store["world"] = world.model_copy(deep=True)

    # Events
    def append_event(self, event: Event) -> None:
        self._events.append(event.model_copy(deep=True))

    def load_events(self) -> list[Event]:
        return [e.model_copy(deep=True) for e in self._events]

    # Summary
    def load_summary(self) -> str:
        return self._store["summary"]

    def save_summary(self, text: str) -> None:
        self._store["summary"] = text

    # Combat
    def load_combat(self, combat_id: str) -> Combat | None:
        c = self._combats.get(combat_id)
        return None if c is None else c.model_copy(deep=True)

    def save_combat(self, combat: Combat) -> None:
        self._combats[combat.combat_id] = combat.model_copy(deep=True)

    def remove_combat(self, combat_id: str) -> None:
        self._combats.pop(combat_id, None)

    # End states
    def archive(self, record: ArchiveRecord, destination: Literal["graveyard", "hall_of_fame"]) -> None:
        self._archives[destination].append(record.model_copy(deep=True))

    # Slots
    def save_slot(self, name: str) -> None:
        self._slots[name] = copy.deepcopy((self._store, self._combats, self._events, self._archives))

    def load_slot(self, name: str) -> None:
        if name not in self._slots:
            raise FileNotFoundError(name)
        self._store, self._combats, self._events, self._archives = copy.deepcopy(self._slots[name])


def _make_backend(kind: str, tmp_path) -> StorageBackend:
    if kind == "memory":
        return InMemoryStorage()
    if kind == "json":
        return JSONStorage(str(tmp_path / "estado"))
    if kind == "mock":
        return MockStorage()
    raise AssertionError(kind)


def _hero() -> CharacterSheet:
    return CharacterSheet(
        name="Hero",
        skill=Attribute(initial=12, current=12),
        stamina=Attribute(initial=24, current=24),
        luck=Attribute(initial=12, current=12),
    )


def _outcome_view(o: Any) -> dict[str, Any]:
    """A backend-independent snapshot of a round outcome (drops nothing material)."""
    return o.model_dump()


def _run_full_fight(storage: StorageBackend) -> dict[str, Any]:
    """A scripted, deterministic fight; returns every observable result.

    Uses a mix of luck/no-luck rounds against a two-enemy party so the run
    touches: active-enemy switching, luck spend + persistence, damage to hero and
    enemies, end detection, and the final summary. ``combat_id`` is intentionally
    excluded from the returned view because it is random per run.
    """
    rng = random.Random(SEED)
    storage.save_character(_hero())
    engine = CombatService(storage, rng)

    combat = engine.start_combat(
        [Enemy(name="Goblin", skill=7, stamina=6), Enemy(name="Wolf", skill=8, stamina=6)],
        flee_allowed=True,
    )

    rounds: list[dict[str, Any]] = []
    use_luck_pattern = (False, True, False, True, True, False)
    final = None
    for i in range(60):
        use_luck = use_luck_pattern[i % len(use_luck_pattern)]
        outcome = engine.resolve_round(combat.combat_id, use_luck=use_luck)
        rounds.append(_outcome_view(outcome))
        if outcome.ended:
            final = engine.end_combat(combat.combat_id)
            break
    assert final is not None, "fight did not conclude within the round budget"

    sheet = storage.load_character()
    return {
        "rounds": rounds,
        "final": final.model_dump(),
        "sheet": sheet.model_dump(),
        # The in-progress record must be gone after end_combat, on every backend.
        "combat_removed": storage.load_combat(combat.combat_id) is None,
    }


def test_combat_behaviour_is_identical_across_storage_backends(tmp_path) -> None:
    """Driving the same fight through three backends yields identical results."""
    memory = _run_full_fight(_make_backend("memory", tmp_path))
    json_ = _run_full_fight(_make_backend("json", tmp_path))
    mock = _run_full_fight(_make_backend("mock", tmp_path))

    assert memory == json_, "InMemoryStorage and JSONStorage diverged (boundary #1 broken)"
    assert memory == mock, "An independent MockStorage diverged (engine coupled to a concrete impl)"

    # The fight actually did something meaningful (guards against a vacuous pass).
    assert memory["rounds"], "no rounds were resolved"
    assert memory["final"]["winner"] in ("hero", "enemy")
    assert memory["combat_removed"] is True


def test_mock_storage_satisfies_the_storage_backend_protocol() -> None:
    """The in-test backend is a real ``StorageBackend`` (structural conformance)."""
    assert isinstance(MockStorage(), StorageBackend)


@pytest.mark.parametrize("kind", ["memory", "json", "mock"])
def test_flee_behaviour_is_identical_across_backends(kind: str, tmp_path) -> None:
    """Fleeing costs exactly 2 stamina and ends the fight on every backend."""
    storage = _make_backend(kind, tmp_path)
    storage.save_character(_hero())
    engine = CombatService(storage, random.Random(SEED))

    combat = engine.start_combat([Enemy(name="Ogre", skill=10, stamina=12)], flee_allowed=True)
    result = engine.flee(combat.combat_id)

    assert result.damage_taken == 2
    assert result.ended is True
    assert result.hero_stamina == 22
    assert storage.load_character().stamina.current == 22


# --------------------------------------------------------------------------- flee-death signal (C2)
@pytest.mark.parametrize("kind", ["memory", "json", "mock"])
def test_safe_flee_signal_identical_across_backends(kind: str, tmp_path) -> None:
    """A survivable escape reports `hero_alive=True`; end_combat has no winner.

    Same observable signal on every backend (boundary #1) — proving the new
    FleeResult.hero_alive / end_combat semantics don't depend on the impl.
    """
    storage = _make_backend(kind, tmp_path)
    storage.save_character(_hero())  # stamina 24, the 2 flee-damage is harmless
    engine = CombatService(storage, random.Random(SEED))

    combat = engine.start_combat([Enemy(name="Ogre", skill=10, stamina=12)], flee_allowed=True)
    flee = engine.flee(combat.combat_id)
    assert flee.hero_alive is True
    assert flee.hero_stamina == 22
    assert storage.load_character().alive is True

    final = engine.end_combat(combat.combat_id)
    assert final.winner is None  # a safe escape is not a defeat


@pytest.mark.parametrize("kind", ["memory", "json", "mock"])
def test_fatal_flee_signal_identical_across_backends(kind: str, tmp_path) -> None:
    """A lethal escape reports `hero_alive=False`; end_combat resolves as enemy win.

    Identical on every backend: the fixed 2 flee-damage drops the hero to 0, the
    sheet flips to not-alive, and `end_combat` returns winner='enemy' even though
    `combat.winner` is None (fleeing has no winner) — the unambiguous death signal.
    """
    storage = _make_backend(kind, tmp_path)
    weak = _hero().model_copy(update={"stamina": Attribute(initial=24, current=2)})
    storage.save_character(weak)
    engine = CombatService(storage, random.Random(SEED))

    combat = engine.start_combat([Enemy(name="Wraith", skill=10, stamina=8)], flee_allowed=True)
    flee = engine.flee(combat.combat_id)
    assert flee.hero_alive is False
    assert flee.hero_stamina == 0
    assert storage.load_character().alive is False

    final = engine.end_combat(combat.combat_id)
    assert final.winner == "enemy"
