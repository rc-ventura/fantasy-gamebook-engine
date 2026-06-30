"""Scene — the validated narrator structured-output unit (CONTRACTS.md §10).

``Scene`` is the contract between the narrator (swap boundary #3) and the
frontend / API client.  After the narrator tool-use refactor (ADR-029), the
narrator calls MCP tools directly during generation and narrates real results.
The ``Scene`` carries only the prose and player choices — no deferred
engine operations.

Invariants (CONTRACTS.md §10):
- ``narrative`` is non-empty.
- ``choices`` may be empty only on terminal scenes (death/victory).
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class Choice(BaseModel):
    """A numbered option offered to the player."""

    id: str    # stable id for the UI / API ("1", "2", …)
    label: str  # what the player sees


class Scene(BaseModel):
    """Validated narrator output for one turn.

    The narrator calls MCP tools during generation, sees real results, and
    incorporates them into the narrative. The Scene carries the final prose
    and player choices — all state changes already happened during narration.
    """

    narrative: str
    choices: list[Choice] = []

    @field_validator("narrative")
    @classmethod
    def narrative_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("narrative must not be empty")
        return v

    @property
    def is_terminal(self) -> bool:
        """True for death/victory scenes (no player choices)."""
        return len(self.choices) == 0
