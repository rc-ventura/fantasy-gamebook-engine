"""Shared Postgres engine construction for web-layer services (ADR-026, issue #18).

The engine-layer ``PostgresStorage`` already enforces the TLS policy —
``POSTGRES_SSL_MODE`` defaults to ``require`` and reaches asyncpg via
``connect_args`` — but ``AccountRepository`` and ``LeaseService`` built their
engines without it, so account and session-lease traffic travelled over
plaintext connections by default.  Both now build their engines from
``pg_engine_kwargs()``, which mirrors the engine-layer behavior (and
deduplicates the bounded-pool settings the two classes previously repeated).

This helper lives in ``gamebook_web`` rather than being shared with
``gamebook.storage.postgres`` because the dependency arrow must keep pointing
web → engine, never engine → web.
"""

from __future__ import annotations

import os
from typing import Any


def pg_engine_kwargs() -> dict[str, Any]:
    """Shared ``create_async_engine`` kwargs: TLS + bounded pool.

    TLS (ADR-026): ``ssl`` defaults to ``require``; set
    ``POSTGRES_SSL_MODE=disable`` for local dev/test against a non-TLS server.
    asyncpg has no ``sslmode`` DSN parameter, so this connect_arg is the only
    way TLS gets requested.

    Pool bounds (L-POOL): an unbounded pool can exhaust Postgres connections
    under load; these limits cap worst-case connection usage per process while
    still allowing reasonable concurrency.
    """
    connect_args: dict[str, Any] = {
        # asyncpg's default connect timeout is None (blocks forever); bound it
        # so engine construction fails fast on an unresponsive database.
        "timeout": float(os.getenv("POSTGRES_CONNECT_TIMEOUT", "10")),
    }
    ssl_mode = os.getenv("POSTGRES_SSL_MODE", "require")
    if ssl_mode != "disable":
        connect_args["ssl"] = ssl_mode  # asyncpg accepts "require" / True
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 30,
        "connect_args": connect_args,
    }
