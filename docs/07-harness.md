# 07 — Module `harness` (the master / narrator) ⭐

## Responsibility
Be the **master**: converse with the player, narrate, propose choices, read the adventure
module, and call the MCP for everything numeric or state-related. This is swap boundary #3:
Claude Code (Phase 1) ↔ PydanticAI/FastAPI (Phase 2), reusing the same MCP.

## Exposed interface (master behavior contract)
Not a code API — a **behavior contract** (lives in SKILL.md / system prompt):

```
SESSION OPENING:
  read_character_sheet + read_world + read_events + read_summary  BEFORE narrating.
  no living character -> offer create_character.
  living character -> resume from the exact point (never restart from zero).

NORMAL TURN:
  narrate 2–4 paragraphs, 2nd person, adventure module's tone;
  end with numbered choices; accept free text;
  every state change -> via MCP;
  NEVER roll dice in prose -> always roll_dice / test_luck.

COMBAT ENCOUNTER:
  delegate to the combat sub-agent (pass hero, enemies, flee_allowed);
  receive FinalResult; narrate victory or death.

CONTEXT CONTROL:
  every N turns compact the summary (update_summary);
  hard facts migrate to world/events (structured), not just prose.

END-STATES:
  death -> archive to graveyard, game over;
  module victory flag -> epilogue + hall of fame.
```

## Sub-components (Phase 1, Claude Code)
- `SKILL.md` of the **master** (tone + turn format).
- `SKILL.md` of the **combat sub-agent** (lean, combat rules only).
- `CLAUDE.md` (session-opening rule).

## Dependencies (contract only)
- MCP tool contract from `mcp` (05).
- `AdventureModule` contract from module 06.

## Pluggability ⭐
- **Phase 1:** Claude Code consumes the MCP + skills.
- **Phase 2:** PydanticAI agent with **structured output** — defines a `Scene` type
  ({ narrative, choices[], effects[] }) that the frontend renders. Same MCP, same adventure module.

## Definition of done
- A session plays opening → exploration → combat → end without the master inventing numbers.
- Swapping the harness requires no changes to MCP or adventure module.
