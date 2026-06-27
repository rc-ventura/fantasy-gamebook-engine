# Phase 1 — Data Model

Feature: Web Platform Migration · Date: 2026-06-26

This describes the entities for Phase 2. The **engine domain entities are unchanged** — they already
live in `src/gamebook/domain/` and `docs/CONTRACTS.md` §2 is authoritative for their shape. Phase 2
adds (a) a Postgres mapping for those entities behind `StorageBackend`, (b) account/ownership and
session-lease entities for the web layer, and (c) the `Scene` validation type. Nothing here changes
engine invariants; it adds persistence and ownership around them.

## A. Engine domain entities (unchanged — authoritative in CONTRACTS.md §2)

| Entity | Key fields (summary) | Invariants (in `domain`) |
|---|---|---|
| `CharacterSheet` | skill/stamina/luck (each `initial`/`current`), gold, provisions, inventory[], conditions[], `alive` | `0 <= current <= initial` per Attribute; serialization round-trips |
| `World` | current location, visited[], flags{} | flags drive progression; written only via MCP (`update_world`) |
| `Event` | ordered record of hard facts (decisions, outcomes) | append-only; used to resume + keep narration consistent |
| `Combat` | participants, rounds, outcome | transient; luck tally ephemeral (ADR-006) |
| `ArchiveRecord` | finished run (death/victory) | immutable once archived |

These map ~1:1 to Postgres tables (per CONTRACTS.md §2 design intent). No field changes.

## B. Postgres mapping (`PostgresStorage`, swap boundary #1)

All engine tables are **scoped to a campaign**, and every campaign is **owned by an account**. The
`StorageBackend` interface signature is unchanged; `PostgresStorage` implements it against these
tables. Writes for one state change occur in a single transaction (Principle V).

```text
account            (id PK, idp_subject UNIQUE, created_at)            -- B.1
campaign           (id PK, account_id FK→account, status, created_at, updated_at)
character_sheet    (campaign_id PK/FK→campaign, data JSONB|columns, alive)
world              (campaign_id PK/FK→campaign, location, visited JSONB, flags JSONB)
event              (id PK, campaign_id FK→campaign, seq, payload JSONB, created_at)  -- append-only
combat             (campaign_id PK/FK→campaign, state JSONB|null)      -- transient, nullable
archive_record     (id PK, campaign_id FK→campaign, payload JSONB, archived_at)      -- immutable
session_lease      (campaign_id PK/FK→campaign, session_token, holder, expires_at)   -- B.2 / FR-025
```

Notes:
- `data JSONB` vs explicit columns is an implementation choice; either must round-trip the domain
  object exactly (Principle V). Attribute bounds stay enforced in `domain`, not the DB.
- `event.seq` preserves order; events are never updated or deleted in normal play (append-only).
- All reads/writes are filtered by `account_id` at the API layer for per-account isolation (FR-009).

## C. Web-layer entities (new)

### C.1 Account / Player Identity
- **Represents**: a registered user (owner of campaigns); distinct from the in-game character.
- **Source of truth for credentials/profile**: the **separate auth service** (OIDC). The engine
  stores only `idp_subject` (opaque `sub`) + minimal metadata — PII minimization (research §8).
- **Lifecycle**: created on first authenticated access; deletable via `DELETE /me` (cascades to all
  owned campaigns and their engine rows) — GDPR erasure (research §8).
- **Relationships**: one account → many campaigns; one campaign → one account.

### C.2 Campaign
- **Represents**: one playthrough = one CharacterSheet + World + Events + (transient) Combat +
  Archive. The unit of ownership and of the single-active-session rule.
- **States**: `active` (living character) → `ended` (death/victory → ArchiveRecord written).
- **Relationships**: owns exactly one CharacterSheet/World; many Events; at most one live Combat.

### C.3 Session Lease (FR-025)
- **Represents**: which session currently holds write rights for a campaign.
- **Fields**: `campaign_id`, `session_token`, `holder` (client/session id), `expires_at`.
- **Rules**: only the lease holder may issue state-changing operations; a second opener is read-only
  until an explicit take-over atomically reassigns the lease and demotes the previous holder; stale
  writes (token mismatch/expired) are rejected. Composes with atomic commits.

### C.4 Scene (narrator output — validated, not persisted as-is)
- **Represents**: the structured unit the narrator produces for one turn, rendered by the UI.
- **Shape**: `{ narrative: str, choices: Choice[], effects: Effect[] }` — see `contracts/scene.md`.
- **Validation**: Pydantic v2; a structurally invalid `Scene` is rejected before it reaches storage
  or the player (FR-014). `effects[]` reference engine operations (not literal numbers) so the
  narrator cannot fabricate values (Principle I).
- **Persistence**: the *narrative text* may be summarized into the engine summary/events via MCP;
  the `Scene` object itself is a transport/validation type, not a new engine table.

## D. State transitions (campaign lifecycle)

```text
(no character) --create_character--> active
active --explore/choices/combat (via MCP)--> active
active --death--> ended (ArchiveRecord: graveyard)
active --victory flag (e.g. malachar_defeated)--> ended (ArchiveRecord: hall of fame)
ended --(read-only)--> ended         # cannot continue a finished run (spec edge case)
```

## E. Ownership & isolation rules (cross-cutting)

- Every engine read/write is scoped to `account_id = authenticated sub` (FR-009, FR-010).
- Unauthenticated requests are rejected (FR-010).
- Erasure (`DELETE /me`) cascades account → campaigns → {character_sheet, world, event, combat,
  archive_record, session_lease}; export (`GET /me/export`) returns the account's game data
  portably (research §8).
