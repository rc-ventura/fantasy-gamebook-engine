# Scoped toolset wrapper: inject security context at the wrapper, not via the LLM

**Date**: 2026-07-01

## Problem

When an agent (PydanticAI narrator) calls MCP tools that require a security-scoped
parameter (`campaign_id`, `account_id`, `tenant_id`, etc.), it is tempting to:

1. Include the parameter in the tool signature so the LLM passes it, and
2. Audit the LLM's output post-generation to verify it used the correct value.

This approach has a critical flaw: the audit runs **after** the tools have already
executed. If the LLM passed the wrong value (accidentally or due to prompt confusion),
the tool's side-effects (writes to storage) happened against the wrong scope **before**
the audit detected the problem.

**The audit is detection, not prevention.**

## Solution: inject at the wrapper layer

Wrap the toolset so that the security-scoped parameter is always overridden with the
correct value **before** the call reaches the MCP server. The LLM is removed from the
security-critical path entirely.

```python
from dataclasses import dataclass
from pydantic_ai.toolsets import WrapperToolset

@dataclass
class ScopedMCPToolset(WrapperToolset):
    """WrapperToolset that injects campaign_id on every call."""

    campaign_id: str = ""

    async def call_tool(self, name, tool_args, ctx, tool):
        merged = {**tool_args, "campaign_id": self.campaign_id}  # always override
        return await self.wrapped.call_tool(name, merged, ctx, tool)
```

## Trap (found 2026-07-02): the wrapper MUST subclass `WrapperToolset`

A duck-typed wrapper (`__getattr__` delegation to the base toolset) **silently loses
the override**. pydantic-ai rebuilds the toolset tree at run start via
`for_run()`/`visit_and_replace()`; delegating those calls returns the *base*
toolset's rebuilt tree — without the wrapper — so `call_tool` injection never runs
and the MCP server sees the raw (unscoped) arguments. There is no error at the
wrapper layer: the failure shows up as the engine rejecting a missing/wrong
`campaign_id`, or worse, as silent cross-scope access if the parameter is optional.

Only a real `WrapperToolset` dataclass subclass survives the rebuild:
`for_run` uses `dataclasses.replace(self, wrapped=...)`, which preserves the
subclass and its extra fields. Also note the exact `call_tool` signature is
`(name, tool_args, ctx, tool)` — patching `args[-1]` corrupts the `ToolsetTool`
object, not the args dict.

This was caught by `tests/server/test_narrator_integration.py`, which drives the
real `PydanticNarrator` with a mocked LLM (`FunctionModel`) that omits
`campaign_id` and asserts the engine still receives it.

With this pattern:
- The LLM can include `campaign_id` in its call (it learns it from the system prompt)
  or omit it — the wrapper enforces the correct value either way.
- No LLM prompt engineering is required for security correctness.
- The post-generation audit (`_assert_narrator_campaign`) becomes belt-and-suspenders
  rather than the primary defense.

## When to use

Whenever an AI agent calls tools that are scoped to a security context (tenant, account,
campaign, user) and that context must never be influenced by the LLM's output:

- Multi-tenant systems (`campaign_id`, `account_id`, `tenant_id`)
- Per-user data isolation (`user_id`)
- Any parameter where LLM confusion could cause cross-account data access

## Future path

This pattern works for the stdio MCP transport (one subprocess, all campaigns).
When migrating to `StreamableHTTPTransport`, `campaign_id` can move to an HTTP header
on each request — the LLM never sees or touches it at all. The wrapper pattern is the
correct intermediate step.

## Applied in

`src/gamebook_web/harness/agent.py` T006b (spec 006) — narrator toolset scoped to
`campaign_id` per turn.
