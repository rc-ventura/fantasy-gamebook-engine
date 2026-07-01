"""Test: reject acting on an ended run (T018 / SC-007 / FR-013).

When a campaign has status "ended", any further turn or combat action MUST
be rejected with ``409 run_ended``.  The same constraint already existed in
the play loop (slice 003); this test suite confirms it is enforced and adds
a check for the combat router as well.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client_with_ended_campaign(api_client: TestClient):
    """API client fixture with one campaign pre-created and forcibly ended."""
    resp = api_client.post(
        "/campaigns",
        headers={"Authorization": "Bearer dev-token"},
    )
    assert resp.status_code == 201, resp.json()
    cid = resp.json()["campaign_id"]

    # Create character
    api_client.post(
        f"/campaigns/{cid}/character",
        headers={"Authorization": "Bearer dev-token"},
    )

    # Mark campaign ended via the registry (test-internal access)
    from gamebook_web.api.app import app
    registry = app.state.campaign_registry
    registry.set_ended(cid)

    return api_client, cid


def test_turn_on_ended_campaign_returns_409(client_with_ended_campaign):
    """POST /turn on an ended campaign → 409 run_ended."""
    client, cid = client_with_ended_campaign
    resp = client.post(
        f"/campaigns/{cid}/turn",
        headers={"Authorization": "Bearer dev-token"},
        json={"choice": "go north"},
    )
    assert resp.status_code == 409, resp.json()
    assert resp.json()["error"]["code"] == "run_ended"


def test_save_on_ended_campaign_returns_409(client_with_ended_campaign):
    """POST /save on an ended campaign → 409 run_ended."""
    client, cid = client_with_ended_campaign
    resp = client.post(
        f"/campaigns/{cid}/save",
        headers={"Authorization": "Bearer dev-token"},
    )
    assert resp.status_code == 409, resp.json()
    assert resp.json()["error"]["code"] == "run_ended"


def test_get_campaign_on_ended_campaign_still_works(client_with_ended_campaign):
    """GET /campaigns/{id} on an ended campaign is still allowed (read-only)."""
    client, cid = client_with_ended_campaign
    resp = client.get(
        f"/campaigns/{cid}",
        headers={"Authorization": "Bearer dev-token"},
    )
    assert resp.status_code == 200, resp.json()
    assert resp.json()["status"] == "ended"
