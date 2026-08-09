/**
 * useGame — core game-state hook for the play loop.
 *
 * Loads and holds the full game state (character, world, scene).
 * All numeric values come from the API — this hook never fabricates any stat.
 * Combat is now resolved inside the narrator's tool-use loop (ADR-029);
 * the frontend has no separate combat endpoints.
 *
 * Routes are /me/game/... — no campaign_id param (D1, spec 006, ADR-017).
 *
 * Handles:
 *   - Loading game state on mount
 *   - Taking turns (choice or free text, both sent as `choice`)
 *   - Session lease acquisition and 409 conflict detection
 *   - Error and loading states
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import type { CampaignState, TurnRequest, TurnResponse } from '../types'
import { ApiError } from '../types'
import {
  getGame,
  takeTurn,
  takeTurnStream,
  acquireSession,
  takeoverSession,
  releaseSession,
  saveGame,
} from '../api'
import { redirectToAuth } from '../utils/navigation'

/** Session-lease flag (FR-007, issue #15): default ON.
 *  Read lazily so tests can stub the env var without re-importing the module. */
function sessionLeaseEnabled(): boolean {
  return import.meta.env.VITE_SESSION_LEASE === 'true'
}

function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && (err.code === 'unauthenticated' || err.code === 'forbidden')
}

/**
 * Sanitize an error for display (FR-059): users get a generic message;
 * the raw error goes to the console in dev builds only.
 */
function sanitizeError(err: unknown, fallback: string): string {
  if (import.meta.env.DEV) {
    console.error(fallback, err)
  }
  return 'Something went wrong. Please try again.'
}

export type GameLoadState = 'idle' | 'loading' | 'ready' | 'error'
export type ActionState = 'idle' | 'pending' | 'error'

export interface GameState {
  /** Overall loading state of the game. */
  loadState: GameLoadState
  /** State of the last turn action. */
  actionState: ActionState
  /** Full game state from the API — all values are engine-produced. */
  campaign: CampaignState | null
  /** Human-readable error message, if any. */
  error: string | null
  /** True when another session holds the write lease (409). */
  sessionConflict: boolean
  /** ISO timestamp of the last successful save, or null. */
  lastSavedAt: string | null
  /**
   * Narrative text accumulated so far from a streaming turn (issue #20) —
   * null when no turn is in flight or streaming produced nothing yet.
   * Components may render this instead of campaign.current_scene.narrative
   * while actionState is 'pending' for a live-updating story.
   */
  streamingNarrative: string | null
  /** Open the adventure: take the first turn with no choice (fetches the opening scene). */
  onStart: () => Promise<void>
  /** Take a turn by choosing a numbered option. */
  onChoose: (choiceId: string) => Promise<void>
  /** Take a turn with free-text input. */
  onFreeText: (text: string) => Promise<void>
  /** Take over the session lease (resolves 409 conflict). */
  onTakeover: () => Promise<void>
  /** Reload game state from the API. */
  onReload: () => Promise<void>
  /** Save a checkpoint. */
  onSave: () => Promise<void>
}

