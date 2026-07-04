# Contract Draft — HTTP API

Feature: Web Platform Migration · Date: 2026-06-26 · Last updated: 2026-07-01 (spec 006, D1 — backend-scoped routes)
Status: **authoritative** (folded into `docs/CONTRACTS.md` §9).

> **Spec 006 (D1) redesign:** All game routes moved from `/campaigns/{id}/...` to `/me/game/...`.
> The backend resolves `campaign_id` from the authenticated account; the frontend never sees or
> manages `campaign_id`. One active game per account at any time.

> **Spec 007 (ADR-029) breaking change:** Combat routes removed. Combat is now driven entirely by
> the narrator calling MCP tools directly during `agent.run()`. These routes no longer exist.

The HTTP API exposes the engine's full play loop. **The UI and external clients use this same
surface — no privileged hidden path** (FR-017). All routes require a valid bearer token from the
auth service (FR-010); every operation is scoped to the authenticated account (FR-009). Errors use a
consistent JSON shape. Concrete request/response schemas reuse the engine domain models and the
`Scene` type (`contracts/scene.md`); only the operations are enumerated here.

## Conventions
- **Auth**: `Authorization: Bearer <JWT>` validated against the IdP (signature/aud/exp).
- **Format**: JSON in/out; OpenAPI auto-generated (FR-016).
- **Scoping**: the backend resolves `campaign_id` from `account_id` — the frontend never passes it.
- **One active game**: `POST /me/game` ends any prior active game before creating a new one.
- **Write gating**: state-changing routes require holding the campaign's session lease (FR-025);
  otherwise → `409 not_session_holder`.
- **Numbers**: every numeric/state change is produced by the engine via MCP — never by the client.

## Identity & account
| Method & path | Purpose | Notes |
|---|---|---|
| `GET /me` | Current account summary | Created on first call from the JWT `sub` |
| `GET /me/export` | Export this account's game data | GDPR export (research §8) |
| `DELETE /me` | Delete account + all owned game data | GDPR erasure; cascades (data-model E) |

## Active game (one per account, D1)
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /me/game` | Start a new game | Ends prior active game; begins adventure opening. Returns `{ campaign_id, status }` |
| `GET /me/game` | Read full game state | character sheet + world + current scene + summary (session-opening read, FR-003). `404 no_active_campaign` if none |
| `DELETE /me/game` | Abandon current game | Marks the game as `ended`; no `campaign_id` in URL |

## Session lease (single active session — FR-025)
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /me/game/session` | Acquire/refresh the play-session lease | Returns lease token |
| `POST /me/game/session/takeover` | Forcibly take over the lease | Demotes prior holder to read-only |
| `DELETE /me/game/session` | Release the lease | |

## Character
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /me/game/character` | Create the hero | Attributes rolled by the engine (skill 1d6+6, etc.) via MCP — never client-supplied |
| `GET /me/game/character` | Read the character sheet | Real engine state (FR-021); used by `/hero`-style views |

## Play loop
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /me/game/turn` | Take a turn (choice index or free text) | Runs the narrator; returns `{ scene, status, character?, world? }`; all rolls/effects via MCP (FR-001/002/004). Combat resolved by narrator inside `agent.run()` (ADR-029) |
| `GET /me/game/scene` | Re-fetch the current scene | For resume/refresh |

## Save / resume
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /me/game/save` | Checkpoint progress | Durable, atomic (Principle V) |
| Resume | (implicit) | `GET /me/game` resumes from the exact recorded point (FR-003) |

## Graveyard (ended games)
| Method & path | Purpose | Notes |
|---|---|---|
| `GET /me/graveyard` | List all ended games | Returns `[{ campaign_id, status, name?, created_at?, ended_at?, ended_reason? }]` |

## Errors (consistent shape)
```json
{ "error": { "code": "not_session_holder", "message": "..." } }
```
| HTTP | `code` examples | Meaning |
|---|---|---|
| 401 | `unauthenticated` | Missing/invalid token (FR-010) |
| 403 / 404 | `forbidden` / `not_found` | Resource not owned by caller (FR-009) |
| 404 | `no_active_campaign` | No active game for this account; hint: POST /me/game |
| 409 | `not_session_holder`, `run_ended` | Lacks write lease; or acting on a finished run |
| 422 | `invalid_scene` | Narrator output failed schema validation (FR-014) — never persisted |
| 503 | `auth_unavailable` | IdP down; degrade gracefully (FR-024) |

## Mapping to requirements
FR-001/004 → `POST /me/game/turn`; FR-003 → `GET /me/game`; FR-006 → end-states in `Scene` +
game `ended`; FR-007/008/010 → auth + `/me`; FR-009 → account scoping (backend resolves campaign);
FR-011/012 → save/resume + atomic writes; FR-014 → `422 invalid_scene`; FR-015/016/017 → this
documented shared API; FR-025 → session-lease routes.
