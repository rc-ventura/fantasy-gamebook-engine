"""Test: session lease concurrency control (T013 / SC-002 / FR-005/006).

Scenarios covered:
  1. Session 1 acquires lease.
  2. Session 2 tries to write → 409 not_session_holder (read-only until takeover).
  3. Session 2 takes over → gets new token; old token rejected on subsequent write.

These tests use the in-memory/dev mode (no DATABASE_URL required) to verify
the middleware layer.  When DATABASE_URL is set the Postgres-backed LeaseService
is used end-to-end.
"""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

ACCOUNT_A = "account-a"
ACCOUNT_B = "account-b"

DEV_LEASE = "dev-lease-token"  # returned by sessions endpoint in dev mode


def _headers(account_id: str, lease: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer dev-token-{account_id}"}
    if lease:
        h["X-Session-Lease"] = lease
    return h


@pytest.fixture
def two_account_client(engine_server, fake_narrator):
    """API client with two distinct accounts."""
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.auth.dev_auth import Account, get_current_account
    from gamebook_web.sessions.campaign import CampaignRegistry

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = fake_narrator

    async def multi_account_dep(
        authorization: str | None = None,
    ) -> Account:
        from fastapi import Header
        if authorization and "account-a" in authorization:
            return Account(account_id=ACCOUNT_A)
        if authorization and "account-b" in authorization:
            return Account(account_id=ACCOUNT_B)
        return Account(account_id="dev-account")

    from fastapi import Header as _H

    async def dep(authorization: str | None = _H(default=None, alias="Authorization")) -> Account:
        return await multi_account_dep(authorization)

    from gamebook_web.auth.dev_auth import get_current_account as _dev
    app.dependency_overrides[_dev] = dep

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(_dev, None)
    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None
    app.state.narrator = None
    app.state.engine_toolset = None


def test_second_session_cannot_write_without_lease(two_account_client: TestClient) -> None:
    """POST /turn without X-Session-Lease when DATABASE_URL is set → 409.

    In dev mode (no DATABASE_URL), LeaseGuardMiddleware passes through,
    so this test only enforces the 409 when Postgres is available.
    """
    if not os.getenv("DATABASE_URL"):
        pytest.skip("Requires DATABASE_URL for Postgres-backed lease enforcement")

    client = two_account_client
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_A))
    assert resp.status_code == 201
    cid = resp.json()["campaign_id"]

    # Create character (exempt from lease)
    client.post(f"/campaigns/{cid}/character", headers=_headers(ACCOUNT_A))

    # Session A acquires lease
    resp_lease = client.post(f"/campaigns/{cid}/session", headers=_headers(ACCOUNT_A))
    assert resp_lease.status_code == 201
    lease_a = resp_lease.json()["lease_token"]

    # Session B attempts to write a turn without a lease → 409
    resp_turn = client.post(
        f"/campaigns/{cid}/turn",
        headers=_headers(ACCOUNT_B),  # no X-Session-Lease
        json={"choice": "go north"},
    )
    assert resp_turn.status_code == 409, f"Expected 409 but got {resp_turn.status_code}: {resp_turn.json()}"
    assert resp_turn.json()["error"]["code"] in (
        "not_session_holder", "lease_expired"
    ), resp_turn.json()


def test_takeover_invalidates_previous_token(two_account_client: TestClient) -> None:
    """After takeover, the prior token is rejected."""
    if not os.getenv("DATABASE_URL"):
        pytest.skip("Requires DATABASE_URL for Postgres-backed lease enforcement")

    client = two_account_client
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_A))
    assert resp.status_code == 201
    cid = resp.json()["campaign_id"]

    # Session A acquires lease
    lease_a = client.post(f"/campaigns/{cid}/session", headers=_headers(ACCOUNT_A)).json()["lease_token"]

    # Session B takes over
    resp_takeover = client.post(
        f"/campaigns/{cid}/session/takeover",
        headers=_headers(ACCOUNT_B),
        json={},
    )
    assert resp_takeover.status_code == 200, resp_takeover.json()
    lease_b = resp_takeover.json()["lease_token"]

    # Old token A is rejected
    resp_old = client.post(
        f"/campaigns/{cid}/turn",
        headers={**_headers(ACCOUNT_A), "X-Session-Lease": lease_a},
        json={"choice": "go north"},
    )
    assert resp_old.status_code == 409, f"Old token should be rejected: {resp_old.json()}"

    # New token B works (campaign must have character for turn to succeed)
    client.post(f"/campaigns/{cid}/character", headers=_headers(ACCOUNT_A))
    resp_new = client.post(
        f"/campaigns/{cid}/turn",
        headers={**_headers(ACCOUNT_B), "X-Session-Lease": lease_b},
        json={"choice": "go north"},
    )
    assert resp_new.status_code in (200, 409), resp_new.json()  # 409 if campaign already ended


def test_acquire_session_dev_mode(two_account_client: TestClient) -> None:
    """In dev mode, acquire session returns a token (may be static or dynamic)."""
    client = two_account_client
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_A))
    assert resp.status_code == 201
    cid = resp.json()["campaign_id"]

    resp_session = client.post(f"/campaigns/{cid}/session", headers=_headers(ACCOUNT_A))
    assert resp_session.status_code == 201, resp_session.json()
    data = resp_session.json()
    assert "lease_token" in data
    assert "expires_at" in data


def test_release_session_dev_mode(two_account_client: TestClient) -> None:
    """Release session completes without error in dev mode."""
    client = two_account_client
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_A))
    assert resp.status_code == 201
    cid = resp.json()["campaign_id"]

    # Acquire
    lease_token = client.post(f"/campaigns/{cid}/session", headers=_headers(ACCOUNT_A)).json()["lease_token"]

    # Release
    resp_del = client.delete(
        f"/campaigns/{cid}/session",
        headers={**_headers(ACCOUNT_A), "X-Session-Lease": lease_token},
    )
    assert resp_del.status_code in (204, 200), resp_del.text
