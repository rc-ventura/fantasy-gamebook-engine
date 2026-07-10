
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AdventureConfig:
    """Static adventure metadata the API layer is allowed to read."""

    name: str
    victory_flag: str
    opening_location: str = ""


# Debut adventure module: Ignarok (docs/06-adventure-module.md).
IGNAROK = AdventureConfig(name="ignarok", victory_flag="malachar_defeated", opening_location="stone_archway")


def get_adventure_config() -> AdventureConfig:
    """Return the active adventure config (env override wins)."""
    flag = os.getenv("GAMEBOOK_VICTORY_FLAG", "")
    if flag:
        return AdventureConfig(name=os.getenv("GAMEBOOK_ADVENTURE", IGNAROK.name), victory_flag=flag)
    return IGNAROK
