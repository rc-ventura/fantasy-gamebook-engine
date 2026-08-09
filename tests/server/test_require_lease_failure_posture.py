"""``require_lease`` failure posture (issue #17, ADR-023/ADR-031/ADR-032).

Once a lease exists for the campaign, the dependency must:
  * propagate 409s from ``validate_and_renew`` (not_session_holder / expired),
  * reject with **503 lease_check_unavailable** when the check itself fails
    for infrastructure reasons (DB blip, pool timeout) — fail closed, never
    proceed with the single-active-writer guarantee unverified.

The dependency is exercised directly (it is a plain async function); the
request/registry/lease-service collaborators are minimal fakes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from gamebook_web.auth.dev_auth import Account
from gamebook_web.sessions.campaign import CampaignRegistry
from gamebook_web.sessions.lease import require_lease, set_lease_service

ACCOUNT = Account(account_id="acct-1")


class FakeLeaseService:
    """Lease exists; ``validate_and_renew`` behavior is injectable."""

    def __init__(self, validate_error: Exception | None = None) -> None:
        self._validate_error = validate_error
        self.validate_calls = 0

    async def get_lease(self, campaign_id: str):
        return {"campaign_id": campaign_id, "lease_token": "held"}

    async def validate_and_renew(self, campaign_id: str, account_id: str, token: str):
        self.validate_calls += 1
        if self._validate_error is not None:
            raise self._validate_error


@pytest_asyncio.fixture
async def request_with_campaign(monkeypatch):
    """A fake Request whose registry has an active campaign for ACCOUNT."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fake/db")
    registry = CampaignRegistry()
    await registry.create(ACCOUNT.account_id, name="Run")
    app = SimpleNamespace(state=SimpleNamespace(campaign_registry=registry))
    yield SimpleNamespace(app=app)
    set_lease_service(None)


@pytest.mark.asyncio
async def test_infra_error_fails_closed_with_503(request_with_campaign):
    svc = FakeLeaseService(validate_error=RuntimeError("connection reset"))
    set_lease_service(svc)

    with pytest.raises(HTTPException) as exc_info:
        await require_lease(request_with_campaign, account=ACCOUNT, x_session_lease="tok")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"]["code"] == "lease_check_unavailable"
    assert svc.validate_calls == 1


@pytest.mark.asyncio
async def test_409_from_validate_still_propagates(request_with_campaign):
    denial = HTTPException(status_code=409, detail={"error": {"code": "not_session_holder"}})
    set_lease_service(FakeLeaseService(validate_error=denial))

    with pytest.raises(HTTPException) as exc_info:
        await require_lease(request_with_campaign, account=ACCOUNT, x_session_lease="stale")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_valid_token_passes(request_with_campaign):
    set_lease_service(FakeLeaseService())

    # No exception — the mutation may proceed and the TTL was renewed.
    await require_lease(request_with_campaign, account=ACCOUNT, x_session_lease="held")


@pytest.mark.asyncio
async def test_missing_token_with_existing_lease_is_409(request_with_campaign):
    set_lease_service(FakeLeaseService())

    with pytest.raises(HTTPException) as exc_info:
        await require_lease(request_with_campaign, account=ACCOUNT, x_session_lease=None)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"]["code"] == "not_session_holder"
