/**
 * TypeScript types mirroring the Scene schema and engine domain entities.
 *
 * ALL values displayed in the UI must come from these API types.
 * The frontend NEVER invents, rolls, or fabricates any stat or number.
 *
 * Field names match the backend (ADR-017 — backend wins):
 *   WorldState: current_location, visited_locations (not location/visited)
 *   TurnRequest: choice (not choice_id/free_text)
 *   CampaignState: no id field — routes are /me/game/... (D1, spec 006)
 *
 * Contracts:
 *   docs/CONTRACTS.md §10 (Scene — updated spec 007, ADR-029)
 *   specs/006-cycle1-remediation/contracts/http-api.md
 */

// ── Scene (narrator structured output, CONTRACTS.md §10) ────────────────────
// spec 007 (ADR-029): narrator calls MCP tools directly during generation.
// Scene carries only prose and choices — no deferred effects.

export interface Choice {
  id: string
  label: string
}

/** Structured unit the narrator produces for one turn.
 *  narrative + choices only — no effects field (spec 007, ADR-029).
 *  terminal=true on death/victory scenes (choices will be empty).
 */
export interface Scene {
  narrative: string
  choices: Choice[]
  terminal?: boolean
}

// ── Engine domain entities (per data-model.md §A) ───────────────────────────

/** Tracks both initial (maximum) and current value. All bounds enforced by engine. */
export interface Attribute {
  initial: number
  current: number
}

export interface InventoryItem {
  id: string
  name: string
  quantity?: number
}

export interface CharacterSheet {
  name?: string
  skill: Attribute
  stamina: Attribute
  luck: Attribute
  gold: number
  provisions: number
  inventory: InventoryItem[]
  conditions: string[]
  alive: boolean
}

/** Backend-canonical field names (ADR-017 backend wins, spec 006 D1). */
export interface WorldState {
  current_location: string
  visited_locations: string[]
  flags: Record<string, boolean | string | number>
  known_npcs?: unknown[]
  turn?: number
}

// ── Game (web-layer entity, D1 backend-scoped routes) ───────────────────────

export type CampaignStatus = 'active' | 'ended'

/** Full game state from GET /me/game. No campaign_id — the frontend never
 *  manages campaign_id; the backend resolves it from the authenticated account
 *  (spec 006, D1, ADR-017).
 */
export interface CampaignState {
  status: CampaignStatus
  name?: string | null
  character?: CharacterSheet
  world?: WorldState
  current_scene?: Scene
  summary?: string
  events?: unknown[]
}

/** Response from POST /me/game. campaign_id is returned for debug/reference;
 *  the SPA does not store or route using it.
 */
export interface CreateGameResponse {
  status: string
  campaign_id: string
  name?: string | null
}

/** Entry in GET /me/graveyard (ended campaign tombstone). */
export interface GraveyardEntry {
  campaign_id: string
  status: 'ended'
  name: string | null
  created_at: string | null
  ended_at: string | null
  ended_reason: 'death' | 'victory' | null
}

// ── Account / Identity ───────────────────────────────────────────────────────

export interface Account {
  id: string
  email?: string
}

// ── Session lease (placeholder — real impl in slice 004) ─────────────────────

export interface SessionLease {
  session_token: string
  expires_at: string
}

// ── API error shape ──────────────────────────────────────────────────────────

export interface ApiErrorBody {
  error: {
    code: string
    message: string
  }
}

export type ApiErrorCode =
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'no_active_campaign'
  | 'not_session_holder'
  | 'run_ended'
  | 'invalid_scene'
  | 'auth_unavailable'
  | 'unknown'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number

  constructor(status: number, code: ApiErrorCode, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

// ── Turn request / response ───────────────────────────────────────────────────

/** Player input — choice ID or free-text; backend field is `choice` (ADR-017). */
export interface TurnRequest {
  choice?: string | number | null
}

export interface TurnResponse {
  scene: Scene
  status: CampaignStatus
  character?: CharacterSheet
  world?: WorldState
}
