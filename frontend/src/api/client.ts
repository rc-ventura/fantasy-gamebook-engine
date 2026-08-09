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
  _leaseToken = null
}

/** True if an auth token is currently available. */
export function isAuthenticated(): boolean {
  return _tokenProvider() !== null
}

// ── Session-lease seam (issue #15) ──────────────────────────────────────────
//
// The held lease token, set by acquireSession()/takeoverSession() and cleared
// by releaseSession(). request() attaches it as X-Session-Lease on every
// mutating call so require_lease (backend) can enforce single-writer-per-
// campaign — see ADR-023/031/032.
let _leaseToken: string | null = null

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
  if (_leaseToken && method !== 'GET') {
    headers['X-Session-Lease'] = _leaseToken
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

/**
 * POST /me/game/turn/stream — SSE variant of takeTurn (issue #20).
 *
 * Calls `onDelta` with each narrative text chunk as the narrator generates
 * it; resolves with the same TurnResponse shape takeTurn() returns once the
 * stream's `done` event arrives. Throws ApiError for any failure — a
 * pre-stream HTTP error (same codes/semantics as takeTurn, e.g.
 * no_active_campaign/run_ended) or a mid-stream `error` event (narrator
 * failure). Callers that want a fallback should retry with takeTurn() on
 * catch (see useGame.ts's runTurn()).
 *
 * Mock mode has no real streaming to simulate — it resolves mockApi.takeTurn()
 * and reports the whole narrative as a single delta, so callers don't need a
 * separate code path for VITE_USE_MOCK=true.
 */
export async function takeTurnStream(
  turnReq: TurnRequest,
  onDelta: (text: string) => void
): Promise<TurnResponse> {
  if (USE_MOCK) {
    const res = await mockApi.takeTurn(turnReq.choice)
    onDelta(res.scene.narrative)
    return res
  }

  const token = _tokenProvider()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (_leaseToken) headers['X-Session-Lease'] = _leaseToken

  let response: Response
  try {
    response = await fetch(`${BASE_URL}/me/game/turn/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(turnReq),
    })
  } catch (err) {
    throw new ApiError(0, 'unknown', err instanceof Error ? err.message : 'Network error')
  }

  if (!response.ok || !response.body) {
    // Same error-body parsing as request<T>() — a 404/409/etc here means the
    // route rejected the turn BEFORE entering the SSE generator (headers
    // aren't committed as 200 yet), identical to what takeTurn() would throw.
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

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sepIndex = buffer.indexOf('\n\n')
    while (sepIndex !== -1) {
      const block = buffer.slice(0, sepIndex)
      buffer = buffer.slice(sepIndex + 2)
      const lines = block.split('\n')
      const eventLine = lines.find((l) => l.startsWith('event: '))
      const dataLine = lines.find((l) => l.startsWith('data: '))
      if (eventLine && dataLine) {
        const eventType = eventLine.slice('event: '.length)
        const data: unknown = JSON.parse(dataLine.slice('data: '.length))

        if (eventType === 'delta') {
          onDelta((data as { text: string }).text)
        } else if (eventType === 'done') {
          return data as TurnResponse
        } else if (eventType === 'error') {
          const apiErr = data as ApiErrorBody
          throw new ApiError(
            200, // headers already committed 200 — the real failure travels inside the stream
            (apiErr.error.code as ApiErrorCode | undefined) ?? 'unknown',
            apiErr.error.message ?? 'Streaming turn failed'
          )
        }
      }
      sepIndex = buffer.indexOf('\n\n')
    }
  }

  throw new ApiError(0, 'unknown', 'Stream ended without a done event')
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

// ── Session lease (issue #15) ───────────────────────────────────────────────

/**
 * POST /me/game/session — acquire the play-session write lease.
 *
 * Succeeds unconditionally for the authenticated account (the backend only
 * 409s an *unexpired* lease held by a *different* account — see
 * LeaseService.acquire), so this also doubles as the reclaim path after a
 * 409: see takeoverSession() below.
 */
export async function acquireSession(): Promise<SessionLease> {
  if (USE_MOCK) return mockApi.acquireSession()
  const lease = await request<SessionLease>('POST', '/me/game/session')
  _leaseToken = lease.session_token
  return lease
}

/**
 * "Take over" the session lease after a 409 not_session_holder conflict.
 *
 * The backend also exposes a dedicated POST /me/game/session/takeover route,
 * but it requires presenting the *current* holder's live token (ADR-023/
 * FR-027) — a token a dispossessed tab structurally cannot know, since it
 * only ever saw its own (now-stale) one. For this single-account-per-
 * campaign app there is no cross-account takeover UI, so reclaiming your own
 * lease is just re-acquiring it: acquireSession() already succeeds
 * unconditionally for the authenticated account regardless of who currently
 * holds it. Delegating here keeps the dedicated /takeover route available
 * for a future multi-account scenario without leaving this call permanently
 * broken for the one it's actually wired to today.
 */
export async function takeoverSession(): Promise<SessionLease> {
  if (USE_MOCK) return mockApi.takeoverSession()
  return acquireSession()
}

/** DELETE /me/game/session — release the write lease. */
export async function releaseSession(): Promise<void> {
  if (USE_MOCK) { await mockApi.releaseSession(); return }
  if (!_leaseToken) return
  try {
    await request<void>('DELETE', '/me/game/session')
  } finally {
    _leaseToken = null
  }
}