export function useGame(): GameState {
  const [loadState, setLoadState] = useState<GameLoadState>('idle')
  const [actionState, setActionState] = useState<ActionState>('idle')
  const [campaign, setCampaign] = useState<CampaignState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionConflict, setSessionConflict] = useState(false)
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null)
  const [streamingNarrative, setStreamingNarrative] = useState<string | null>(null)
  const sessionTokenRef = useRef<string | null>(null)
  const leaseExpiresAtRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  /** True when the session lease has an expiry in the past (FR-056). */
  function isLeaseExpired(): boolean {
    const expiresAt = leaseExpiresAtRef.current
    if (!expiresAt) return false
    const parsed = Date.parse(expiresAt)
    return !Number.isNaN(parsed) && parsed <= Date.now()
  }

  // ── Load game ─────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    // Cancel any in-flight load from a previous mount (React 18 StrictMode
    // double-mount pattern); create a fresh controller for this invocation.
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setLoadState('loading')
    setError(null)
    try {
      if (sessionLeaseEnabled()) {
        try {
          const lease = await acquireSession()
          if (ctrl.signal.aborted) return
          sessionTokenRef.current = lease.session_token
          leaseExpiresAtRef.current = lease.expires_at
          setSessionConflict(false)
        } catch (err) {
          if (ctrl.signal.aborted) return
          if (err instanceof ApiError && err.code === 'not_session_holder') {
            setSessionConflict(true)
          } else {
            throw err
          }
        }
      }
      const state = await getGame()
      if (ctrl.signal.aborted) return
      setCampaign(state)
      setLoadState('ready')
    } catch (err) {
      if (ctrl.signal.aborted) return
      if (isAuthError(err)) {
        redirectToAuth()
        return
      }
      setError(sanitizeError(err, 'Failed to load game'))
      setLoadState('error')
    }
  }, [])

  useEffect(() => {
    void load()

    return () => {
      // Signal the in-flight load to discard its results (finding #8).
      abortRef.current?.abort()
      if (sessionLeaseEnabled()) {
        void releaseSession().catch(() => {
          // Best-effort release — ignore errors on unmount.
        })
      }
    }
  }, [load])

  // ── Action helpers ────────────────────────────────────────────────────────

  function applyTurnResponse(res: TurnResponse): void {
    setCampaign(prev => {
      if (!prev) return prev
      return {
        ...prev,
        status: res.status,
        current_scene: res.scene,
        ...(res.character !== undefined && { character: res.character }),
        ...(res.world !== undefined && { world: res.world }),
      }
    })
  }

  // ── Take a turn (shared by onStart / onChoose / onFreeText) ──────────────

  /**
   * Runs one turn, preferring the streaming endpoint (issue #20) so the
   * narrative appears as it's generated instead of after a single 10-30s
   * wait. `streamingNarrative` accumulates deltas for components to render
   * live; it's cleared once the turn settles (success or error).
   *
   * Fallback: only a genuinely *unclassified* failure (network hiccup mid-
   * stream, a malformed/short-cut stream) retries via the plain takeTurn().
   * A classified ApiError (auth, session conflict, no_active_campaign,
   * run_ended, invalid_scene, ...) means the plain endpoint would fail
   * identically for the same request — surfacing it directly avoids a
   * pointless extra round trip and duplicate narrator call.
   */
  const runTurn = useCallback(
    async (turnReq: TurnRequest, failureMessage: string): Promise<void> => {
      if (isLeaseExpired()) { redirectToAuth(); return }
      setActionState('pending')
      setError(null)
      setStreamingNarrative(null)
      try {
        let res: TurnResponse
        try {
          res = await takeTurnStream(turnReq, (delta) => {
            setStreamingNarrative((prev) => (prev ?? '') + delta)
          })
        } catch (streamErr) {
          if (streamErr instanceof ApiError && streamErr.code !== 'unknown') {
            throw streamErr
          }
          setStreamingNarrative(null)
          res = await takeTurn(turnReq)
        }
        applyTurnResponse(res)
        setActionState('idle')
      } catch (err) {
        if (isAuthError(err)) { redirectToAuth(); return }
        if (err instanceof ApiError && err.code === 'not_session_holder') {
          setSessionConflict(true)
        }
        setError(sanitizeError(err, failureMessage))
        setActionState('error')
      } finally {
        setStreamingNarrative(null)
      }
    },
    []
  )

  // No choice — the backend narrates the opening scene for a fresh turn.
  const onStart = useCallback(
    (): Promise<void> => runTurn({}, 'Failed to open the adventure'),
    [runTurn]
  )

  const onChoose = useCallback(
    (choiceId: string): Promise<void> => runTurn({ choice: choiceId }, 'Failed to take turn'),
    [runTurn]
  )

  // Free text is also sent as `choice` — backend accepts both IDs and prose.
  const onFreeText = useCallback(
    (text: string): Promise<void> => runTurn({ choice: text }, 'Failed to take turn'),
    [runTurn]
  )

  // ── Session takeover ──────────────────────────────────────────────────────

  const onTakeover = useCallback(async (): Promise<void> => {
    setActionState('pending')
    setError(null)
    try {
      const lease = await takeoverSession()
      sessionTokenRef.current = lease.session_token
      leaseExpiresAtRef.current = lease.expires_at
      setSessionConflict(false)
      const state = await getGame()
      setCampaign(state)
      setActionState('idle')
    } catch (err) {
      if (isAuthError(err)) { redirectToAuth(); return }
      setError(sanitizeError(err, 'Failed to take over session'))
      setActionState('error')
    }
  }, [])

  // ── Reload ────────────────────────────────────────────────────────────────

  const onReload = useCallback(async (): Promise<void> => {
    await load()
  }, [load])

  // ── Save ──────────────────────────────────────────────────────────────────

  const onSave = useCallback(async (): Promise<void> => {
    try {
      await saveGame()
      setLastSavedAt(new Date().toISOString())
    } catch (err) {
      if (isAuthError(err)) { redirectToAuth(); return }
      if (err instanceof ApiError && err.code === 'not_session_holder') {
        setSessionConflict(true)
        return
      }
      setError(sanitizeError(err, 'Failed to save'))
    }
  }, [])

  return {
    loadState,
    actionState,
    campaign,
    error,
    sessionConflict,
    lastSavedAt,
    streamingNarrative,
    onStart,
    onChoose,
    onFreeText,
    onTakeover,
    onReload,
    onSave,
  }
}
