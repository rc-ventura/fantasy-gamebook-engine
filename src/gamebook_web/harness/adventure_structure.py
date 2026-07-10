from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Adventure structure — Layers 1 (backbone), 2 (probabilistic), 3 (narrative)
# ---------------------------------------------------------------------------


class ProbabilisticEncounter(BaseModel):
    """A Layer-2 encounter: rolled once per zone per playthrough, then
    remembered (FR-006/FR-007) — persisted to ``World.flags``, not re-decided.
    """

    id: str
    probability: float = Field(ge=0.0, le=1.0)
    template: str  # references templates.yaml
    params: dict[str, Any] = Field(default_factory=dict)


class AdventureStructure(BaseModel):
    """A module's fixed identity (Layer 1) + its per-playthrough variance
    (Layer 2) + its explicitly-free zones (Layer 3), loaded from
    ``backbone.yaml``. Every zone not listed in ``probabilistic_encounters`` or
    ``narrative_zones`` defaults to Layer 3 (incremental migration).
    """

    zones: list[str]
    key_npcs: list[str] = Field(default_factory=list)
    boss: str
    victory_condition: dict[str, Any]
    opening_location: str
    probabilistic_encounters: dict[str, list[ProbabilisticEncounter]] = Field(
        default_factory=dict
    )
    narrative_zones: list[str] = Field(default_factory=list)

    # FR-011 — the automated structural validator (FR-010) 
    reviewed_by: str | None = None
    reviewed_at: str | None = None  # ISO-8601; set together with reviewed_by or not at all


# ---------------------------------------------------------------------------
# Mechanical situation template library (shared across every module)
# ---------------------------------------------------------------------------


class ParamSpec(BaseModel):
    """Bounds on a template parameter — what an adventure author (or the
    intent classifier resolving one at runtime) may choose, never unbounded.
    """

    type: Literal["int", "str", "bool", "list", "enum"]
    min: int | None = None
    max: int | None = None
    values: list[str] | None = None  # only meaningful when type == "enum"


class CheckStep(BaseModel):
    """One step of a template's ``mandatory_checks``: a tool call, optionally
    gated by a ``comparator``. ``comparator.op`` is a closed enum
    (``eq/ne/lt/le/gt/ge``) interpreted by the dispatcher as structured data —
    **never** ``eval()``/``exec()`` (ADR-033 structural requirement 1).
    """

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    comparator: dict[str, Any] | None = None
    on_success: list["CheckStep"] = Field(default_factory=list)
    on_failure: list["CheckStep"] = Field(default_factory=list)


class MechanicalSituationTemplate(BaseModel):
    """A reusable, named kind of game-mechanical moment (FR-009) — shared
    across every adventure module, referenced by name from
    ``probabilistic_encounters`` and by the intent classifier.
    """

    name: str
    description: str
    params: dict[str, ParamSpec] = Field(default_factory=dict)
    mandatory_checks: list[CheckStep] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Loaders — YAML -> Pydantic, fail loudly on schema violation
# ---------------------------------------------------------------------------


def load_adventure_structure(module_dir: Path) -> AdventureStructure:
    """Load and validate a module's ``backbone.yaml``.

    Raises on schema violation — fails loudly rather than silently accepting
    malformed content; feeds the FR-010 structural validator
    (``tests/qa/test_adventure_structure.py``). The YAML groups presentational
    sections (``backbone:``, ``probabilistic_encounters:``, ...) for
    readability; this loader flattens them into ``AdventureStructure``'s flat
    field set.
    """
    path = Path(module_dir) / "backbone.yaml"
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    backbone: dict[str, Any] = raw.get("backbone", {})
    merged = {
        **backbone,
        "probabilistic_encounters": raw.get("probabilistic_encounters", {}),
        "narrative_zones": raw.get("narrative_zones", []),
        "reviewed_by": raw.get("reviewed_by"),
        "reviewed_at": raw.get("reviewed_at"),
    }
    return AdventureStructure.model_validate(merged)


def load_templates(path: Path) -> dict[str, MechanicalSituationTemplate]:
    """Load the shared template library (``adventure_modules/templates.yaml``).

    Raises on schema violation. The `name` on each `MechanicalSituationTemplate`
    is the YAML mapping key, not a duplicated field inside each entry.
    """
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries: dict[str, Any] = raw.get("templates", {})
    return {
        name: MechanicalSituationTemplate.model_validate({"name": name, **spec})
        for name, spec in entries.items()
    }
