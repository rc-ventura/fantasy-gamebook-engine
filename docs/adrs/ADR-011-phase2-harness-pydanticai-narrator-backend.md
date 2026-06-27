# ADR-011: Phase-2 production harness — PydanticAI core, model/provider-agnostic, behind a NarratorBackend port

**Status**: Accepted
**Date**: 2026-06-26
**Related spec**: [001-web-platform-migration](../../specs/001-web-platform-migration/) — Phase 2, swap boundary #3 (harness)

---

## Context

Phase 1 uses Claude Code as the narrator/master (module 07). Phase 2 must replace it with a
**programmatic, web-servable narrator** that consumes the **same MCP tool contract** and emits a
Pydantic-validated `Scene` (`{ narrative, choices[], effects[] }`), per `docs/07-harness.md`.

Two forces shape the choice:

1. **Model/provider agnosticism** is a requirement — we must be able to swap the LLM (Opus, Sonnet,
   Haiku, or non-Claude via OpenRouter) without rewriting the harness.
2. The constitution's **Principle I ("numbers never in prose")** must hold regardless of which model
   runs. That guarantee lives in the *Scene validation + MCP execution* boundary, not in the model —
   so the framework must make that boundary easy to enforce in code.

The existing engine is a **FastMCP** server over stdio and the domain is **Pydantic v2**, so the
narrator framework should integrate with both with minimal impedance.

## Decision

Build the Phase-2 narrator on **PydanticAI core (`Agent`)**, behind a thin **`NarratorBackend`
port** so a deterministic `FakeNarrator` can be injected for tests (Principle IV). Model/provider is
selected by the PydanticAI **model string** and injected at startup — not hardcoded across the code.

PydanticAI features used, each mapping 1:1 to a harness need:

- `MCPToolset(StdioTransport(...))` — consume the **existing FastMCP server** (it imports
  `fastmcp`'s `StdioTransport`; zero impedance, engine unchanged).
- `output_type=Scene` — structured output; PydanticAI re-prompts on schema-validation failure.
- An **`output_validator` raising `ModelRetry`** — rejects any `Scene` carrying a literal number,
  making Principle I a **code invariant** that is independent of the model.
- **Agent delegation** (a combat subagent called inside a tool, sharing `ctx.usage`) — the
  combat sub-agent pattern of [ADR-001](./ADR-001-combat-sub-agent-delegation-pattern.md).
- `deps_type` / `RunContext` — inject `campaign_id` + the MCP toolset per request (type-safe).
- `run_stream` — progressive narration UX; `UsageLimits` — per-turn cost guardrails.

The harness is **stateless between turns**: game state is the engine's, read via MCP
(`read_summary` / `read_events`) at the start of each turn. We do **not** rely on PydanticAI
`message_history` for game state.

Default model tier: `anthropic:claude-opus-4-8` (quality), Sonnet 4.6 (volume), Haiku 4.5 (cheap
subtasks); OpenRouter is a valid alternate route behind the same port.

## Alternatives considered

### Alternative A: LangChain `deepagents` (the "deep agent" library)

The pattern of planner tool + subagents + virtual filesystem + long-horizon autonomous loop, on
LangGraph.

**Why not chosen**:
- A gamebook turn is **bounded and structured** (read state → narrate → `Scene` → apply effects),
  not an open-ended long-horizon task that needs a planner or a virtual filesystem.
- The "memory/planning" it provides **already lives in the engine** (summary, events, world flags).
- Brings the LangChain + LangGraph weight for no domain benefit.

**Advantages (not leveraged)**: built-in planning, subagents, and scratchpad filesystem — useful for
much more open-ended autonomous workloads than a turn-based narrator.

### Alternative B: Hand-rolled agent loop on the raw Anthropic SDK

**Why not chosen**:
- More code to own, and provider-agnosticism would be **manual** (per-provider adapters).
- PydanticAI gives structured output + MCP client + agnosticism natively while staying
  Pydantic-native (matching the existing domain).

**Advantages (not leveraged)**: maximum control and the fewest dependencies.

### Alternative C: `pydantic-ai-harness` (official capability lib) — CodeMode

`pydantic-ai-harness` is Pydantic AI's official **capability** package ("batteries"); its flagship
capability **CodeMode** lets the agent write/execute sandboxed Python to orchestrate many tool calls
in one model round-trip.

**Why not chosen (deferred, not adopted in v1)**:
- Per-turn tool fan-out is **small** (read state, a roll, maybe a luck test, an update, an event) —
  CodeMode pays off with *many* calls per round-trip.
- Combat is **interactive** (the player decides whether to test luck between rounds), which a single
  code-orchestrated block does not fit.
- CodeMode routes tool calls **inside code**, bypassing the `Scene.effects[]` + `output_validator`
  gate that enforces Principle I — a direct **tension** with our safety model.
- Adds a code-sandbox dependency for marginal gain.

> Terminology note: `pydantic-ai-harness` "harness" = optional capability batteries, **not** our
> module-07 narrator harness. Keep CodeMode on the radar for a future tool-heavy, non-interactive
> step (e.g. adventure generation).

## Consequences

### Accepted

- Reuses the **existing FastMCP engine unchanged** (Principles II & III).
- **Principle I becomes a code invariant** via `output_validator`, independent of the model.
- The model is swappable by **config**, satisfying the agnosticism requirement.
- Combat delegation **preserves ADR-001's pattern**.
- Testable via a `FakeNarrator` behind the `NarratorBackend` port (Principle IV).

### Trade-offs

- Depends on **PydanticAI**, a fast-moving library.
- Non-Anthropic routes (e.g. OpenRouter) lose some Claude-native niceties (native MCP, prompt
  caching, adaptive thinking) and may show higher `Scene`-validation retry rates — the `Scene` gate
  still protects correctness.

### Conditions that invalidate this decision

This decision should be **revisited** if:

1. A future phase introduces a genuinely tool-heavy, **non-interactive** step (e.g. procedural
   adventure generation) where CodeMode's many-calls-per-round-trip pays off.
2. PydanticAI's API diverges enough that the `NarratorBackend` port can no longer hide it cleanly.

### Migration path when needed

The `NarratorBackend` port is the seam: swap the concrete implementation (PydanticAI → hand-rolled,
or add an `OpenRouterNarrator`) without touching the engine, MCP contract, or the `Scene` schema.

## References

- Spec & plan: `specs/001-web-platform-migration/` (`research.md` §2, `contracts/scene.md`)
- [ADR-001 — Combat sub-agent delegation pattern](./ADR-001-combat-sub-agent-delegation-pattern.md)
- `docs/07-harness.md` (Phase-2 harness intent), `.specify/memory/constitution.md` (Principle I)
- PydanticAI docs (Agent, MCPToolset, output validators, agent delegation); `pydantic-ai-harness`
  (capability lib / CodeMode)
