# Booting a single shared engine subprocess scoped to an env var is a multi-tenancy anti-pattern

**Date**: 2026-07-02

## Problem

The first Phase-2 MCP integration started the engine subprocess with
`GAMEBOOK_CAMPAIGN_ID` in its environment: one process, permanently bound to one
campaign. That works for exactly one player and silently breaks for two — the web
backend is multi-tenant (many accounts, many campaigns), so either:

- every request for campaign B hits a process scoped to campaign A (cross-tenant
  state corruption), or
- the host must boot one subprocess per campaign, which turns a stateless API into
  a process-manager with unbounded fan-out, lifecycle races, and no clean shutdown.

The root mistake: **scoping a long-lived shared resource with boot-time
configuration when the scope is actually per-request.**

## Solution (ADR-018 Option A)

- One engine subprocess for the whole app.
- `campaign_id: str` is the **first parameter of every MCP tool** — the scope
  travels with each call, not with the process.
- The engine resolves storage per call via a `storage_factory(campaign_id)`.
- The narrator's LLM never controls the value: `ScopedMCPToolset` overrides
  `campaign_id` at the wrapper layer on every tool call (see
  [scoped_toolset_wrapper_for_security_context](./scoped_toolset_wrapper_for_security_context.md)).

## Rule of thumb

Ask "what is the *smallest* unit this value can change across?" If the answer is
"per request" (tenant, account, campaign, user), the value must be a call parameter
or per-request header — never process env, module state, or a singleton set at
startup. Boot-time scoping is only correct for values that are genuinely constant
for the process lifetime (DB URL, credentials, feature flags).
