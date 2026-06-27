# Contract Draft — HTTP API

Feature: Web Platform Migration · Date: 2026-06-26 · Status: **draft** (to be folded into
`docs/CONTRACTS.md` per Principle III before/with implementation).

The HTTP API exposes the engine's full play loop. **The UI and external clients use this same
surface — no privileged hidden path** (FR-017). All routes require a valid bearer token from the
auth service (FR-010); every operation is scoped to the authenticated account (FR-009). Errors use a
consistent JSON shape. Concrete request/response schemas reuse the engine domain models and the
`Scene` type (`contracts/scene.md`); only the operations are enumerated here.

## Conventions
- **Auth**: `Authorization: Bearer <JWT>` validated against the IdP (signature/aud/exp).
- **Format**: JSON in/out; OpenAPI auto-generated (FR-016).
- **Scoping**: `{campaign_id}` must belong to the caller's account or → `404`/`403`.
- **Write gating**: state-changing routes require holding the campaign's session lease (FR-025);
  otherwise → `409 not_session_holder`.
- **Numbers**: every numeric/state change is produced by the engine via MCP — never by the client.

## Identity & account
| Method & path | Purpose | Notes |
|---|---|---|
| `GET /me` | Current account summary | Created on first call from the JWT `sub` |
| `GET /me/export` | Export this account's game data | GDPR export (research §8) |
| `DELETE /me` | Delete account + all owned game data | GDPR erasure; cascades (data-model E) |

## Campaigns
| Method & path | Purpose | Notes |
|---|---|---|
| `GET /campaigns` | List the caller's campaigns | Own campaigns only (FR-009) |
| `POST /campaigns` | Start a new campaign | Offers character creation; begins adventure opening |
| `GET /campaigns/{id}` | Read full campaign state | character sheet + world + recent events + summary (session-opening read, FR-003) |
| `DELETE /campaigns/{id}` | Delete one campaign | |

## Session lease (single active session — FR-025)
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /campaigns/{id}/session` | Acquire/refresh the play-session lease | Returns lease token; read-only if another holder is active |
| `POST /campaigns/{id}/session/takeover` | Forcibly take over the lease | Demotes prior holder to read-only |
| `DELETE /campaigns/{id}/session` | Release the lease | |

## Character
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /campaigns/{id}/character` | Create the hero | Attributes rolled by the engine (skill 1d6+6, etc.) via MCP — never client-supplied |
| `GET /campaigns/{id}/character` | Read the character sheet | Real engine state (FR-021); used by `/hero`-style views |

## Play loop
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /campaigns/{id}/turn` | Take a turn (choice index or free text) | Runs the narrator; returns a validated `Scene`; all rolls/effects via MCP (FR-001/002/004) |
| `GET /campaigns/{id}/scene` | Re-fetch the current scene | For resume/refresh |

## Combat
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /campaigns/{id}/combat/round` | Resolve a combat round | Optional `test_luck` flag; engine computes outcome (FR-005) |
| `POST /campaigns/{id}/combat/flee` | Attempt to flee | Only if `flee_allowed`; costs engine-computed damage |

> Combat is normally driven *inside* a turn by the narrator's combat subagent; these routes exist
> for explicit/stepwise control and for external API clients.

## Save / resume
| Method & path | Purpose | Notes |
|---|---|---|
| `POST /campaigns/{id}/save` | Checkpoint progress | Durable, atomic (Principle V) |
| Resume | (implicit) | `GET /campaigns/{id}` resumes from the exact recorded point (FR-003) |

## Errors (consistent shape)
```json
{ "error": { "code": "not_session_holder", "message": "..." } }
```
| HTTP | `code` examples | Meaning |
|---|---|---|
| 401 | `unauthenticated` | Missing/invalid token (FR-010) |
| 403 / 404 | `forbidden` / `not_found` | Campaign not owned by caller (FR-009) |
| 409 | `not_session_holder`, `run_ended` | Lacks write lease; or acting on a finished run (edge case) |
| 422 | `invalid_scene` | Narrator output failed schema validation (FR-014) — never persisted |
| 503 | `auth_unavailable` | IdP down; degrade gracefully (FR-024) |

## Mapping to requirements
FR-001/004 → `POST /turn`; FR-003 → `GET /campaigns/{id}`; FR-005 → combat routes; FR-006 →
end-states surfaced in `Scene` + campaign `ended`; FR-007/008/010 → auth + `/me`; FR-009 → account
scoping; FR-011/012 → save/resume + atomic writes; FR-014 → `422 invalid_scene`; FR-015/016/017 →
this documented, shared API; FR-025 → session-lease routes.
