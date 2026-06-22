"""Combat lifecycle implementation: ``CombatService``.

Orchestrates a fight using the pure ``regras`` math and a ``StorageBackend`` to
persist the ``Combat`` and ``CharacterSheet`` between calls (so an in-progress
fight survives a restart). It contains **no game rules of its own** — all math
lives in ``regras``.

Dependency hygiene (golden rule): this module imports ``regras`` (the stable
core) and ``dominio`` at runtime, but references ``StorageBackend`` only under
``TYPE_CHECKING``. It therefore has *no* runtime dependency on the storage layer
and never imports a concrete backend (``json_storage`` / ``in_memory``); the
backend is injected at construction by the composition root.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from gamebook.combate.interfaces import (
    FinalResult,
    FleeResult,
    LuckUse,
    RoundOutcome,
)
from gamebook.dominio.models import Attribute, Combat, Enemy
from gamebook.regras import implementation as rules

if TYPE_CHECKING:
    from gamebook.regras.interfaces import RandomSource
    from gamebook.storage.interfaces import StorageBackend

# Stamina lost by the hero when fleeing (fixed by the rules).
_FLEE_DAMAGE = 2


class CombatService:
    """A ``CombatEngine`` driving one fight at a time through injected collaborators."""

    def __init__(self, storage: StorageBackend, rng: RandomSource) -> None:
        self._storage = storage
        self._rng = rng
        # Ephemeral per-combat tally of luck tests spent. Authoritative combat
        # state lives in storage; this counter only feeds the final summary and
        # resets harmlessly to 0 if the process restarts mid-fight.
        self._luck_spent: dict[str, int] = {}

    # --- Lifecycle -----------------------------------------------------------
    def start_combat(self, enemies: list[Enemy], flee_allowed: bool) -> Combat:
        if not enemies:
            raise ValueError("start_combat requires at least one enemy")
        if all(enemy.stamina <= 0 for enemy in enemies):
            raise ValueError(
                "start_combat requires at least one enemy with stamina > 0"
            )
        combat = Combat(
            combat_id=uuid.uuid4().hex,
            enemies=[enemy.model_copy(deep=True) for enemy in enemies],
            round=0,
            flee_allowed=flee_allowed,
            ended=False,
            winner=None,
        )
        self._storage.save_combat(combat)
        self._luck_spent[combat.combat_id] = 0
        return combat

    def resolve_round(self, combat_id: str, use_luck: bool) -> RoundOutcome:
        combat = self._load_active_combat(combat_id)
        sheet = self._load_character()
        enemy = self._active_enemy(combat)
        if enemy is None:
            raise ValueError(f"combat {combat_id!r} has no enemy left to fight")

        result = rules.resolve_round(sheet.skill.current, enemy.skill, self._rng)

        luck_used: LuckUse | None = None
        damage = result.base_damage

        if result.hitter != "tie":
            if use_luck:
                luck = rules.test_luck(sheet.luck.current, self._rng)
                # Persist luck -1, floored at 0 to respect the Attribute invariant.
                sheet.luck = Attribute(
                    initial=sheet.luck.initial,
                    current=max(0, luck.luck_after),
                )
                self._luck_spent[combat_id] = self._luck_spent.get(combat_id, 0) + 1
                luck_used = LuckUse(roll=luck.roll, success=luck.success)
                damage = rules.apply_luck_modifier(
                    result.hitter, result.base_damage, luck.success
                )

            if result.hitter == "hero":
                enemy.stamina = max(0, enemy.stamina - damage)
            else:  # the enemy landed the hit
                sheet.stamina = Attribute(
                    initial=sheet.stamina.initial,
                    current=max(0, sheet.stamina.current - damage),
                )

        combat.round += 1

        ended = False
        winner: str | None = None
        if sheet.stamina.current <= 0:
            sheet.alive = False
            ended, winner = True, "enemy"
        elif all(foe.stamina <= 0 for foe in combat.enemies):
            ended, winner = True, "hero"

        if ended:
            combat.ended = True
            combat.winner = winner  # type: ignore[assignment]

        self._storage.save_character(sheet)
        self._storage.save_combat(combat)

        return RoundOutcome(
            hero_as=result.hero_as,
            enemy_as=result.enemy_as,
            hitter=result.hitter,
            damage_applied=damage if result.hitter != "tie" else 0,
            hero_stamina=sheet.stamina.current,
            enemy_stamina=enemy.stamina,
            luck_used=luck_used,
            ended=ended,
            winner=winner,  # type: ignore[arg-type]
        )

    def flee(self, combat_id: str) -> FleeResult:
        combat = self._load_active_combat(combat_id)
        if not combat.flee_allowed:
            raise ValueError(f"fleeing is not allowed in combat {combat_id!r}")

        sheet = self._load_character()
        sheet.stamina = Attribute(
            initial=sheet.stamina.initial,
            current=max(0, sheet.stamina.current - _FLEE_DAMAGE),
        )
        hero_alive = sheet.stamina.current > 0
        if not hero_alive:
            sheet.alive = False

        combat.ended = True
        # Fleeing leaves no combat winner; a fatal flee is signalled by the sheet
        # (alive=False) and surfaced unambiguously by end_combat / FleeResult.
        combat.winner = None
        self._storage.save_character(sheet)
        self._storage.save_combat(combat)

        return FleeResult(
            damage_taken=_FLEE_DAMAGE,
            hero_stamina=sheet.stamina.current,
            ended=True,
            hero_alive=hero_alive,
        )

    def end_combat(self, combat_id: str) -> FinalResult:
        combat = self._storage.load_combat(combat_id)
        if combat is None:
            raise ValueError(f"no combat with id {combat_id!r}")

        sheet = self._load_character()
        if combat.winner == "enemy":
            sheet.alive = False
        # Victory or flight: the hero's stamina was already persisted per round;
        # re-persisting here keeps end_combat idempotent and the sheet canonical.
        self._storage.save_character(sheet)

        # Unambiguous death signal: a non-living hero always reports the enemy as
        # winner — this covers death in combat AND a fatal flee (where
        # combat.winner is None). winner stays None only for a safe escape.
        winner = "enemy" if not sheet.alive else combat.winner

        result = FinalResult(
            winner=winner,  # type: ignore[arg-type]
            hero_final_stamina=sheet.stamina.current,
            luck_spent=self._luck_spent.pop(combat_id, 0),
            rounds=combat.round,
            drops=None,
        )
        self._storage.remove_combat(combat_id)
        return result

    # --- Internal helpers ----------------------------------------------------
    def _load_active_combat(self, combat_id: str) -> Combat:
        combat = self._storage.load_combat(combat_id)
        if combat is None:
            raise ValueError(f"no combat with id {combat_id!r}")
        if combat.ended:
            raise ValueError(f"combat {combat_id!r} has already ended")
        return combat

    def _load_character(self):
        sheet = self._storage.load_character()
        if sheet is None:
            raise ValueError("no character sheet available for this combat")
        return sheet

    @staticmethod
    def _active_enemy(combat: Combat) -> Enemy | None:
        for enemy in combat.enemies:
            if enemy.stamina > 0:
                return enemy
        return None


__all__ = ["CombatService"]
