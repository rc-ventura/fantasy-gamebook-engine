# Contract: HTTP API (Cycle-1 Remediation — spec 006)

**Date**: 2026-07-01 | **Status**: Authoritative for spec 006 implementation.

This document supersedes the `specs/001-web-platform-migration/contracts/http-api.md`
for the spec 006 implementation. Key changes: backend-scoped routes (D1), combat routes
removed (spec 007 / ADR-029), error codes for structured `no_active_campaign` response.

---

## Conventions

- **Auth**: `Authorization: Bearer <JWT>` on all routes (except sign-in / health).
- **Format**: JSON in/out.
- **Ownership**: all game routes resolve to the authenticated account's active campaign.
  There is no `{campaign_id}` in the URL — the backend resolves it.
- **Write gating**: state-changing game routes require holding the campaign's session
  lease (`VITE_SESSION_LEASE=true`); otherwise → `409 not_session_holder`.
- **Numbers**: every numeric/state change produced by the engine via MCP, never by
  the client.

---

## Identity & account

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/me` | Current account identity (dev stub → `{ id: account_id }`) |
| `GET` | `/me/export` | GDPR data export (rate-limited) |
| `DELETE` | `/me` | Account + data erasure (requires `confirmation` in body) |

---

## Active game (one per account)

| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| `POST` | `/me/game` | Create a new game / start fresh | Body: `{ name?: string }` |
| `GET` | `/me/game` | Get current game state | Returns character + world + summary + events + current scene |
| `DELETE` | `/me/game` | Abandon current game | Marks campaign `ended` without archiving |

**`GET /me/game` when no active campaign**:
```json
{ "error": { "code": "no_active_campaign", "message": "...", "hint": "POST /me/game to start a new game" } }
```
HTTP 404. The SPA intercepts this code and routes the player to the start screen.

---

## Character

| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| `POST` | `/me/game/character` | Create the hero | Engine rolls stats via MCP — no client stats |
| `GET` | `/me/game/character` | Read character sheet | Real engine state |

**`POST /me/game/character` body**: `{ name?: string }` (default `"Hero"`).

---

## Play loop

| Method | Path | Purpose | Notes |
|--------|------|---------|-------|
| `POST` | `/me/game/turn` | Take a turn | Body: `{ choice?: string \| number }` |
| `GET` | `/me/game/scene` | Re-fetch current scene | For resume/refresh |

**`POST /me/game/turn` flow (ADR-029)**:
1. Read engine state (character, world, summary, events).
2. Narrator calls MCP tools during `agent.run()` (via `ScopedMCPToolset`).
3. Narrator emits `Scene` with real numbers already in `narrative`.
4. API validates `Scene` → re-reads state → checks terminal conditions.
5. Returns `TurnResponse`.

**Combat**: auto-resolved inside `POST /me/game/turn` by the narrator calling combat
MCP tools directly. No separate `POST /combat/round` endpoint.

---

## Session lease

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/me/game/session` | Acquire / refresh the play-session lease |
| `POST` | `/me/game/session/takeover` | Force-acquire lease (validates `current_token`) |
| `DELETE` | `/me/game/session` | Release the lease |

---

## Save / resume

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/me/game/save` | Checkpoint progress (durable, atomic) |
| _(implicit)_ | `GET /me/game` | Resumes from exact recorded point (FR-003) |

---

## Graveyard (ended campaigns)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/me/graveyard` | List all ended campaigns (death + victory) |

**`GET /me/graveyard` response**:
```json
[
  {
    "campaign_id": "...",
    "status": "ended",
    "name": "My Hero",
    "created_at": "2026-07-01T...",
    "ended_at": "2026-07-01T...",
    "ended_reason": "death"
  }
]
```

Individual graveyard entry deletion is not supported in this slice.
`DELETE /me` (GDPR erasure) cascades all entries.

---

## Response shapes

### `TurnResponse`
```json
{
  "scene": {
    "narrative": "...",
    "choices": [{ "id": "1", "label": "..." }],
    "terminal": false
  },
  "status": "active",
  "character": { /* CharacterSheet */ },
  "world": { /* WorldState */ }
}
```
No `effects_applied` field (removed in spec 007).

### `GameState` (from `GET /me/game`)
```json
{
  "status": "active",
  "character": { /* CharacterSheet or null */ },
  "world": { /* WorldState */ },
  "summary": "...",
  "events": [...],
  "current_scene": { /* Scene or null */ }
}
```

### `GraveyardEntry`
```json
{
  "campaign_id": "...",
  "status": "ended",
  "name": "My Hero",
  "created_at": "...",
  "ended_at": "...",
  "ended_reason": "death"
}
```

---

## Error shape (consistent)

```json
{ "error": { "code": "...", "message": "...", "hint": "..." } }
```

| HTTP | Code | Meaning |
|------|------|---------|
| 401 | `unauthenticated` | Missing/invalid token |
| 403 | `forbidden` | Account mismatch |
| 404 | `not_found` | Resource not found |
| 404 | `no_active_campaign` | No active game — POST /me/game to start |
| 409 | `not_session_holder` | Lacks write lease |
| 409 | `run_ended` | Game is already ended |
| 409 | `character_exists` | Hero already created for this game |
| 422 | `invalid_scene` | Narrator output failed validation |
| 503 | `auth_unavailable` | IdP down |

---

## Removed routes (spec 007 / ADR-029)

These routes existed in spec 003/005 but are removed in spec 007:

| ~~Route~~ | ~~Purpose~~ | ~~Why removed~~ |
|-----------|-------------|-----------------|
| ~~`POST /campaigns/{id}/combat/round`~~ | Combat round | `combat.py` deleted in spec 007 |
| ~~`POST /campaigns/{id}/combat/flee`~~ | Flee combat | `combat.py` deleted in spec 007 |
| ~~`GET /campaigns`~~ | List campaigns | Replaced by `GET /me/graveyard` (D1) |

---

## Requirement mapping

| Route | FRs |
|-------|-----|
| `POST /me/game` | FR-004b, D1 |
| `GET /me/game` | FR-003, FR-004b |
| `POST /me/game/character` | FR-001 (engine rolls stats) |
| `POST /me/game/turn` | FR-001, FR-002 (ADR-029 narrator + MCP) |
| `GET /me/graveyard` | FR-048, D1 |
| `GET /me` | FR-007 |
| All routes | ADR-017 (backend-canonical shapes) |
