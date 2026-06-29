/**
 * Typed API client — all HTTP calls to the backend go through this module.
 *
 * Auth seam: the token provider function is swappable. Until slice 004 delivers
 * real OIDC, the dev stub reads from sessionStorage or VITE_DEV_TOKEN env var.
 * When 004 lands, only setTokenProvider() changes — zero component changes.
 *
 * Mock mode: when VITE_USE_MOCK=true (in .env.local), all calls dispatch to the
 * deterministic mock handlers in mock.ts instead of the real HTTP backend.
 *
 * Base URL: defaults to /api (proxied by Vite to localhost:8000 in dev).
 * Configure via VITE_API_BASE_URL in .env.local if needed.
 *
 * Contract: specs/001-web-platform-migration/contracts/http-api.md
 */

import type {
  Account,
  ApiErrorBody,
  ApiErrorCode,
  CampaignState,
  CampaignSummary,
  CharacterSheet,
  CombatRoundRequest,
  CombatRoundResponse,
  Scene,
  SessionLease,
  TurnRequest,
  TurnResponse,
} from '../types'
import { ApiError } from '../types'
import { mockApi } from './mock'

// ── Auth seam ─────────────────────────────────────────────────────────────────

/**
 * Returns the current auth token, or null if not authenticated.
 * The default implementation uses the dev auth stub (VITE_DEV_TOKEN or sessionStorage).
 * Slice 004 replaces this via setTokenProvider() without touching any component.
 */
let _tokenProvider: () => string | null = () => {
  const stored = sessionStorage.getItem('auth_token')
  if (stored) return stored
  const devToken = import.meta.env.VITE_DEV_TOKEN
  return typeof devToken === 'string' && devToken.length > 0 ? devToken : null
}

/** Swap the auth token provider (used by slice 004 real OIDC integration). */
export function setTokenProvider(fn: () => string | null): void {
  _tokenProvider = fn
}

/** Store an auth token (dev auth stub). */
export function setAuthToken(token: string): void {
  sessionStorage.setItem('auth_token', token)
}

/** Clear the stored auth token. */
export function clearAuthToken(): void {
  sessionStorage.removeItem('auth_token')
}

/** True if an auth token is currently available. */
export function isAuthenticated(): boolean {
  return _tokenProvider() !== null
}

// ── HTTP core ─────────────────────────────────────────────────────────────────

