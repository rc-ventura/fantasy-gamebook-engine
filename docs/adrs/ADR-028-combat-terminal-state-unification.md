# ADR-028: Combat terminal-state check — single entry point after take_turn

**Status**: Accepted | **Date**: 2026-07-02 | **Spec**: [006-cycle1-remediation](../../specs/006-cycle1-remediation/)

> Number 028 previously held "combat resolution via agent tool + SSE stream", which was
> renumbered to [ADR-029](./ADR-029-narrator-as-tool-use-agent-eliminate-effects.md) on
> 2026-06-30 and reserved 028 for this decision.

## Context

The cycle-1 review of slice 003 found the death/victory check duplicated and divergent:
`POST /turn` checked for death but the combat-round endpoint missed the victory path, so
defeating Malachar via combat left the campaign active. The original remediation plan was
to unify the check into a shared helper called from both entry points.

Spec 007 (ADR-029) then **deleted the combat endpoints entirely**: combat resolves inside
the narrator's tool-use loop during `agent.run()`, and `POST /me/game/turn` is the only
place a turn's outcome becomes visible to the API layer.

## Decision

`_check_terminal_state` (`src/gamebook_web/api/play.py`) is the **single** terminal-state
check, and it runs once per turn, **after** the narrator returns and the API re-reads
engine state:

1. Re-read `character` and `world` post-narrate (the narrator's tool calls may have
   changed either).
2. **Death**: `character.alive == False` → archive to `graveyard`, end campaign with
   `ended_reason="death"`.
3. **Victory**: the adventure module's `victory_flag` (Ignarok: `malachar_defeated`,
   read from `adventure_module.get_adventure_config()` — never hard-coded in the API,
   FR-005/swap boundary #2) set in `world.flags` → archive to `hall_of_fame`, end
   campaign with `ended_reason="victory"`.

The original "unify between take_turn and combat_round" scope is moot — there is no
`combat_round` to unify with.

## Consequences

- One code path to test: `tests/server/test_combat_victory.py` proves a combat won
  *during* `narrate()` ends and archives the campaign on the same turn, and
  `tests/server/test_api_play_loop.py` covers the death path.
- A future second entry point (e.g. a streaming turn endpoint) MUST call the same
  helper after its final state re-read — never re-implement the checks.
- Ended campaigns are unreachable (`404 no_active_campaign`) rather than replayable.
