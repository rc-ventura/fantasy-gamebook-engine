"""NarratorBackend port and FakeNarrator (ADR-011, Principle IV).

``NarratorBackend`` is the swap boundary #3 interface: the FastAPI routes
talk to a ``NarratorBackend``; the concrete implementations (``FakeNarrator``
for tests, ``PydanticNarrator`` for live play) hide behind it.

``FakeNarrator`` is the test double.  It returns a deterministic ``Scene``
with no LLM calls, no MCP calls, and no external I/O — pure in-memory.
Tests inject it via ``app.dependency_overrides[get_narrator]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from gamebook_web.harness.scene import Choice, Effect, Scene

# ---------------------------------------------------------------------------
# Context passed to the narrator for a turn
# ---------------------------------------------------------------------------

@dataclass
class NarratorContext:
    """Engine state snapshot read before narrating a turn.

    The narrator reads these fields to produce the next ``Scene``.  State
    changes happen ONLY via ``Scene.effects[]`` executed through MCP — never
    by the narrator directly (Principle I).
    """

    character: dict[str, Any] | None = None       # CharacterSheet or None (not yet created)
    world: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    choice: str | int | None = None               # player's most recent choice


# ---------------------------------------------------------------------------
# NarratorBackend Protocol (swap boundary #3)
# ---------------------------------------------------------------------------

@runtime_checkable
class NarratorBackend(Protocol):
    """The narrator port.  ``PydanticNarrator`` and ``FakeNarrator`` both satisfy it."""

    async def narrate(
        self,
        campaign_id: str,
        context: NarratorContext,
    ) -> Scene:
        """Produce the next ``Scene`` given the campaign id and engine context."""
        ...


# ---------------------------------------------------------------------------
# Default opening Scene (used by FakeNarrator when no queue is provided)
# ---------------------------------------------------------------------------

_DEFAULT_OPENING_SCENE = Scene(
    narrative=(
        "You stand at the base of the Grey Mountain, wind howling around you. "
        "Runes carved into the ancient stone glow faintly — a warning, or an invitation? "
        "Somewhere above, the archmage Malachar waits. "
        "Your adventure begins here."
    ),
    choices=[
        Choice(id="1", label="Climb the mountain path"),
        Choice(id="2", label="Study the glowing runes"),
        Choice(id="3", label="Make camp and rest first"),
    ],
    effects=[
        Effect(
            type="register_event",
            params={"type": "adventure_start", "data": {"location": "mountain_base"}},
        ),
        Effect(
            type="update_world",
            params={"current_location": "mountain_base"},
        ),
    ],
)

_DEFAULT_FOLLOWUP_SCENE = Scene(
    narrative=(
        "You push forward along the winding mountain path. "
        "Loose stones skitter underfoot as the altitude climbs. "
        "A fork in the path presents itself: one way leads into a dark cave, "
        "the other continues upward through an exposed ridge."
    ),
    choices=[
        Choice(id="1", label="Enter the cave"),
        Choice(id="2", label="Continue along the ridge"),
    ],
    effects=[
        Effect(
            type="register_event",
            params={"type": "exploration", "data": {"location": "mountain_path"}},
        ),
    ],
)


# ---------------------------------------------------------------------------
# FakeNarrator — deterministic test double
# ---------------------------------------------------------------------------

class FakeNarrator:
    """Deterministic narrator for tests — no LLM, no MCP, no I/O.

    Scenes are consumed in order from the queue; once exhausted, alternates
    between the built-in opening and follow-up defaults so the play loop can
    run indefinitely.

    Usage::

        narrator = FakeNarrator(scenes=[
            opening_scene,
            combat_scene,
            terminal_scene,
        ])
        app.dependency_overrides[get_narrator] = lambda: narrator
    """

    def __init__(self, scenes: list[Scene] | None = None) -> None:
        self._queue: list[Scene] = list(scenes) if scenes else []
        self._call_count: int = 0

    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:  # noqa: ARG002
        self._call_count += 1
        if self._queue:
            return self._queue.pop(0)
        # Alternate defaults once queue is empty
        if self._call_count % 2 == 1:
            return _DEFAULT_OPENING_SCENE
        return _DEFAULT_FOLLOWUP_SCENE


# ---------------------------------------------------------------------------
# FastAPI dependency (overridden by tests via dependency_overrides)
# ---------------------------------------------------------------------------

def get_narrator(request: Any) -> NarratorBackend:  # noqa: ANN401
    """FastAPI dependency: return the active narrator from app state."""
    narrator = getattr(request.app.state, "narrator", None)
    if narrator is None:
        raise RuntimeError(
            "Narrator not configured — check app lifespan or test fixture."
        )
    return narrator
