# The narrator can loop inside a zone indefinitely without ever narrating toward an exit — mechanically correct classification, narratively stuck

**Context:** Discovered during spec 009 (`feat/009-deterministic-turn-dispatcher`), while sweeping the backend's docker logs after a real, moderately long live-play session (13 turns, campaign `382f369c-c0a2-429e-bc18-0a7dee78ced6`, real Postgres + real Dex OIDC + real `openai:gpt-4o-mini`, `docker compose --profile gameobs`), run by the user after that session's SDD-final-review fixes had been implemented.
**Date:** 2026-07-11
**Future intent:** Inform a later game-mechanic / narrator-prompt-design adjustment pass. Deliberately **not implemented now** — the user explicitly asked to leave current narrator/choice behavior untouched for the moment and only wanted this documented for a future tuning session.

---

## What happened

Every single `encounter_roll` audit log line (added earlier the same day, T046) across the entire 13-turn, ~8-minute session showed `zone=stone_archway`. The player never left the starting zone — despite `move` to the only adjacent zone (`shattered_trailhead`) being a valid, correctly-configured classifier candidate on every single turn (`candidates=5` every turn; the adjacency guard and the classifier params-fill fix from the same day both independently confirmed working in isolation, in unrelated shorter test sessions run earlier).

This is **not a code defect**. Tracing the actual `classify_intent`/`mechanical_dispatch` log lines for the session shows the dispatcher behaved exactly as designed at every step:

```
choice='3' label='Begin the climb'                                                    → action=None,        confidence=0.00 → narrative
choice='3' label='Continue up the switchback and begin the climb.'                    → action=None,        confidence=0.45 → narrative
choice='1' label='Pick through the broken scaffolding and timbers...'                 → action=None,        confidence=0.25 → narrative
choice='3' label='Examine the claw-marks on the rock more closely.'                   → action=None,        confidence=0.95 → narrative
choice='1' label='Examine the trailhead more broadly.'                                → action=skill_check, confidence=0.90 → mechanical (risk_amount=1)
choice='2' label='Examine the claw-marks above the switchback.'                       → action=skill_check, confidence=0.87 → mechanical (risk_amount=1)
choice='1' label='1 — Attempt to climb the archway to reach the claw-marks.'           → action=skill_check, confidence=0.86 → mechanical (risk_amount=2)
choice='1' label='Climb higher along the ledge to follow the claw-marks deeper...'     → action=skill_check, confidence=0.90 → mechanical (risk_amount=2)
```

The classifier correctly read these as risky **local** actions ("climb the ledge," "examine the claw-marks") rather than a zone departure, because that is genuinely what the narrator's own text described. The classification quality itself was accurate turn after turn — the story simply never converged on offering a clean "you now leave this area" choice. Compare to every other test session run earlier the same day (see `docs/learning-lessons/one_live_validation_session_is_not_a_regression_suite.md`), all of which were short, deliberate playthroughs (1-3 turns per zone) where the player explicitly chose or typed an unambiguous "move on" phrasing — the pattern above only surfaced once a real session ran long enough for the narrator to keep elaborating in place instead.

## Measured consequence

The character's stamina went from **17 (initial) to 15 (current)** — confirmed via a direct Postgres query on `character_sheet` — purely from repeated `skill_check` dispatches accumulated while the player made zero narrative or zone progress. Not fatal or urgent in this instance, but it demonstrates a real "treadmill": mechanical risk (real stamina loss, from the real engine, correctly gated — no invented numbers, ADR-033 held throughout) can accumulate indefinitely while the player experiences no forward story movement, because nothing in the current design gives the narrator pressure to eventually offer — or gives the player a way to force — a definitive zone-exit choice.

## A related, secondary, non-blocking observation

A **"Check your gear (/hero)"** narrator-generated numbered choice appeared twice in the same session and was — correctly — classified both times as non-mechanical (`action=None`, routed to free narration). Technically correct dispatcher behavior, but a UX/game-design redundancy: the frontend already has a dedicated **Backpack** tab in the main navigation for exactly this, so the narrator re-offering it as a story choice produces a narrative dead end (clicking it just gets a free-form non-answer) that duplicates existing, better-designed UI. Per explicit instruction this was **not** touched — noted here only for a future tuning discussion.

## Why only live testing surfaced this

No mocked/scripted-model unit test in this repo's suite (`FunctionModel`/`TestModel`-backed, one canned response per call) can surface a multi-turn narrative-**convergence** pattern like this — it only exists across many successive real LLM calls, where the narrator's tendency to keep elaborating local atmospheric detail compounds turn over turn instead of ever resolving toward a transition. This is a distinct discovery from `one_live_validation_session_is_not_a_regression_suite.md` (that lesson is about classifier/testing *methodology* — one validation session isn't a regression suite; this one is about narrator/game-*design* behavior over a long real session — a different failure surface, related only in that both required genuinely playing the live stack to find).

## Relation to ADRs and next steps

- **ADR-033** (numbers/events never invented in prose) held throughout — the stamina loss was real, engine-computed, correctly dispatched. This lesson is not about integrity, it's about narrative *pacing*.
- **ADR-035** (pydantic-evals offline harness) is the natural home for eventually catching this class of issue systematically — a multi-turn scenario dataset (not just single-turn classifier cases) could assert "the narrator offers a zone-exit choice within N turns of entering a zone with no remaining local content," rather than relying on someone noticing it in a live session transcript.
- **Candidate future mechanic-adjustment directions** (not implemented, for later discussion):
  1. Give the narrator's system prompt an explicit nudge/counter-based pressure to offer a clear zone-transition choice after some number of turns spent in the same zone without one being offered or chosen.
  2. Consider a diminishing-returns or cap on accumulated `skill_check`/`risky_action` risk within the same zone visit, to bound the stamina "treadmill."
  3. Reconsider whether the narrator-generated "check your gear" choice should be suppressed/replaced given the dedicated Backpack tab already exists — a prompt/UI redundancy, not a mechanical bug.
