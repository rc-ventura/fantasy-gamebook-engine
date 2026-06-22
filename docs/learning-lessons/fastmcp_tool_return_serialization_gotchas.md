# FastMCP tool return-serialization & invocation gotchas (`mcp` SDK ≥ 1.28)

**Context:** Discovered while building and testing the module-05 MCP server
(`src/gamebook/mcp/server.py`, `tests/server/test_mcp_server.py`).
**Date:** 2026-06-21
**Future intent:** Reference for anyone writing tools or tests against `FastMCP`
(QA isolation/e2e tests, the Phase-2 harness author).

---

## Mental Model: what `call_tool` hands back

`FastMCP.call_tool(name, args)` is **async** and its return shape depends on what
the tool returned:

| Tool return type | `call_tool` result | How to read it |
|------------------|--------------------|----------------|
| pydantic `BaseModel` (e.g. `CharacterSheet`) | `tuple(content_list, structured_dict)` | use `result[1]` — the full model dict |
| typed `dict` (e.g. `{"ok": True}`) | bare `content_list` (list of `TextContent`) | `json.loads(result[0].text)` |
| `list[...]` / `str` / scalar | `tuple(content_list, {"result": <value>})` | unwrap the single-key `{"result": ...}` |

A robust test normalizer handles all three:

```python
def call(server, tool, **arguments):
    result = asyncio.run(server.call_tool(tool, arguments))
    if isinstance(result, tuple):
        structured = result[1]
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]          # list/str/scalar envelope
        return structured                         # model dict
    block = result[0]                             # bare content list
    text = getattr(block, "text", None)
    return json.loads(text) if text is not None else result
```

---

## Verified facts (mcp SDK ≥ 1.28)

1. **`call_tool` and `list_tools` are async.** In sync tests, wrap each call in
   `asyncio.run(...)`. Calling `asyncio.run` once per tool call across a whole
   flow is fine — FastMCP keeps no loop-bound state, and a shared
   `InMemoryStorage` carries state between calls.
2. **Non-object returns are wrapped** as `{"result": ...}` in the structured
   payload (`read_events` → `{"result": [...]}`, `read_summary` →
   `{"result": "..."}`). Object returns (BaseModel / dict) are **not** wrapped.
3. **Raising a tool raises `ToolError`**, wrapping the message as
   `"Error executing tool <name>: <original message>"`. So
   `pytest.raises(Exception, match="<substring of your message>")` works — make
   tool error messages distinctive.
4. **Tool functions may be plain `sync` functions.** FastMCP runs them via anyio;
   no `async def` required, which matches our synchronous engine.
5. **Pin the contract name explicitly:** `@server.tool(name="exact_name")` sets
   the registered tool name independently of the Python function name — the way
   to guarantee the `^[a-z0-9_]+$` set in CONTRACTS §6. `list_tools()` returns
   objects with a `.name` attribute.

---

## Examples for fantasy-gamebook-engine

### 1. Test-helper parameter collision

`create_character(name=...)` is a real tool argument. If your test helper is
`call(server, name, **arguments)`, then `call(server, "create_character",
name="Aldric")` raises `TypeError: got multiple values for argument 'name'`.

**Fix:** name the helper's positional parameter `tool`, not `name`.

### 2. Asserting "state unchanged on error"

```python
before = storage.load_character()
with pytest.raises(Exception, match="unknown character field"):
    call(server, "update_character_sheet", changes={"hp": 99})
assert storage.load_character() == before   # ToolError ⇒ nothing persisted
```

---

## Relation to ADRs and next steps

- **ADR-007** — FastMCP over stdio: this lesson documents the serialization
  conventions that decision commits us to.
- **Next step:** the QA e2e (`tests/qa/test_mcp_integration.py`) and the Phase-2
  harness should reuse the normalizer above rather than re-deriving the shapes.
