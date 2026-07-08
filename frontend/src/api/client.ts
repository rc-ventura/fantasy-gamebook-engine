/**
 * Typed API client — all HTTP calls to the backend go through this module.
 *
 * Routes follow D1 backend-scoped design (spec 006, ADR-017):
 *   /me/game/...     — active game operations (no campaign_id in URL)
 *   /me/graveyard    — ended campaigns
 * The frontend never manages campaign_id; the backend resolves it from the
 * authenticated account.
 *
 * Auth seam: setTokenProvider() is the only change slice 008's real OIDC
 * needed (auth/tokenBridge.ts) — zero other component changes required.
 *
 * Mock mode: VITE_USE_MOCK=true routes all calls to mock.ts handlers.
 *
 * Contract: specs/006-cycle1-remediation/contracts/http-api.md
 */

import type {
  Account,
  ApiErrorBody,
  ApiErrorCode,
  CampaignState,
  CharacterSheet,
  CreateGameResponse,
  GraveyardEntry,
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
 * Default implementation (dev auth stub, DEV builds only): VITE_DEV_TOKEN or
 * sessionStorage. Overridden at startup by auth/tokenBridge.ts to source the
 * real OIDC id_token instead (slice 008) — see setTokenProvider() below.
 */
let _tokenProvider: () => string | null = () => {
  const stored = sessionStorage.getItem('auth_token')
  if (stored) return stored
  const devToken = import.meta.env.VITE_DEV_TOKEN
  return typeof devToken === 'string' && devToken.length > 0 ? devToken : null
}

/** Swap the auth token provider (used by auth/tokenBridge.ts's real OIDC integration). */
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

// ── Game (one active game per account, D1 backend-scoped) ────────────────────

/** POST /me/game — start a new game. Returns status + campaign_id (for debug only). */
export async function createGame(name?: string): Promise<CreateGameResponse> {
  if (USE_MOCK) return mockApi.createGame(name)
  return request<CreateGameResponse>('POST', '/me/game', { name: name ?? null })
}

/** GET /me/game — full game state (character + world + scene + summary + events). */
export async function getGame(): Promise<CampaignState> {
  if (USE_MOCK) return mockApi.getGame()
  return request<CampaignState>('GET', '/me/game')
}

/** DELETE /me/game — abandon the current game. */
export async function deleteGame(): Promise<void> {
  if (USE_MOCK) return mockApi.deleteGame()
  return request<void>('DELETE', '/me/game')
}

// ── Character ─────────────────────────────────────────────────────────────────

/** POST /me/game/character — create the hero (attributes rolled by engine). */
export async function createCharacter(name?: string): Promise<CharacterSheet> {
  if (USE_MOCK) return mockApi.createCharacter(name)
  return request<CharacterSheet>('POST', '/me/game/character', { name })
}

/** GET /me/game/character — read the character sheet (real engine state). */
export async function getCharacter(): Promise<CharacterSheet> {
  if (USE_MOCK) {
    const game = await mockApi.getGame()
    if (!game.character) throw new ApiError(404, 'not_found', 'No character found')
    return game.character
  }
  return request<CharacterSheet>('GET', '/me/game/character')
}

// ── Play loop ─────────────────────────────────────────────────────────────────

/** POST /me/game/turn — take a turn; returns validated Scene + updated game state. */
export async function takeTurn(turnReq: TurnRequest): Promise<TurnResponse> {
  if (USE_MOCK) return mockApi.takeTurn(turnReq.choice)
  return request<TurnResponse>('POST', '/me/game/turn', turnReq)
}

/** GET /me/game/scene — re-fetch the current scene (for resume/refresh). */
export async function getCurrentScene(): Promise<{ scene: Scene | null }> {
  if (USE_MOCK) return { scene: await mockApi.getScene() }
  return request<{ scene: Scene | null }>('GET', '/me/game/scene')
}

// ── Save ──────────────────────────────────────────────────────────────────────

/** POST /me/game/save — checkpoint progress (durable, atomic). */
export async function saveGame(): Promise<{ ok: boolean; slot?: string }> {
  if (USE_MOCK) { await mockApi.saveGame(); return { ok: true } }
  return request<{ ok: boolean; slot?: string }>('POST', '/me/game/save', {})
}

// ── Graveyard ─────────────────────────────────────────────────────────────────

/** GET /me/graveyard — list ended campaigns (death + victory). */
export async function getGraveyard(): Promise<GraveyardEntry[]> {
  if (USE_MOCK) return mockApi.getGraveyard()
  return request<GraveyardEntry[]>('GET', '/me/graveyard')
}

// ── Session lease (stub — real impl in slice 004) ─────────────────────────────

/** POST /me/game/session — acquire the play-session lease (slice 004). */
export async function acquireSession(): Promise<SessionLease> {
  if (USE_MOCK) return mockApi.acquireSession()
  // Slice 004 will replace with: request<SessionLease>('POST', '/me/game/session')
  return { session_token: 'stub', expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString() }
}

/** POST /me/game/session/takeover — forcibly take over the lease (slice 004). */
export async function takeoverSession(): Promise<SessionLease> {
  if (USE_MOCK) return mockApi.takeoverSession()
  return { session_token: 'stub-takeover', expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString() }
}

/** DELETE /me/game/session — release the lease (slice 004). */
export async function releaseSession(): Promise<void> {
  if (USE_MOCK) { await mockApi.releaseSession(); return }
  // Best-effort release — no-op until slice 004 implements real sessions
}
