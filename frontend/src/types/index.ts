/**
 * TypeScript types mirroring the Scene schema and engine domain entities.
 *
 * ALL values displayed in the UI must come from these API types.
 * The frontend NEVER invents, rolls, or fabricates any stat or number.
 *
 * Contracts:
 *   docs/CONTRACTS.md §10 (Scene — updated spec 007, ADR-029)
 *   specs/001-web-platform-migration/data-model.md §A
 */

// ── Scene (narrator structured output, CONTRACTS.md §10) ────────────────────
// Updated spec 007 (ADR-029): narrator calls MCP tools directly during
// generation. Scene carries only prose and choices — no deferred effects.

export interface Choice {
  id: string
  label: string
}

/** The structured unit the narrator produces for one turn.
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

export interface WorldState {
  location: string
  visited: string[]
  flags: Record<string, boolean | string | number>
}

// ── Campaign (web-layer entity) ──────────────────────────────────────────────

export type CampaignStatus = 'active' | 'ended'

export interface CampaignSummary {
  id: string
  status: CampaignStatus
  created_at: string
  updated_at: string
}

export interface CampaignState {
  id: string
  status: CampaignStatus
  character?: CharacterSheet
  world?: WorldState
  current_scene?: Scene
}

// ── Account / Identity ───────────────────────────────────────────────────────

export interface Account {
  id: string
  email?: string
}

// ── Session lease (FR-025) ────────────────────────────────────────────────────

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

// ── Turn request ─────────────────────────────────────────────────────────────

export interface TurnRequest {
  /** Choice ID from the current scene's choices array. Mutually exclusive with free_text. */
  choice_id?: string
  /** Free-text input from the player. Mutually exclusive with choice_id. */
  free_text?: string
}

export interface TurnResponse {
  scene: Scene
  character?: CharacterSheet
  world?: WorldState
}

