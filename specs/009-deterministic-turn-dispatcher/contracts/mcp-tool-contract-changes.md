# Contract: MCP tool changes — 009

**Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md) | **Authoritative source**:
`docs/CONTRACTS.md` §6 (this document proposes the delta to merge there in the same
change that implements it, per Constitution Principle III)

---

## New tools (added to the 18-tool contract, taking it to 20)

| tool | params | returns |
|---|---|---|
| `apply_healing` | `campaign_id: str, amount: int, source: str` | `CharacterSheet` — `stamina.current += amount`, clamped to `initial` (existing `Attribute` invariant) |
| `apply_damage` | `campaign_id: str, amount: int, source: str` | `CharacterSheet` — `stamina.current -= amount`, clamped to `0`; `alive=False` if it reaches `0` |

Both are **relative**, not absolute — the caller supplies a delta, never a target value.
`amount` MUST be a positive integer; the tool rejects `amount <= 0` (use the other tool
instead of a negative amount). `source` is free text for `Event`/audit purposes, not
validated against an enum at the tool layer (the *template* schema bounds `source` to a
closed enum before the dispatcher ever calls the tool — see `data-model.md`'s
`MechanicalSituationTemplate`).

## Unchanged tools

All 18 existing tools (`docs/CONTRACTS.md` §6) keep their exact signatures and
semantics. `update_character_sheet` in particular is **not removed** — lifecycle
operations (`create_character`'s initial roll, admin/debug paths) still use it. What
changes is *who is allowed to call it*: see below.

---

## Narrator toolset — empty (was: 14-tool allowlist)

`_NARRATOR_ALLOWED_TOOLS` (`src/gamebook_web/harness/agent.py`) is replaced by an empty
toolset for the pure-narration `Narrate` graph node: `toolsets=[]`. The narrator receives
`TurnOutcome` + `NarratorContext` as prompt content instead of tool access. No MCP tool —
mutating or read-only — is reachable from the narrator's `agent.run()` call.

## Dispatcher's tool access

The dispatcher (graph nodes, not an LLM) calls exactly these tools via
`call_engine()`/`direct_call_tool` — the same 20-tool surface minus lifecycle-only tools
(`create_character`, `archive_character`, `save_progress`, `load_progress` stay
API-orchestrated, as they are today):

`read_character_sheet`, `read_world`, `read_events`, `read_summary`, `roll_dice`,
`test_luck`, `apply_healing`, `apply_damage`, `update_world`, `update_summary`,
`register_event`, `start_combat`, `resolve_combat_round`, `flee_combat`, `end_combat`.

No `ScopedMCPToolset` behavior changes — `campaign_id` injection (ADR-018 D2) applies
identically regardless of whether the caller is a narrator agent or a dispatcher node.

---

## Backward compatibility

`FakeNarrator` (test double, `harness/base.py`) is unaffected — it never called real
tools. Existing tests that assert on the old `_NARRATOR_ALLOWED_TOOLS` allowlist need
updating to assert an empty narrator toolset instead; tests that exercise
`update_character_sheet`/combat tools directly (engine-layer tests, `tests/engine`,
`tests/server`) are unaffected — the tools' own contracts don't change.
