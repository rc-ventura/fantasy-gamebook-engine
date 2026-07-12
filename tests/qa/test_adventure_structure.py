"""Structural validator for adventure modules (spec 009, US4 — FR-010/FR-011).

Every adventure module under ``adventure_modules/`` is validated against the
rules in ``specs/009-deterministic-turn-dispatcher/contracts/adventure-module-schema.md``:

- Every zone referenced in ``probabilistic_encounters`` appears in ``backbone.zones``.
- No zone is in both ``probabilistic_encounters`` and ``narrative_zones``.
- Every ``template`` reference resolves in the shared ``templates.yaml``.
- Every ``probability`` is in [0.0, 1.0].
- Every encounter's ``params`` keys are valid for its template's declared ``ParamSpec``s.
- ``reviewed_by`` and ``reviewed_at`` are both present (FR-011 — human sign-off gate).

T039: this file is run alongside the existing plugability audit. To add it to the
mandatory pre-merge suite, update the CLAUDE.md "Build/test/run" section with:

    uv run pytest tests/qa/test_adventure_structure.py -q

T041 (shared templates): the validator checks that a second adventure module
(``_HYPOTHETICAL_MODULE`` below) can reference existing templates without
defining new ones — proving the library is shared, not per-module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from gamebook_web.harness.adventure_structure import (
    AdventureStructure,
    MechanicalSituationTemplate,
    ProbabilisticEncounter,
    load_adventure_structure,
    load_templates,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parents[2]
_ADVENTURE_MODULES_DIR = _REPO_ROOT / "adventure_modules"
_TEMPLATES_PATH = _ADVENTURE_MODULES_DIR / "templates.yaml"
_IGNAROK_DIR = _ADVENTURE_MODULES_DIR / "ignarok"


# ---------------------------------------------------------------------------
# Validator implementation (used both by the parameterized test and directly)
# ---------------------------------------------------------------------------


def validate_adventure_module(
    adventure: AdventureStructure,
    templates: dict[str, MechanicalSituationTemplate],
    module_name: str = "<unknown>",
) -> list[str]:
    """Return a list of validation error strings; empty list means valid."""
    errors: list[str] = []
    zone_set = set(adventure.zones)
    narrative_zone_set = set(adventure.narrative_zones)

    # --- FR-010a: every probabilistic encounter zone exists in backbone.zones ---
    for zone in adventure.probabilistic_encounters:
        if zone not in zone_set:
            errors.append(
                f"[{module_name}] probabilistic_encounters zone '{zone}' "
                f"not found in backbone.zones"
            )

    # --- FR-010b: no zone is in both probabilistic_encounters and narrative_zones ---
    both = set(adventure.probabilistic_encounters) & narrative_zone_set
    for zone in sorted(both):
        errors.append(
            f"[{module_name}] zone '{zone}' is in both probabilistic_encounters "
            f"and narrative_zones — it can only be in one"
        )

    # --- FR-010c: narrative_zones zones exist in backbone.zones ---
    for zone in adventure.narrative_zones:
        if zone not in zone_set:
            errors.append(
                f"[{module_name}] narrative_zones zone '{zone}' "
                f"not found in backbone.zones"
            )

    # --- FR-010d: every template reference resolves in templates.yaml ---
    for zone, encounters in adventure.probabilistic_encounters.items():
        for enc in encounters:
            if enc.template not in templates:
                errors.append(
                    f"[{module_name}] encounter '{enc.id}' in zone '{zone}' "
                    f"references unknown template '{enc.template}'"
                )

    # --- FR-010e: every probability is in [0.0, 1.0] ---
    for zone, encounters in adventure.probabilistic_encounters.items():
        for enc in encounters:
            if not (0.0 <= enc.probability <= 1.0):
                errors.append(
                    f"[{module_name}] encounter '{enc.id}' in zone '{zone}' "
                    f"has probability {enc.probability} outside [0.0, 1.0]"
                )

    # --- FR-010f: params keys are a subset of the template's declared ParamSpecs ---
    for zone, encounters in adventure.probabilistic_encounters.items():
        for enc in encounters:
            tmpl = templates.get(enc.template)
            if tmpl is None:
                continue  # already reported above
            declared_keys = set(tmpl.params.keys())
            unknown_params = set(enc.params.keys()) - declared_keys
            if unknown_params:
                errors.append(
                    f"[{module_name}] encounter '{enc.id}' in zone '{zone}' "
                    f"has params {sorted(unknown_params)} not declared in "
                    f"template '{enc.template}' (declared: {sorted(declared_keys)})"
                )

    # --- FR-011: human review sign-off fields ---
    if adventure.reviewed_by is None or adventure.reviewed_at is None:
        errors.append(
            f"[{module_name}] missing human review sign-off: "
            f"reviewed_by={adventure.reviewed_by!r}, reviewed_at={adventure.reviewed_at!r}. "
            f"Set both fields after a human has reviewed the module content."
        )

    return errors


# ---------------------------------------------------------------------------
# Parameterized test over all installed adventure modules
# ---------------------------------------------------------------------------


def _find_adventure_modules() -> list[Path]:
    """Return all subdirectories of adventure_modules/ that contain backbone.yaml."""
    if not _ADVENTURE_MODULES_DIR.exists():
        return []
    return sorted(
        d for d in _ADVENTURE_MODULES_DIR.iterdir()
        if d.is_dir() and (d / "backbone.yaml").exists()
    )


_MODULES = _find_adventure_modules()


@pytest.mark.skipif(not _MODULES, reason="No adventure modules found under adventure_modules/")
@pytest.mark.parametrize("module_dir", _MODULES, ids=lambda p: p.name)
def test_adventure_module_structure(module_dir: Path) -> None:
    """Every adventure module's backbone.yaml must pass the structural validator."""
    if not _TEMPLATES_PATH.exists():
        pytest.skip("Shared templates.yaml not found — cannot validate template references")

    from gamebook_web.harness.adventure_structure import load_templates
    templates = load_templates(_TEMPLATES_PATH)

    adventure = load_adventure_structure(module_dir)
    errors = validate_adventure_module(adventure, templates, module_name=module_dir.name)

    assert not errors, (
        f"Adventure module '{module_dir.name}' failed structural validation:\n"
        + "\n".join(f"  - {e}" for e in errors)
    )


