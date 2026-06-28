# ADR-014: pydantic-ai 2.0 MCPToolset pattern — `direct_call_tool` for routes, `toolsets=[]` for agents

**Status**: Accepted  
**Date**: 2026-06-27  
**Related spec**: [003-web-backend-mvp](../../specs/003-web-backend-mvp/)

---

## Context

The web backend (slice 003) needs to call MCP tools in two distinct contexts:

1. **Route-level direct calls** — FastAPI route handlers call MCP tools directly:
   `create_character`, `read_character_sheet`, `read_world`, `start_combat`,
   `resolve_combat_round`, `end_combat`, `archive_character`, etc.

2. **Agent calls** — The PydanticAI narrator agent calls MCP tools autonomously
   during its generation loop (reading state, proposing effects).

When this slice was implemented, `pydantic-ai` resolved to **2.0.0** (the package
jumped from 0.0.x pre-releases to a 2.0 stable release).  The API changed in
relevant ways:

- `MCPToolset(client)` accepts a `ClientTransport` *or* a `FastMCP` server
  directly (no `StdioServerParameters` from the `mcp` library needed).
- `StdioTransport` is provided by `pydantic_ai.mcp`, not the `mcp` library.
- Direct tool calls from outside an agent run are supported via
  `MCPToolset.direct_call_tool(name, args)`.
- For agent runs, `toolsets=[mcp_toolset]` is passed to `Agent.run(...)`.

## Decision

### Route-level calls: `MCPToolset.direct_call_tool`

The application enters an `MCPToolset` once at startup (FastAPI lifespan) and
stores it in `app.state.engine_toolset`.  Route handlers call:

```python
result = await toolset.direct_call_tool(tool_name, arguments)
```

This reuses the live MCP connection without re-entering the toolset context.

### Agent runs: `toolsets=[toolset]`

The `PydanticNarrator` passes the same already-entered toolset to `agent.run()`:

```python
result = await self._agent.run(prompt, toolsets=[self._toolset])
```

The agent is created WITHOUT a toolset in `__init__`; the toolset is injected
per-run so the same shared connection is used.

### Test injection: `set_engine_toolset_factory`

Tests inject an in-process `MCPToolset(FastMCP_server)` instead of a subprocess:

```python
from gamebook_web import mcp_host
mcp_host.set_engine_toolset_factory(lambda: MCPToolset(build_server(...)))
```

The FastAPI lifespan calls the factory and enters the toolset — same code path
as production, different backend (in-process FastMCP + InMemoryStorage).

### Params transformation: `_build_tool_args`

MCP tools `update_character_sheet` and `update_world` take a single `changes`
argument.  The `Scene.effects[]` contract expresses these as flat params
`{ field, delta|set }` / `{ current_location?, flags? }`.  A thin transformation
layer wraps them:

```python
def _build_tool_args(effect) -> dict:
    if effect.type in {"update_character", "update_world"}:
        return {"changes": effect.params}
    return dict(effect.params)
```

## Alternatives considered

### A: One MCPToolset per request (subprocess per turn)

Simple but slow — spawning a subprocess per request adds hundreds of
milliseconds.  The lifecycle approach (one connection per app) is much faster.

### B: Separate `EngineClient` abstraction

A custom Protocol wrapping `direct_call_tool` was considered.  Rejected because:
- `MCPToolset` IS the MCP contract layer; wrapping it in another abstraction
  adds no architectural value (it's not a swap boundary — the MCP tool contract
  is the boundary).
- It would require yet another module that `gamebook_web` depends on.
- `direct_call_tool` is already the correct minimal interface.

### C: Using `mcp.ClientSession` over stdio (raw `mcp` library)

The raw `mcp.ClientSession` over `stdio_client` was considered.  Rejected
because pydantic-ai 2.0 provides `StdioTransport` natively (zero extra code)
and the in-process `MCPToolset(FastMCP_server)` path makes test injection
trivially clean.

## Consequences

### Accepted
- No subprocess needed for tests (in-process FastMCP with InMemoryStorage).
- One shared MCP connection per app startup (fast, efficient for the dev stub).
- Consistent API surface for route handlers and narrator agents.

### Trade-offs
- `app.state.engine_toolset` must be entered before routes can handle requests;
  the lifespan manages this lifecycle.
- The `_build_tool_args` transformation couples effect params to MCP tool
  signatures — documented in the contract (CONTRACTS.md §10).

### Invalidating conditions
Revisit if pydantic-ai 3.0 changes `MCPToolset` significantly; the
`set_engine_toolset_factory` injection point makes the swap clean.

## References
- [ADR-011 — PydanticAI narrator backend](./ADR-011-phase2-harness-pydanticai-narrator-backend.md)
- [ADR-007 — MCP server FastMCP stdio](./ADR-007-mcp-server-fastmcp-stdio.md)
- `src/gamebook_web/mcp_host.py`, `src/gamebook_web/api/play.py`
- pydantic-ai 2.0.0 changelog / API docs
