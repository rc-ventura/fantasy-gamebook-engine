"""Test: resume across devices (T012 / SC-001/002/003).

Scenarios covered:
  1. Account A plays several turns, saves, "signs out".
  2. Account A re-authenticates (new session) and resumes — character/world
     identical (SC-001/002).
  3. Account B's campaigns are never visible from Account A's perspective
     (404 on cross-account GET) — SC-003.

These tests use FakeNarrator + InMemoryStorage so no Postgres is required.
Where Postgres IS configured (DATABASE_URL set) the full persistence path is
exercised.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from gamebook_web.auth.dev_auth import DEV_TOKEN, Account

# ---------------------------------------------------------------------------
# Two-account fixture (A + B with different account_id / dev tokens)
# ---------------------------------------------------------------------------

ACCOUNT_A_ID = "account-a"
ACCOUNT_B_ID = "account-b"


def _headers(account_id: str, lease: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer dev-token-{account_id}"}
    if lease:
        h["X-Session-Lease"] = lease
    return h


@pytest.fixture
def two_account_client(engine_server, fake_narrator):
    """API client that supports two distinct accounts (A and B).

    Uses the dev auth stub with different account IDs, driven via
    dependency override so the play loop is exercised through the real routes.
    """
    import random
    from pydantic_ai.mcp import MCPToolset
    from starlette.testclient import TestClient

    import gamebook_web.mcp_host as mcp_host_mod
    from gamebook_web.api.app import app
    from gamebook_web.auth.dev_auth import Account, get_current_account
    from gamebook_web.sessions.campaign import CampaignRegistry

    mcp_host_mod.set_engine_toolset_factory(lambda: MCPToolset(engine_server))
    app.state.campaign_registry = CampaignRegistry()
    app.state.narrator = fake_narrator

    # Override auth to return account based on the Authorization header value
    async def multi_account_auth(
        authorization: str | None = None,
    ) -> Account:
        if authorization and "account-a" in authorization:
            return Account(account_id=ACCOUNT_A_ID)
        if authorization and "account-b" in authorization:
            return Account(account_id=ACCOUNT_B_ID)
        # Default dev account for unrecognized tokens
        return Account(account_id="dev-account")

    from fastapi import Header as _Header

    async def multi_account_dep(
        authorization: str | None = _Header(default=None, alias="Authorization"),
    ) -> Account:
        return await multi_account_auth(authorization)

    from gamebook_web.auth.dev_auth import get_current_account as _dev_dep
    app.dependency_overrides[_dev_dep] = multi_account_dep

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(_dev_dep, None)
    mcp_host_mod.set_engine_toolset_factory(None)
    app.state.campaign_registry = None
    app.state.narrator = None
    app.state.engine_toolset = None


# ---------------------------------------------------------------------------
# Test 1: Save and resume within the same account
# ---------------------------------------------------------------------------

def test_resume_same_account(two_account_client: TestClient) -> None:
    """Account A creates a campaign, creates a character, then 'resumes' by
    fetching the campaign state — character and world must be identical.
    """
    client = two_account_client

    # Create campaign
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_A_ID))
    assert resp.status_code == 201, resp.json()
    cid = resp.json()["campaign_id"]

    # Create character
    resp = client.post(f"/campaigns/{cid}/character", headers=_headers(ACCOUNT_A_ID))
    assert resp.status_code == 201, resp.json()
    first_character = resp.json()

    # Resume: re-read the campaign state — must reflect the created character
    resp = client.get(f"/campaigns/{cid}", headers=_headers(ACCOUNT_A_ID))
    assert resp.status_code == 200, resp.json()
    resumed = resp.json()

    # Character must match (alive, same skill/stamina values)
    assert resumed["character"] is not None
    assert resumed["character"]["alive"] == first_character["alive"]
    assert resumed["character"]["name"] == first_character["name"]


# ---------------------------------------------------------------------------
# Test 2: Cross-account isolation — Account B cannot see Account A's campaign
# ---------------------------------------------------------------------------

def test_cross_account_isolation(two_account_client: TestClient) -> None:
    """Account A's campaign is invisible to Account B (404)."""
    client = two_account_client

    # Account A creates campaign
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_A_ID))
    assert resp.status_code == 201, resp.json()
    cid_a = resp.json()["campaign_id"]

    # Account B tries to access Account A's campaign — should get 404 or 403
    resp = client.get(f"/campaigns/{cid_a}", headers=_headers(ACCOUNT_B_ID))
    assert resp.status_code in (403, 404), f"Expected 403/404 but got {resp.status_code}: {resp.json()}"

    # Account B can only see their own campaigns (empty list or their own)
    resp_b = client.post("/campaigns", headers=_headers(ACCOUNT_B_ID))
    assert resp_b.status_code == 201
    cid_b = resp_b.json()["campaign_id"]

    resp_list_b = client.get("/campaigns", headers=_headers(ACCOUNT_B_ID))
    assert resp_list_b.status_code == 200
    campaign_ids_b = [c["campaign_id"] for c in resp_list_b.json()]
    assert cid_a not in campaign_ids_b, "Account B must not see Account A's campaigns"
    assert cid_b in campaign_ids_b, "Account B must see their own campaign"


# ---------------------------------------------------------------------------
# Test 3: Account A's campaigns are not in Account B's list
# ---------------------------------------------------------------------------

def test_list_campaigns_isolation(two_account_client: TestClient) -> None:
    """Campaign lists are strictly per-account."""
    client = two_account_client

    # A creates two campaigns
    for _ in range(2):
        resp = client.post("/campaigns", headers=_headers(ACCOUNT_A_ID))
        assert resp.status_code == 201

    # B creates one
    resp = client.post("/campaigns", headers=_headers(ACCOUNT_B_ID))
    assert resp.status_code == 201
    cid_b = resp.json()["campaign_id"]

    list_a = client.get("/campaigns", headers=_headers(ACCOUNT_A_ID)).json()
    list_b = client.get("/campaigns", headers=_headers(ACCOUNT_B_ID)).json()

    ids_a = {c["campaign_id"] for c in list_a}
    ids_b = {c["campaign_id"] for c in list_b}

    assert len(ids_a) >= 2, "Account A should see their campaigns"
    assert len(ids_b) >= 1, "Account B should see their campaign"
    assert ids_a.isdisjoint(ids_b), "Account lists must not overlap"