# ---------------------------------------------------------------------------
# T041 — Shared template library: a second module can reference existing
# templates without defining new ones.
# ---------------------------------------------------------------------------

_HYPOTHETICAL_MODULE = AdventureStructure(
    zones=["entry_hall", "crystal_vault", "boss_chamber", "garden"],
    boss="crystal_golem",
    victory_condition={"flag": "crystal_golem_defeated"},
    opening_location="entry_hall",
    probabilistic_encounters={
        "entry_hall": [
            ProbabilisticEncounter(
                id="wandering_guard",
                probability=0.6,
                template="combat",
                params={"enemies": [{"name": "Guard", "skill": 5, "stamina": 4}], "flee_allowed": True},
            ),
        ],
        "crystal_vault": [
            ProbabilisticEncounter(
                id="pressure_trap",
                probability=0.5,
                template="risky_action",
                params={"risk_amount": 2, "risk_source": "trap"},
            ),
        ],
    },
    narrative_zones=["garden"],
    reviewed_by="test-author",
    reviewed_at="2026-07-11",
)


@pytest.mark.skipif(not _TEMPLATES_PATH.exists(), reason="Shared templates.yaml not found")
def test_second_module_can_use_shared_templates_without_new_definitions() -> None:
    """T041: A hypothetical second adventure module validates using only the
    shared template library — no new template definitions required, proving
    the library is genuinely shared (SC-004).
    """
    templates = load_templates(_TEMPLATES_PATH)
    errors = validate_adventure_module(
        _HYPOTHETICAL_MODULE, templates, module_name="hypothetical_crystal_keep"
    )
    assert not errors, (
        "A second adventure module that only references existing shared templates "
        "should pass validation without any new template definitions:\n"
        + "\n".join(f"  - {e}" for e in errors)
    )


