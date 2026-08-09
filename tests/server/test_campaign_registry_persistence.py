"""DB-backed CampaignRegistry (issues #14/#25, ADR-025, spec-006 T037).

The acceptance criteria from issue #14, exercised hermetically against the
functional in-memory repository from conftest:

  * after a process restart (fresh registry, same repository), the active
    campaign resolves from the durable store;
  * two replicas (two registries) sharing the same repository see the same
    campaign state;
  * without a repository, the registry keeps its previous pure in-memory
    behavior (DATABASE_URL-less dev/test runs).

Route-level restart coverage lives at the bottom: wiping the registry's
in-memory cache mid-session (what a restart does to a process) must not break
``GET /me/game`` / ``POST /me/game/turn``.
"""

from __future__ import annotations

import pytest

from gamebook_web.sessions.campaign import CampaignRegistry

AUTH = {"Authorization": "Bearer dev-token"}
ACCOUNT = "acct-persist"


# ---------------------------------------------------------------------------
# Registry-level (repository-backed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_campaign_survives_process_restart(account_repo):
    repo = account_repo
    reg1 = CampaignRegistry(repository=repo)
    created = await reg1.create(ACCOUNT, name="The Long Run")

    # "Restart": a brand-new registry with empty memory, same durable store.
    reg2 = CampaignRegistry(repository=repo)
    resolved = await reg2.get_active_for_account(ACCOUNT)

    assert resolved is not None
    assert resolved.campaign_id == created.campaign_id
    assert resolved.name == "The Long Run"
    assert resolved.status == "active"


@pytest.mark.asyncio
async def test_two_replicas_share_campaign_state(account_repo):
    repo = account_repo
    replica_a = CampaignRegistry(repository=repo)
    replica_b = CampaignRegistry(repository=repo)

    created = await replica_a.create(ACCOUNT)

    # B sees A's campaign without ever having created it.
    seen_by_b = await replica_b.get_active_for_account(ACCOUNT)
    assert seen_by_b is not None and seen_by_b.campaign_id == created.campaign_id

    # B ends it; A observes the end on its next read.
    await replica_b.set_ended(seen_by_b.campaign_id, reason="death")
    assert await replica_a.get_active_for_account(ACCOUNT) is None
    ended = await replica_a.list_ended_for_account(ACCOUNT)
    assert [c.campaign_id for c in ended] == [created.campaign_id]
    assert ended[0].ended_reason == "death"
    assert ended[0].ended_at is not None


@pytest.mark.asyncio
async def test_scene_is_transient_but_campaign_is_not(account_repo):
    repo = account_repo
    reg1 = CampaignRegistry(repository=repo)
    created = await reg1.create(ACCOUNT)
    reg1.set_scene(created.campaign_id, {"narrative": "You enter the pass."})

    reg2 = CampaignRegistry(repository=repo)
    resolved = await reg2.get_active_for_account(ACCOUNT)

    assert resolved is not None and resolved.campaign_id == created.campaign_id
    assert resolved.current_scene is None  # scene is per-process, by design


@pytest.mark.asyncio
async def test_merge_preserves_object_identity_and_scene(account_repo):
    """DB reads fold into the cached instance — a route holding the state sees
    later mutations, and the transient scene survives re-reads."""
    repo = account_repo
    reg = CampaignRegistry(repository=repo)
    created = await reg.create(ACCOUNT)
    reg.set_scene(created.campaign_id, {"narrative": "…"})

    again = await reg.get_active_for_account(ACCOUNT)
    assert again is created
    assert again.current_scene == {"narrative": "…"}


# ---------------------------------------------------------------------------
# Registry-level (no repository — legacy in-memory behavior)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_only_registry_still_works_without_repository():
    reg = CampaignRegistry()
    created = await reg.create(ACCOUNT, name="Ephemeral")

    active = await reg.get_active_for_account(ACCOUNT)
    assert active is created

    await reg.set_ended(created.campaign_id, reason="victory")
    assert await reg.get_active_for_account(ACCOUNT) is None
    ended = await reg.list_ended_for_account(ACCOUNT)
    assert ended == [created] and created.ended_reason == "victory"


# ---------------------------------------------------------------------------
# Route-level: registry wipe (= restart) mid-session
# ---------------------------------------------------------------------------

def test_get_game_survives_registry_memory_wipe(api_client, account_repo):
    from gamebook_web.api.app import app

    created = api_client.post("/me/game", headers=AUTH)
    assert created.status_code == 201
    cid = created.json()["campaign_id"]
    api_client.post("/me/game/character", json={"name": "Hero"}, headers=AUTH)

    # Simulate a backend restart: in-process memory is gone, the DB is not.
    app.state.campaign_registry.clear()

    resp = api_client.get("/me/game", headers=AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["character"]["name"] == "Hero"
    # The scene cache is transient and re-derivable — a turn works post-wipe.
    turn = api_client.post("/me/game/turn", json={"choice": "look around"}, headers=AUTH)
    assert turn.status_code == 200, turn.text

    # And the campaign resolved after the wipe is the same one (from the repo).
    assert account_repo.created[-1][1] == cid
