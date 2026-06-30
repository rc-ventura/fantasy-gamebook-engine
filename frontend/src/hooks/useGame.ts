/**
 * useGame — core game-state hook for the play loop.
 *
 * Loads and holds the full campaign state (character, world, scene).
 * All numeric values come from the API — this hook never fabricates any stat.
 * Combat is now resolved inside the narrator's tool-use loop (ADR-029);
 * the frontend has no separate combat endpoints.
 *
 * Handles:
 *   - Loading campaign state on mount
 *   - Taking turns (choice or free text)
 *   - Session lease acquisition and 409 conflict detection
 *   - Error and loading states
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import type { CampaignState, TurnResponse } from '../types'
import { ApiError } from '../types'
import {
  getCampaign,
  takeTurn,
  acquireSession,
  takeoverSession,
  releaseSession,
  saveCampaign,
} from '../api'

export type GameLoadState = 'idle' | 'loading' | 'ready' | 'error'
export type ActionState = 'idle' | 'pending' | 'error'

export interface GameState {
  /** Overall loading state of the campaign. */
  loadState: GameLoadState
  /** State of the last turn/combat action. */
  actionState: ActionState
  /** Full campaign state from the API — all values are engine-produced. */
  campaign: CampaignState | null
  /** Human-readable error message, if any. */
  error: string | null
  /** True when another session holds the write lease (409). */
  sessionConflict: boolean
  /** Take a turn by choosing a numbered option or typing free text. */
  onChoose: (choiceId: string) => Promise<void>
  /** Take a turn with free-text input. */
  onFreeText: (text: string) => Promise<void>
  /** Take over the session lease (resolves 409 conflict). */
  onTakeover: () => Promise<void>
  /** Reload campaign state from the API. */
  onReload: () => Promise<void>
  /** Save a checkpoint. */
  onSave: () => Promise<void>
}

export function useGame(campaignId: string): GameState {
  const [loadState, setLoadState] = useState<GameLoadState>('idle')
  const [actionState, setActionState] = useState<ActionState>('idle')
  const [campaign, setCampaign] = useState<CampaignState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionConflict, setSessionConflict] = useState(false)
  const sessionTokenRef = useRef<string | null>(null)

  // ── Load campaign ─────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    setLoadState('loading')
    setError(null)
    try {
      // Acquire session lease; if 409 not_session_holder → show conflict prompt.
      try {
        const lease = await acquireSession(campaignId)
        sessionTokenRef.current = lease.session_token
        setSessionConflict(false)
      } catch (err) {
        if (err instanceof ApiError && err.code === 'not_session_holder') {
          setSessionConflict(true)
          // Still load the state (read-only view); loadState is set to 'ready'
          // below once getCampaign resolves, so the UI never renders 'ready'
          // with a null campaign (which would flash the character-creation screen).
        } else {
          throw err
        }
      }
      const state = await getCampaign(campaignId)
      setCampaign(state)
      setLoadState('ready')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load campaign'
      setError(msg)
      setLoadState('error')
    }
  }, [campaignId])

  useEffect(() => {
    void load()

    // Release session lease on unmount.
    return () => {
      void releaseSession(campaignId).catch(() => {
        // Best-effort release — ignore errors on unmount.
      })
    }
  }, [campaignId, load])

  // ── Action helpers ────────────────────────────────────────────────────────

  function applyTurnResponse(res: TurnResponse): void {
    setCampaign(prev => {
      if (!prev) return prev
      return {
        ...prev,
        current_scene: res.scene,
        ...(res.character !== undefined && { character: res.character }),
        ...(res.world !== undefined && { world: res.world }),
      }
    })
  }

  // ── Take turn ─────────────────────────────────────────────────────────────

  const onChoose = useCallback(
    async (choiceId: string): Promise<void> => {
      setActionState('pending')
      setError(null)
      try {
        const res = await takeTurn(campaignId, { choice_id: choiceId })
        applyTurnResponse(res)
        setActionState('idle')
      } catch (err) {
        if (err instanceof ApiError && err.code === 'not_session_holder') {
          setSessionConflict(true)
        }
        const msg = err instanceof Error ? err.message : 'Failed to take turn'
        setError(msg)
        setActionState('error')
      }
    },
    [campaignId]
  )

  const onFreeText = useCallback(
    async (text: string): Promise<void> => {
      setActionState('pending')
      setError(null)
      try {
        const res = await takeTurn(campaignId, { free_text: text })
        applyTurnResponse(res)
        setActionState('idle')
      } catch (err) {
        if (err instanceof ApiError && err.code === 'not_session_holder') {
          setSessionConflict(true)
        }
        const msg = err instanceof Error ? err.message : 'Failed to take turn'
        setError(msg)
        setActionState('error')
      }
    },
    [campaignId]
  )

  // ── Session takeover ──────────────────────────────────────────────────────

  const onTakeover = useCallback(async (): Promise<void> => {
    setActionState('pending')
    setError(null)
    try {
      const lease = await takeoverSession(campaignId)
      sessionTokenRef.current = lease.session_token
      setSessionConflict(false)
      const state = await getCampaign(campaignId)
      setCampaign(state)
      setActionState('idle')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to take over session'
      setError(msg)
      setActionState('error')
    }
  }, [campaignId])

  // ── Reload ────────────────────────────────────────────────────────────────

  const onReload = useCallback(async (): Promise<void> => {
    await load()
  }, [load])

  // ── Save ──────────────────────────────────────────────────────────────────

  const onSave = useCallback(async (): Promise<void> => {
    try {
      await saveCampaign(campaignId)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to save'
      setError(msg)
    }
  }, [campaignId])

  return {
    loadState,
    actionState,
    campaign,
    error,
    sessionConflict,
    onChoose,
    onFreeText,
    onTakeover,
    onReload,
    onSave,
  }
}
