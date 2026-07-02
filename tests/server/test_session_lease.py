"""Session-lease endpoint tests — D1 dev mode (T013 / SC-002 / FR-005/006).

These verify the D1 ``/me/game/session`` endpoints in dev mode (no DATABASE_URL):
they return the SPA-compatible ``{session_token, expires_at}`` shape and the
lifecycle round-trips.  The real DB-backed lease semantics — takeover
``current_token`` validation (FR-027), the ``<=`` expiry boundary (FR-028), and
``SELECT FOR UPDATE`` concurrency — are covered against live Postgres by
``test_postgres_leases.py``.
"""

from __future__ import annotations

AUTH = {"Authorization": "Bearer dev-token"}


def test_acquire_session_returns_spa_shape(api_client):
    api_client.post("/me/game", headers=AUTH)
    resp = api_client.post("/me/game/session", headers=AUTH)
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert "session_token" in body and body["session_token"]
    assert "expires_at" in body


def test_takeover_session_returns_token(api_client):
    api_client.post("/me/game", headers=AUTH)
    resp = api_client.post("/me/game/session/takeover", headers=AUTH, json={})
    assert resp.status_code == 200, resp.json()
    assert resp.json()["session_token"]


def test_release_session_ok(api_client):
    api_client.post("/me/game", headers=AUTH)
    resp = api_client.request(
        "DELETE", "/me/game/session", headers={**AUTH, "X-Session-Lease": "dev"}
    )
    assert resp.status_code == 204, resp.text