# ---------------------------------------------------------------------------
# Unit tests for the validator itself (edge cases)
# ---------------------------------------------------------------------------


class TestValidatorEdgeCases:
    """Verify the validator catches specific error conditions."""

    def _base_adventure(self, **kwargs: Any) -> AdventureStructure:
        defaults: dict[str, Any] = dict(
            zones=["zone_a", "zone_b"],
            boss="boss",
            victory_condition={"flag": "boss_defeated"},
            opening_location="zone_a",
            reviewed_by="reviewer",
            reviewed_at="2026-07-11",
        )
        defaults.update(kwargs)
        return AdventureStructure(**defaults)

    def _templates(self) -> dict[str, MechanicalSituationTemplate]:
        if _TEMPLATES_PATH.exists():
            return load_templates(_TEMPLATES_PATH)
        return {}

    def test_encounter_in_unknown_zone_is_flagged(self) -> None:
        adventure = self._base_adventure(
            probabilistic_encounters={
                "ghost_zone": [
                    ProbabilisticEncounter(
                        id="ghost", probability=0.5, template="combat",
                        params={"enemies": [{"name": "Ghost", "skill": 3, "stamina": 2}], "flee_allowed": True},
                    )
                ]
            }
        )
        errors = validate_adventure_module(adventure, self._templates())
        assert any("ghost_zone" in e for e in errors)

    def test_zone_in_both_sections_is_flagged(self) -> None:
        adventure = self._base_adventure(
            probabilistic_encounters={
                "zone_a": [
                    ProbabilisticEncounter(id="enc", probability=0.5, template="combat", params={})
                ]
            },
            narrative_zones=["zone_a"],
        )
        errors = validate_adventure_module(adventure, self._templates())
        assert any("zone_a" in e and "both" in e for e in errors)

    def test_missing_reviewed_fields_is_flagged(self) -> None:
        adventure = self._base_adventure(reviewed_by=None, reviewed_at=None)
        errors = validate_adventure_module(adventure, self._templates())
        assert any("review" in e.lower() for e in errors)

    def test_invalid_probability_rejected_by_schema(self) -> None:
        """probability=1.5 is caught at construction time by Pydantic — the
        validator never sees it (Field(ge=0.0, le=1.0) enforces the range).
        This is a feature: invalid values cannot enter the system at all.
        """
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="less_than_equal"):
            ProbabilisticEncounter(id="enc", probability=1.5, template="combat", params={})

    def test_boundary_probability_one_is_accepted(self) -> None:
        """probability=1.0 (always present) is the valid upper boundary — no error."""
        adventure = self._base_adventure(
            probabilistic_encounters={
                "zone_a": [
                    ProbabilisticEncounter(id="enc", probability=1.0, template="combat", params={})
                ]
            }
        )
        errors = validate_adventure_module(adventure, self._templates())
        prob_errors = [e for e in errors if "probability" in e]
        assert not prob_errors, f"probability=1.0 should not be flagged: {prob_errors}"

    def test_unknown_template_reference_is_flagged(self) -> None:
        adventure = self._base_adventure(
            probabilistic_encounters={
                "zone_a": [
                    ProbabilisticEncounter(id="enc", probability=0.5, template="nonexistent_tmpl", params={})
                ]
            }
        )
        templates = self._templates()
        errors = validate_adventure_module(adventure, templates)
        assert any("nonexistent_tmpl" in e for e in errors)

    def test_valid_module_produces_no_errors(self) -> None:
        templates = self._templates()
        errors = validate_adventure_module(_HYPOTHETICAL_MODULE, templates, "hypothetical")
        assert not errors, f"A valid module should produce no errors: {errors}"
