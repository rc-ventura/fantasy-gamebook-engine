"""ADR-026 TLS enforcement on the web-layer Postgres engines (issue #18).

``PostgresStorage`` (engine layer) has requested TLS by default since spec 006
(T072), but ``AccountRepository`` and ``LeaseService`` created their engines
with no ``connect_args`` at all — account records and session-lease tokens
travelled over plaintext connections by default.  Both now build their engines
from ``gamebook_web.db.pg_engine_kwargs()``.

Mirrors the spy pattern of ``test_postgres_storage.py::test_tls_ssl_mode_wiring``
so all three Postgres-connecting classes are covered by the same style of check.
No live database needed — engine construction is lazy.
"""

from __future__ import annotations

import pytest

from gamebook_web.db import pg_engine_kwargs

FAKE_URL = "postgresql+asyncpg://user:pass@db.example/gamebook"


# ---------------------------------------------------------------------------
# The shared helper
# ---------------------------------------------------------------------------

def test_pg_engine_kwargs_defaults_to_tls(monkeypatch):
    monkeypatch.delenv("POSTGRES_SSL_MODE", raising=False)
    kwargs = pg_engine_kwargs()
    assert kwargs["connect_args"]["ssl"] == "require"
    # Bounded pool (L-POOL) travels with the TLS policy.
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 10
    assert kwargs["pool_timeout"] == 30
    assert kwargs["pool_pre_ping"] is True


def test_pg_engine_kwargs_disable_drops_ssl(monkeypatch):
    monkeypatch.setenv("POSTGRES_SSL_MODE", "disable")
    kwargs = pg_engine_kwargs()
    assert "ssl" not in kwargs["connect_args"]


def test_pg_engine_kwargs_custom_mode_passthrough(monkeypatch):
    monkeypatch.setenv("POSTGRES_SSL_MODE", "verify-full")
    kwargs = pg_engine_kwargs()
    assert kwargs["connect_args"]["ssl"] == "verify-full"


# ---------------------------------------------------------------------------
# The two consumers (spy on create_async_engine in each module's namespace)
# ---------------------------------------------------------------------------

def _spy_engine_factory(module, monkeypatch) -> dict:
    captured: dict = {}
    real_create = module.create_async_engine

    def spy(url, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return real_create(url, **kwargs)

    monkeypatch.setattr(module, "create_async_engine", spy)
    return captured


@pytest.mark.parametrize("ssl_env,expected", [(None, "require"), ("disable", None)])
def test_account_repository_engine_requests_tls(monkeypatch, ssl_env, expected):
    import gamebook_web.accounts as accounts_mod

    if ssl_env is None:
        monkeypatch.delenv("POSTGRES_SSL_MODE", raising=False)
    else:
        monkeypatch.setenv("POSTGRES_SSL_MODE", ssl_env)

    captured = _spy_engine_factory(accounts_mod, monkeypatch)
    accounts_mod.AccountRepository(FAKE_URL)

    assert captured["connect_args"].get("ssl") == expected
    assert captured["pool_size"] == 5


@pytest.mark.parametrize("ssl_env,expected", [(None, "require"), ("disable", None)])
def test_lease_service_engine_requests_tls(monkeypatch, ssl_env, expected):
    import gamebook_web.sessions.lease as lease_mod

    if ssl_env is None:
        monkeypatch.delenv("POSTGRES_SSL_MODE", raising=False)
    else:
        monkeypatch.setenv("POSTGRES_SSL_MODE", ssl_env)

    captured = _spy_engine_factory(lease_mod, monkeypatch)
    lease_mod.LeaseService(FAKE_URL)

    assert captured["connect_args"].get("ssl") == expected
    assert captured["pool_size"] == 5
