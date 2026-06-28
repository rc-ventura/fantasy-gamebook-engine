"""MCP host — engine toolset factory and direct-call helpers.

The web layer talks to the game engine ONLY through this module.  No
``gamebook.*`` engine module is imported here — only the PydanticAI MCP
client abstractions (``MCPToolset``, ``StdioTransport``) which are the
standard MCP protocol layer (not engine internals).

Production path:
  ``MCPToolset(StdioTransport(command="uv", args=["run", "python", "-m",
  "gamebook.mcp.server"], env=...))`` — starts the engine as a subprocess
  and communicates over stdio (ADR-007, ADR-011).

Test path (injected by conftest):
  ``MCPToolset(build_server(...))`` — an in-process FastMCP server backed by
  ``InMemoryStorage``.  No subprocess required; identical MCP protocol.

The active factory is a module-level variable so tests can override it
before the FastAPI lifespan runs.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable

from pydantic_ai.mcp import MCPToolset, StdioTransport

# ---------------------------------------------------------------------------
# Toolset factory (swappable for tests)
# ---------------------------------------------------------------------------

# Set this in tests (before TestClient enters lifespan) to inject an
# in-process engine instead of starting a subprocess.
_TOOLSET_FACTORY: Callable[[], MCPToolset] | None = None


def set_engine_toolset_factory(factory: Callable[[], MCPToolset] | None) -> None:
    """Override the MCPToolset factory (for tests; never call in production code)."""
    global _TOOLSET_FACTORY  # noqa: PLW0603
    _TOOLSET_FACTORY = factory


def _default_toolset_factory(campaign_id: str | None = None) -> MCPToolset:
    """Production toolset: engine subprocess over stdio (ADR-007)."""
    env = {**os.environ}
    if campaign_id:
        env["GAMEBOOK_CAMPAIGN_ID"] = campaign_id
    return MCPToolset(
        StdioTransport(
            command=sys.executable,
            args=["-m", "gamebook.mcp.server"],
            env=env,
        )
    )


def make_toolset(campaign_id: str | None = None) -> MCPToolset:
    """Create an MCPToolset using the active factory (production or test).

    In production the factory is ``None`` so the default subprocess path is
    used.  In tests, ``set_engine_toolset_factory`` installs a factory that
    returns an in-process MCPToolset with ``InMemoryStorage``.
    """
    if _TOOLSET_FACTORY is not None:
        return _TOOLSET_FACTORY()
    return _default_toolset_factory(campaign_id)


# ---------------------------------------------------------------------------
# Async context manager for the toolset lifecycle (used by the app lifespan)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def engine_toolset_lifespan(
    campaign_id: str | None = None,
) -> AsyncGenerator[MCPToolset, None]:
    """Async context manager: enter the MCPToolset and yield it.

    The toolset is entered ONCE at app startup and kept alive until shutdown.
    All routes call ``toolset.direct_call_tool(...)`` against this live
    connection.  The lifespan in ``api/app.py`` stores the entered toolset in
    ``app.state.engine_toolset``.
    """
    toolset = make_toolset(campaign_id)
    async with toolset:
        yield toolset


# ---------------------------------------------------------------------------
# Direct tool-call helper (used by routes)
# ---------------------------------------------------------------------------

async def call_engine(
    toolset: MCPToolset,
    tool_name: str,
    **arguments: Any,
) -> Any:
    """Call an engine MCP tool and return its result as a plain Python value.

    ``toolset`` must already be entered (it is, since it lives in app.state).
    Raises ``RuntimeError`` if the tool returns an error.
    """
    return await toolset.direct_call_tool(tool_name, arguments)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_engine_toolset(request: Any) -> MCPToolset:  # noqa: ANN401
    """FastAPI dependency: return the active engine toolset from app state."""
    toolset = getattr(request.app.state, "engine_toolset", None)
    if toolset is None:
        raise RuntimeError(
            "Engine toolset not configured — check app lifespan or test fixture."
        )
    return toolset
