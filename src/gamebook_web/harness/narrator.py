from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from gamebook_web.harness.scene import Choice, Scene


@dataclass
class NarratorContext:
    """Engine state snapshot read before narrating a turn.

    Pure narrator (spec 009, ADR-033): the narrator has zero tools. All
    numeric grounding comes from this context — either ``turn_outcome`` (the
    deterministic dispatcher's settled result for this turn, if the player's
    action had mechanical stakes) or the plain ``character``/``world``
    snapshot (Principle I — numbers are never invented in prose, they're
    handed in as already-computed fact).
    """

    character: dict[str, Any] | None = None
    world: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    recent_events: list[dict[str, Any]] = field(default_factory=list)

    # The current turn's TurnOutcome (harness/dispatcher.py), if the player's
    # action was classified as mechanical — None for a narrative-free turn.
    turn_outcome: dict[str, Any] | None = None
    choice: str | int | None = None


@runtime_checkable
class NarratorBackend(Protocol):
    """The narrator port. ``PydanticNarrator`` and ``FakeNarrator`` both satisfy it."""

    async def narrate(
        self,
        campaign_id: str,
        context: NarratorContext,
    ) -> Scene:
        """Produce the next ``Scene`` given the campaign id and engine context."""
        ...


_DEFAULT_OPENING_SCENE = Scene(
    narrative=(
        "Your adventure begins. The world stretches out before you, "
        "full of danger and possibility. What will you do first?"
    ),
    choices=[
        Choice(id="1", label="Press on"),
        Choice(id="2", label="Look around carefully"),
        Choice(id="3", label="Rest and gather your thoughts"),
    ],
)

_DEFAULT_FOLLOWUP_SCENE = Scene(
    narrative=(
        "You continue forward. The path ahead forks — "
        "one way looks safer, the other more direct."
    ),
    choices=[
        Choice(id="1", label="Take the safer route"),
        Choice(id="2", label="Push straight ahead"),
    ],
)


class FakeNarrator:
    """Deterministic narrator for tests — no LLM, no MCP, no I/O.

    Scenes are consumed in order from the queue; once exhausted, alternates
    between the built-in opening and follow-up defaults so the play loop can
    run indefinitely.
    """

    def __init__(self, scenes: list[Scene] | None = None) -> None:
        self._queue: list[Scene] = list(scenes) if scenes else []
        self._call_count: int = 0

    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:  # noqa: ARG002
        self._call_count += 1
        if self._queue:
            return self._queue.pop(0)
        if self._call_count % 2 == 1:
            return _DEFAULT_OPENING_SCENE
        return _DEFAULT_FOLLOWUP_SCENE


def get_narrator(request: Any) -> NarratorBackend:  # noqa: ANN401
    """FastAPI dependency: return the active narrator from app state."""
    narrator = getattr(request.app.state, "narrator", None)
    if narrator is None:
        raise RuntimeError(
            "Narrator not configured — check app lifespan or test fixture."
        )
    return narrator
