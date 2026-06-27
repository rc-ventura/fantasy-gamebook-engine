# pydantic-ai 2.0 MCPToolset: `direct_call_tool` vs `toolsets=[]` in agents

**Date**: 2026-06-27  
**Slice**: 003-web-backend-mvp

---

## Discovery

When implementing the web backend (slice 003), `pydantic-ai>=0.0.15` resolved
to **2.0.0** — a major version jump from the pre-release 0.0.x series.

Key changes relevant to this project:

1. **`StdioTransport` is in `pydantic_ai.mcp`**, not in the `mcp` library:
   ```python
   from pydantic_ai.mcp import MCPToolset, StdioTransport
   ```

2. **`MCPToolset` accepts a `FastMCP` server directly** (no stdio needed for tests):
   ```python
   toolset = MCPToolset(build_server(storage=InMemoryStorage(), ...))
   # Works without starting a subprocess — perfect for tests
   ```

3. **Direct tool calls outside an agent**: use `direct_call_tool(name, args)`:
   ```python
   async with toolset:
       result = await toolset.direct_call_tool("create_character", {"name": "Hero"})
   ```

4. **Agent runs pass toolsets per-run**, not at agent construction:
   ```python
   # Create agent without toolset
   agent = Agent("anthropic:claude-opus-4-8", output_type=Scene)
   
   # Pass toolset at run time
   result = await agent.run(prompt, toolsets=[already_entered_toolset])
   ```

5. **`raise_server_exceptions=True`** (default in `TestClient`) re-raises
   exceptions that propagate through the ASGI app, even when exception handlers
   are registered.  Use `raise_server_exceptions=False` when testing routes that
   intentionally trigger engine errors (tool errors, validation failures).

6. **`MCPToolset` as an async context manager**: must be entered ONCE at app
   startup and kept alive; `direct_call_tool` reuses the live connection.

## Rule of thumb

| Context | Pattern |
|---------|---------|
| FastAPI route handler | `await toolset.direct_call_tool(name, args)` |
| PydanticAI agent run | `agent.run(prompt, toolsets=[toolset])` |
| Tests (no subprocess) | `MCPToolset(build_server(InMemoryStorage(), ...))` |
| Production (subprocess) | `MCPToolset(StdioTransport(command="uv", args=[...]))` |
