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
import type { CampaignState, TurnResponse } from '../types'
import { ApiError } from '../types'
import {
  getGame,
  takeTurn,
  acquireSession,
  takeoverSession,
  releaseSession,
  saveGame,
} from '../api'
import { redirectToAuth } from '../utils/navigation'

/** Session-lease flag (FR-007): default OFF until slice 004 ships real leases.
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

  // ── Open the adventure (first turn, no choice) ────────────────────────────

  const onStart = useCallback(async (): Promise<void> => {
    if (isLeaseExpired()) { redirectToAuth(); return }
    setActionState('pending')
    setError(null)
    try {
      // No choice — the backend narrates the opening scene for a fresh turn.
      const res = await takeTurn({})
      applyTurnResponse(res)
      setActionState('idle')
    } catch (err) {
      if (isAuthError(err)) { redirectToAuth(); return }
      if (err instanceof ApiError && err.code === 'not_session_holder') {
        setSessionConflict(true)
      }
      setError(sanitizeError(err, 'Failed to open the adventure'))
      setActionState('error')
    }
  }, [])

  // ── Take turn ─────────────────────────────────────────────────────────────

  const onChoose = useCallback(
    async (choiceId: string): Promise<void> => {
      if (isLeaseExpired()) { redirectToAuth(); return }
      setActionState('pending')
      setError(null)
      try {
        const res = await takeTurn({ choice: choiceId })
        applyTurnResponse(res)
        setActionState('idle')
      } catch (err) {
        if (isAuthError(err)) { redirectToAuth(); return }
        if (err instanceof ApiError && err.code === 'not_session_holder') {
          setSessionConflict(true)
        }
        setError(sanitizeError(err, 'Failed to take turn'))
        setActionState('error')
      }
    },
    []
  )

  const onFreeText = useCallback(
    async (text: string): Promise<void> => {
      if (isLeaseExpired()) { redirectToAuth(); return }
      setActionState('pending')
      setError(null)
      try {
        // Free text is also sent as `choice` — backend accepts both IDs and prose
        const res = await takeTurn({ choice: text })
        applyTurnResponse(res)
        setActionState('idle')
      } catch (err) {
        if (isAuthError(err)) { redirectToAuth(); return }
        if (err instanceof ApiError && err.code === 'not_session_holder') {
          setSessionConflict(true)
        }
        setError(sanitizeError(err, 'Failed to take turn'))
        setActionState('error')
      }
    },
    []
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
    onStart,
    onChoose,
    onFreeText,
    onTakeover,
    onReload,
    onSave,
  }
}
