"""Shared in-process MCP-server plumbing for the QA end-to-end tests.

Helper module (leading underscore -> never collected as tests), made importable
by ``conftest.py`` (which puts this directory on ``sys.path``).

It builds the real server via ``gamebook.mcp.server.build_server`` wired to an
``InMemoryStorage`` + ``CombatService`` + a seeded RNG, and normalizes FastMCP's
``call_tool`` return — which is either ``(unstructured, structured_dict)`` for a
typed tool, a bare ``dict``, or a sequence of content blocks — into a plain
Python value, so tests can assert on dicts directly.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

from gamebook.combat.implementation import CombatService
from gamebook.storage.in_memory import InMemoryStorage


def build_test_server(seed: int) -> tuple[Any, InMemoryStorage]:
    """Build the MCP server over fresh in-memory storage; return (server, storage).

    ``storage`` is returned so tests can introspect persisted state directly
    (e.g. ``storage._archives``) the way the infra server tests do.
    Imports ``build_server`` lazily so a missing server module surfaces as a
    skip in the importing test, not an import error here.
    """
    from gamebook.mcp.server import build_server

    storage = InMemoryStorage()
    rng = random.Random(seed)
    combat = CombatService(storage, rng)
    server = build_server(storage=storage, combat=combat, rng=rng)
    return server, storage


def _unwrap(value: Any) -> Any:
    """FastMCP wraps non-object return types as ``{"result": ...}`` — unwrap it."""
    if isinstance(value, dict) and set(value.keys()) == {"result"}:
        return value["result"]
    return value


def _normalize(raw: Any) -> Any:
    """Reduce a FastMCP ``call_tool`` return to its underlying JSON value."""
    if isinstance(raw, tuple) and len(raw) == 2:
        return _unwrap(raw[1])
    if isinstance(raw, dict):
        return _unwrap(raw)
    for block in list(raw):
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return _unwrap(json.loads(text))
            except (ValueError, TypeError):
                return text
    return raw


def call(server: Any, tool: str, **arguments: Any) -> Any:
    """Invoke an MCP tool by name and return its normalized result.

    The tool-name parameter is ``tool`` (not ``name``) so it can't collide with a
    tool argument literally called ``name`` (e.g. ``create_character(name=...)``).
    """
    return _normalize(asyncio.run(server.call_tool(tool, arguments)))
