from __future__ import annotations

import logging
from typing import Any

from pydantic_ai.mcp import MCPToolset

from gamebook_web.harness.adventure_structure import ProbabilisticEncounter
from gamebook_web.mcp_host import call_engine

logger = logging.getLogger(__name__)


async def resolve_zone_encounters(
    encounters: list[ProbabilisticEncounter],
    location: str,
    toolset: MCPToolset,
    campaign_id: str,
    world_flags: dict[str, Any],
) -> list[ProbabilisticEncounter]:
    """Roll each encounter once per playthrough; reuse the persisted result on re-entry.

    Implements T033 (first-entry roll + persist) and T034 (remembered re-entry).
    Flag key pattern: ``encounter.<zone>.<encounter_id>`` — a bool in World.flags.

    Encounters with probability >= 1.0 are always active (short-circuit, no roll).
    Encounters with probability <= 0.0 are never active (short-circuit, no roll).
    """
    if not encounters:
        return []

    new_flags: dict[str, Any] = {}
    active: list[ProbabilisticEncounter] = []

    for enc in encounters:
        flag_key = f"encounter.{location}.{enc.id}"

        if flag_key in world_flags:
            # T034: remembered — re-use the persisted decision for this playthrough.
            present = bool(world_flags[flag_key])
            logger.info(
                "encounter_roll campaign=%s zone=%s encounter=%s source=remembered "
                "roll=n/a threshold=n/a present=%s",
                campaign_id, location, enc.id, present,
            )
            if present:
                active.append(enc)
            continue

        # T033: first entry — roll against the encounter's probability.
        roll_value: int | str = "n/a"
        if enc.probability >= 1.0:
            present = True
            source = "forced_always"
        elif enc.probability <= 0.0:
            present = False
            source = "forced_never"
        else:
            # Use the engine's seeded RNG. This engine (ADR-005).
            roll_result = await call_engine(
                toolset, "roll_dice",
                campaign_id=campaign_id,
                notation="1d100",
            )
            roll_value = roll_result.get("total", 100) if isinstance(roll_result, dict) else 100
            present = roll_value <= int(enc.probability * 100)
            source = "rolled"

        logger.info(
            "encounter_roll campaign=%s zone=%s encounter=%s source=%s "
            "roll=%s threshold=%s present=%s",
            campaign_id, location, enc.id, source,
            roll_value, int(enc.probability * 100), present,
        )

        new_flags[flag_key] = present
        if present:
            active.append(enc)

    if new_flags:
        await call_engine(
            toolset, "update_world",
            campaign_id=campaign_id,
            changes={"flags": new_flags},
        )

    return active
