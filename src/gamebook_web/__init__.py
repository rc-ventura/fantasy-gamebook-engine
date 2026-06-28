"""gamebook_web — Phase-2 web backend for the gamebook engine.

FastAPI HTTP API + PydanticAI narrator harness + MCP host.  The web layer
depends only on the MCP tool contract and the HTTP API contract; it never
imports concrete storage implementations or engine internals (Principle II).
"""
