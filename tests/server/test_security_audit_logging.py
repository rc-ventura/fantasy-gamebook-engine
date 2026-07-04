"""Security audit logging tests (T055, SC-015, FR-033).

Asserts that security-relevant events are written to the ``gamebook.audit``
logger with opaque identifiers only (no token, name, sub, or player input).

Events covered (observable in dev/in-memory mode):
  * ``auth.failed``        — a bad/missing bearer token.
  * ``session.acquired``   — lease acquired ("sign-in" to a play session).
  * ``session.takeover``   — lease taken over.
  * ``session.released``   — lease released ("sign-out").
  * ``account.deleted``    — account erased (GDPR).
"""

from __future__ import annotations

import logging

import pytest

AUTH = {"Authorization": "Bearer dev-token"}


@pytest.fixture(autouse=True)
def capture_audit(caplog):
    caplog.set_level(logging.INFO, logger="gamebook.audit")
    return caplog


def _audit_events(caplog) -> str:
    return "\n".join(
        r.getMessage() for r in caplog.records if r.name == "gamebook.audit"
    )


def test_failed_auth_is_audited(api_client, capture_audit):
    resp = api_client.get("/me/game", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401
    assert "event=auth.failed" in _audit_events(capture_audit)


def test_session_lifecycle_is_audited(api_client, capture_audit):
    api_client.post("/me/game", headers=AUTH)

    api_client.post("/me/game/session", headers=AUTH)
    api_client.post("/me/game/session/takeover", headers=AUTH, json={})
    api_client.request(
        "DELETE",
        "/me/game/session",
        headers={**AUTH, "X-Session-Lease": "dev-lease-token"},
    )

    events = _audit_events(capture_audit)
    assert "event=session.acquired" in events
    assert "event=session.takeover" in events
    assert "event=session.released" in events
    # No token value is logged.
    assert "dev-lease-token" not in events


def test_account_deletion_is_audited(api_client, capture_audit):
    resp = api_client.request("DELETE", "/me", headers=AUTH, json={"confirmation": True})
    assert resp.status_code == 204
    assert "event=account.deleted" in _audit_events(capture_audit)


def test_audit_never_logs_pii_fields(capture_audit):
    """The audit helper drops forbidden PII fields even if a caller passes them."""
    from gamebook_web.observability.audit import audit_event

    audit_event("auth.signin", account_id="acct-1", sub="google|123", name="Aria")
    line = _audit_events(capture_audit)
    assert "acct-1" in line
    assert "google|123" not in line
    assert "Aria" not in line
