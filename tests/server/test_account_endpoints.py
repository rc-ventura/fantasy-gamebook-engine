"""Account/privacy endpoint tests (T044, SC-013/SC-014, ADR-025).

Exercises the DB-path behaviour of ``/me`` without a live Postgres by setting
``DATABASE_URL`` (so ``_has_database()`` routes to the repository) and injecting
a fake ``AccountRepository`` via ``set_account_repository``.

Covers:
  * DELETE /me → 400 without ``confirmation`` (FR-025).
  * DELETE /me → 404 when the account does not exist (FR-025).
  * DELETE /me → 204 with ``confirmation`` for an existing account.
  * GET /me/export → payload includes per-campaign ``save_slots`` (FR-026).
"""

from __future__ import annotations

from typing import Any

import pytest

AUTH = {"Authorization": "Bearer dev-token"}
DEV_ACCOUNT = "dev-account"


class FakeAccountRepository:
    """Minimal in-memory stand-in for AccountRepository (no DB engine)."""

    def __init__(self, *, account_exists: bool = True, save_slots: list[dict] | None = None) -> None:
        self._account_exists = account_exists
        self._save_slots = save_slots or []
        self.deleted: list[str] = []

    async def get_account_by_id(self, account_id: str) -> dict[str, Any] | None:
        if not self._account_exists:
            return None
        return {"account_id": account_id, "sub": "sub-123", "created_at": None}

    async def delete_account(self, account_id: str) -> None:
        self.deleted.append(account_id)

    async def export_account(self, account_id: str) -> dict[str, Any]:
        return {
            "account": {"account_id": account_id, "sub": "sub-123", "created_at": None},
            "campaigns": [
                {
                    "campaign_id": "camp-1",
                    "status": "active",
                    "character": None,
                    "world": None,
                    "events": [],
                    "archive": [],
                    "save_slots": self._save_slots,
                }
            ],
        }


@pytest.fixture
def repo_client(api_client, monkeypatch):
    """api_client with DATABASE_URL set and a fake repo installed.

    Returns ``(client, install)`` where ``install(repo)`` swaps in a repo.
    """
    from gamebook_web.accounts import set_account_repository

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://fake/db")

    def install(repo: Any) -> None:
        set_account_repository(repo)

    yield api_client, install
    set_account_repository(None)


def test_delete_me_without_confirmation_is_400(repo_client):
    client, install = repo_client
    install(FakeAccountRepository(account_exists=True))

    resp = client.request("DELETE", "/me", headers=AUTH)  # no body
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "confirmation_required"


def test_delete_me_nonexistent_account_is_404(repo_client):
    client, install = repo_client
    install(FakeAccountRepository(account_exists=False))

    resp = client.request("DELETE", "/me", json={"confirmation": True}, headers=AUTH)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_delete_me_with_confirmation_is_204(repo_client):
    client, install = repo_client
    repo = FakeAccountRepository(account_exists=True)
    install(repo)

    resp = client.request("DELETE", "/me", json={"confirmation": True}, headers=AUTH)
    assert resp.status_code == 204
    assert repo.deleted == [DEV_ACCOUNT]


def test_export_includes_save_slots(repo_client):
    client, install = repo_client
    install(
        FakeAccountRepository(
            save_slots=[{"name": "checkpoint-1", "snapshot": {"turn": 3}, "created_at": None}]
        )
    )

    resp = client.get("/me/export", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    slots = body["campaigns"][0]["save_slots"]
    assert slots and slots[0]["name"] == "checkpoint-1"
    assert slots[0]["snapshot"] == {"turn": 3}
