# ADR-007: MCP server uses the FastMCP high-level API over stdio transport

**Status**: Accepted
**Date**: 2026-06-21
**Related spec**: [05-mcp.md](../05-mcp.md) · [CONTRACTS.md §6](../CONTRACTS.md)
**Code**: `src/gamebook/mcp/server.py`

---

## Context

Module 05 (`mcp`) is the façade that exposes the engine to a harness (swap point
#3). CONTRACTS §6 mandates **exactly 17 tools** with names matching `^[a-z0-9_]+$`,
a **stdio** transport, server name `gamebook`, and a `python -m gamebook.mcp.server`
entry point so Claude Code can launch it via `.mcp.json`. The tools must return
domain pydantic models (`CharacterSheet`, `Combat`, `RoundOutcome`, …) and small
ack dicts, contain **no game rules**, and orchestrate `regras` / `combate` /
`storage` through **interfaces only**. The `mcp` SDK (`mcp>=1.28.0`) offers two
ways to build a server: the low-level `mcp.server.Server` and the high-level
`mcp.server.fastmcp.FastMCP`.

## Decision

Build the server with **`FastMCP`**.

```python
server = FastMCP(name="gamebook", instructions=...)

@server.tool(name="create_character", description="...")
def create_character(name: str) -> CharacterSheet:
    ...

# Composition root — the ONLY place concretes are constructed:
def main() -> None:
    import random
    from gamebook.combate.implementation import CombatService
    from gamebook.storage.json_storage import JSONStorage
    storage = JSONStorage("estado")
    rng = random.Random()
    combat = CombatService(storage, rng)
    build_server(storage, combat, rng).run(transport="stdio")
```

`build_server(storage, combat, rng)` takes **interfaces only** and constructs no
concretes; `main()` is the sole composition root. Concrete imports live *inside*
`main()` so importing the module never pulls a storage backend into `sys.modules`
(verified: a fresh-interpreter import of `gamebook.mcp.server` loads no
`storage.json_storage` / `storage.in_memory`).

## Alternatives considered

### Alternative A: low-level `mcp.server.Server`

**Why not chosen**:
- Requires hand-writing each tool's JSON input schema and the
  `list_tools` / `call_tool` dispatch by hand.
- Manual serialization of pydantic return values into content + structured output.
- More boilerplate per tool ⇒ more surface for drifting from CONTRACTS §6.

**Advantages** (not leveraged):
- Finer control over the wire protocol and custom content blocks.

## Consequences

### Accepted

- FastMCP derives input schemas from typed function signatures and
  auto-serializes pydantic `BaseModel` returns into both text and **structured**
  content.
- `@server.tool(name=...)` pins the exact contract tool name independently of the
  Python function name, guaranteeing the `^[a-z0-9_]+$` set.
- Tool functions can be plain **sync** functions (FastMCP runs them via anyio),
  matching the synchronous engine.
- The tool contract is stable across harnesses: the Phase-2 PydanticAI/FastAPI
  harness can reuse the same MCP unchanged.

### Trade-offs

- We depend on FastMCP's serialization conventions (e.g. non-object returns are
  wrapped as `{"result": ...}`; see the companion learning lesson). Callers must
  normalize these shapes.

### Conditions that invalidate this decision

This decision should be **revisited** if:

1. The harness needs a non-stdio transport as the default (e.g. remote
   streamable-http for a web frontend) — FastMCP still supports it via
   `run(transport=...)`, so only `main()` changes.
2. A tool needs wire-level control that FastMCP cannot express.

### Migration path when needed

- Adding a transport: change only `main()` (`run(transport="streamable-http")`);
  tools and `build_server` are untouched.
- Dropping to low-level `Server`: re-wrap each `build_server` closure as an
  explicit `call_tool` dispatch with hand-written schemas; the orchestration
  bodies port verbatim.

## References

- CONTRACTS.md §6 (17-tool contract, composition root)
- ADR-005 (determinism via injected `RandomSource`) — same injection discipline
- Learning lesson: *FastMCP tool return-serialization & invocation gotchas*
