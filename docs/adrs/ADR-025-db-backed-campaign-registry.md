# ADR-025: DB-backed campaign registry replaces the in-memory CampaignRegistry

**Status**: Accepted | **Date**: 2026-06-28 | **Spec**: [006-cycle1-remediation](../../specs/006-cycle1-remediation/)

## Context

Slice 003 shipped `CampaignRegistry` (`src/gamebook_web/sessions/campaign.py`) as an
in-memory dev stub: a dict of `CampaignState` living in `app.state`. The cycle-1 review
flagged the consequences of promoting it to production unchanged:

- **No durability** — a process restart forgets which campaigns exist, which one is
  active, and every graveyard entry, even though the engine state itself is safely in
  Postgres. The registry and the engine disagree after any restart.
- **No ownership integrity** — `account_id` is a plain string field with no FK; nothing
  prevents a campaign row pointing at a deleted account, and `create_campaign` cannot
  detect duplicate IDs reliably across processes.
- **No horizontal scale** — two API replicas hold two divergent registries.

## Decision

Replace `CampaignRegistry` with an **`AccountRepository`** backed by the same Postgres
database the engine uses (slice 004 migration `0002_accounts_session_lease.py`):

- `account` table (OIDC `sub` → account row, created on first login).
- `campaign.account_id` becomes a real FK → `account.id` (CASCADE on account erasure,
  satisfying GDPR delete).
- Campaign status (`active`/`ended`), `name`, `created_at`, `ended_at`, `ended_reason`
  move from dataclass fields to columns — the graveyard survives restarts.
- Duplicate campaign creation returns `409` from a DB uniqueness violation, not an
  in-memory check.
- The play loop keeps talking to the same interface (`get_active_for_account`,
  `set_ended`, `list_ended_for_account`, …), so `play.py` routes do not change — this is
  the same swap-behind-an-interface discipline as storage boundary #1.

## Consequences

- The in-memory `CampaignRegistry` remains the test double (fast, isolated per test) —
  exactly like `InMemoryStorage` vs `PostgresStorage`.
- Session-lease state (ADR-023) lands in the same database, so "who owns this campaign"
  and "who holds the write lease" are answered by one consistent store.
- Implementation is scheduled with slice 004 (the `AccountRepository`, `accounts.py`,
  and migration 0002 live on the 004 branch); spec 006 records the decision and shapes
  the API layer (D1 `/me/game/...` routes already resolve campaigns per account).
