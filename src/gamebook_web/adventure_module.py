"""Adventure-module config (swap boundary #2, FR-005).

The engine and API must not hard-code adventure-specific facts. The victory
condition is a World flag whose *name* belongs to the adventure module (the
Ignarok debut module uses ``malachar_defeated`` — see
``.claude/skills/ignarok/SKILL.md``). Swapping the adventure means swapping
this config, not editing the play loop.

``GAMEBOOK_VICTORY_FLAG`` overrides the flag name at deploy time so a new
adventure module can plug in without a code change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AdventureConfig:
    """Static adventure metadata the API layer is allowed to read."""

    name: str
    victory_flag: str


# Debut adventure module: Ignarok (docs/06-adventure-module.md).
IGNAROK = AdventureConfig(name="ignarok", victory_flag="malachar_defeated")


def get_adventure_config() -> AdventureConfig:
    """Return the active adventure config (env override wins)."""
    flag = os.getenv("GAMEBOOK_VICTORY_FLAG", "")
    if flag:
        return AdventureConfig(name=os.getenv("GAMEBOOK_ADVENTURE", IGNAROK.name), victory_flag=flag)
    return IGNAROK