const BASE_URL: string = (() => {
  const env = import.meta.env.VITE_API_BASE_URL
  return typeof env === 'string' && env.length > 0 ? env : '/api'
})()

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = _tokenProvider()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    throw new ApiError(0, 'unknown', err instanceof Error ? err.message : 'Network error')
  }

  if (!response.ok) {
    let code: ApiErrorCode = 'unknown'
    let message = `HTTP ${response.status.toString()}`
    try {
      const text = await response.text()
      const data: unknown = JSON.parse(text)
      const apiErr = data as ApiErrorBody
      code = (apiErr.error.code as ApiErrorCode | undefined) ?? 'unknown'
      message = apiErr.error.message ?? message
    } catch {
      // Ignore JSON parse errors — use defaults
    }
    throw new ApiError(response.status, code, message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  const parsed: unknown = JSON.parse(text)
  return parsed as T
}

// ── Mock mode dispatch ─────────────────────────────────────────────────────────

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// ── Identity & account ─────────────────────────────────────────────────────────

/** GET /me — current account summary. */
export async function getAccount(): Promise<Account> {
  if (USE_MOCK) return mockApi.getAccount()
  return request<Account>('GET', '/me')
}

// ── Campaigns ─────────────────────────────────────────────────────────────────

/** GET /campaigns — list the caller's campaigns. */
export async function listCampaigns(): Promise<CampaignSummary[]> {
  if (USE_MOCK) return mockApi.listCampaigns()
  return request<CampaignSummary[]>('GET', '/campaigns')
}

/** POST /campaigns — start a new campaign. */
export async function createCampaign(): Promise<CampaignSummary> {
  if (USE_MOCK) return mockApi.createCampaign()
  return request<CampaignSummary>('POST', '/campaigns', {})
}

/** GET /campaigns/{id} — full campaign state (character + world + scene). */
export async function getCampaign(id: string): Promise<CampaignState> {
  if (USE_MOCK) return mockApi.getCampaign(id)
  return request<CampaignState>('GET', `/campaigns/${id}`)
}

/** DELETE /campaigns/{id} — delete a campaign. */
export async function deleteCampaign(id: string): Promise<void> {
  if (USE_MOCK) return mockApi.deleteCampaign(id)
  return request<void>('DELETE', `/campaigns/${id}`)
}

// ── Session lease (FR-025) ────────────────────────────────────────────────────

/** POST /campaigns/{id}/session — acquire or refresh the play-session lease. */
export async function acquireSession(id: string): Promise<SessionLease> {
  if (USE_MOCK) return mockApi.acquireSession(id)
  return request<SessionLease>('POST', `/campaigns/${id}/session`)
}

/** POST /campaigns/{id}/session/takeover — forcibly take over the lease. */
export async function takeoverSession(id: string): Promise<SessionLease> {
  if (USE_MOCK) return mockApi.takeoverSession(id)
  return request<SessionLease>('POST', `/campaigns/${id}/session/takeover`)
}

/** DELETE /campaigns/{id}/session — release the lease. */
export async function releaseSession(id: string): Promise<void> {
  if (USE_MOCK) return mockApi.releaseSession(id)
  return request<void>('DELETE', `/campaigns/${id}/session`)
}

// ── Character ─────────────────────────────────────────────────────────────────

/** POST /campaigns/{id}/character — create the hero (attributes rolled by engine). */
export async function createCharacter(id: string, name?: string): Promise<CharacterSheet> {
  if (USE_MOCK) return mockApi.createCharacter(id, name)
  return request<CharacterSheet>('POST', `/campaigns/${id}/character`, { name })
}

/** GET /campaigns/{id}/character — read the character sheet (real engine state). */
export async function getCharacter(id: string): Promise<CharacterSheet> {
  if (USE_MOCK) {
    const campaign = await mockApi.getCampaign(id)
    if (!campaign.character) throw new ApiError(404, 'not_found', 'No character found')
    return campaign.character
  }
  return request<CharacterSheet>('GET', `/campaigns/${id}/character`)
}

// ── Play loop ─────────────────────────────────────────────────────────────────

/** POST /campaigns/{id}/turn — take a turn; returns validated Scene + updated campaign. */
export async function takeTurn(id: string, turnReq: TurnRequest): Promise<TurnResponse> {
  if (USE_MOCK) {
    return mockApi.takeTurn(id, turnReq.choice_id, turnReq.free_text)
  }
  return request<TurnResponse>('POST', `/campaigns/${id}/turn`, turnReq)
}

/** GET /campaigns/{id}/scene — re-fetch the current scene (for resume/refresh). */
export async function getCurrentScene(id: string): Promise<Scene> {
  if (USE_MOCK) return mockApi.getScene(id)
  return request<Scene>('GET', `/campaigns/${id}/scene`)
}

// ── Combat ────────────────────────────────────────────────────────────────────

/** POST /campaigns/{id}/combat/round — resolve a combat round (engine-computed). */
export async function combatRound(id: string, req: CombatRoundRequest): Promise<CombatRoundResponse> {
  if (USE_MOCK) return mockApi.combatRound(id, req.test_luck ?? false)
  return request<CombatRoundResponse>('POST', `/campaigns/${id}/combat/round`, req)
}

/** POST /campaigns/{id}/combat/flee — attempt to flee combat. */
export async function fleeCombat(id: string): Promise<{ campaign: CampaignState }> {
  if (USE_MOCK) return mockApi.fleeCombat(id)
  return request<{ campaign: CampaignState }>('POST', `/campaigns/${id}/combat/flee`, {})
}

// ── Save ──────────────────────────────────────────────────────────────────────

/** POST /campaigns/{id}/save — checkpoint progress (durable, atomic). */
export async function saveCampaign(id: string): Promise<void> {
  if (USE_MOCK) return mockApi.saveCampaign(id)
  return request<void>('POST', `/campaigns/${id}/save`, {})
}
