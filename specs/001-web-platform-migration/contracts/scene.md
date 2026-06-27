# Contract Draft — `Scene` (narrator structured output)

Feature: Web Platform Migration · Date: 2026-06-26 · Status: **draft** (to be folded into
`docs/CONTRACTS.md` per Principle III before/with implementation).

`Scene` is the structured unit the new harness produces for one turn. It is the swap-boundary-#3
contract: the narrator emits a `Scene`, the frontend renders it, and the engine applies its
`effects[]`. It is **schema-validated with Pydantic v2 before it can reach storage or the player**
(FR-014). The defining safety property: a `Scene` carries **no narrator-fabricated numbers** — its
`effects[]` reference engine operations, and every numeric outcome comes from an MCP tool result
(Principle I).

## Shape

```text
Scene
├── narrative : str            # 2–4 paragraphs, 2nd person, adventure-module tone
├── choices   : Choice[]       # numbered options offered to the player (free text also accepted)
└── effects   : Effect[]       # engine operations to apply this turn (NOT literal stat values)

Choice
├── id        : str            # stable id for the UI / API ("1", "2", ...)
└── label     : str            # what the player sees

Effect  (discriminated union by `type` — each maps to an MCP tool, never a narrated number)
├── type: "roll_dice"          → params: { notation }            # engine returns the roll
├── type: "test_luck"          → params: {}                      # engine resolves + decrements luck
├── type: "update_character"   → params: { field, delta|set }    # engine enforces invariants
├── type: "register_event"     → params: { payload }             # append hard fact
├── type: "update_world"       → params: { location?, flags? }   # world write via MCP
├── type: "start_combat"       → params: { enemies[], flee_allowed }
├── type: "resolve_combat_round"→ params: { test_luck: bool }
├── type: "flee_combat"        → params: {}
└── type: "end_combat"         → params: {}
```

## Validation rules (Pydantic v2)
- `narrative` non-empty; `choices` may be empty only on terminal scenes (death/victory).
- `effects[].type` must be one of the known engine operations (closed enum / discriminated union).
- No `Effect` may carry a literal resulting stat/dice value — only operation parameters. The engine
  computes outcomes; the narrator never asserts them. A `Scene` violating this is rejected (`422
  invalid_scene`) and never persisted.
- The set of `Effect.type` values **must stay in lockstep with the MCP tool contract**
  (`docs/CONTRACTS.md` §6). Adding an effect type requires a corresponding MCP tool and a
  CONTRACTS.md update (Principle III).

## Lifecycle
1. Player submits a choice/free text → `POST /campaigns/{id}/turn`.
2. Narrator loop (claude-opus-4-8) reads engine state via MCP, decides the turn, and emits a `Scene`.
3. `Scene` is validated; its `effects[]` are executed through MCP (producing real numbers/state).
4. The validated `Scene` (with engine-resolved outcomes merged in for display) is returned to the UI
   and rendered; durable state lives in the engine, not in the `Scene`.

## Terminal scenes
- Death → `choices` empty, narrative is the death ending; campaign → `ended`, ArchiveRecord written.
- Victory (module flag, e.g. `malachar_defeated`) → epilogue narrative; campaign → `ended`.
- A turn on an already-`ended` campaign → `409 run_ended` (no new `Scene`).
