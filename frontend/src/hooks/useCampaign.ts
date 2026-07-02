/**
 * useCampaign — game management hook (dashboard operations).
 *
 * Loads the single active game + the graveyard of ended games.
 * Used by DashboardPage and GraveyardPage.
 *
 * Routes are /me/game/... — no campaign_id required (D1, spec 006, ADR-017).
 */

import { useState, useEffect, useCallback } from 'react'
import type { CampaignState, GraveyardEntry } from '../types'
import { ApiError } from '../types'
import { getGame, getGraveyard, createGame, deleteGame } from '../api'

export type CampaignListState = 'loading' | 'ready' | 'error'

export interface CampaignHookResult {
  state: CampaignListState
  /** The one active game, or null if none exists. */
  activeGame: CampaignState | null
  /** Ended campaigns (death + victory). */
  graveyard: GraveyardEntry[]
  error: string | null
  /** Create a new game (any existing active game is ended first). */
  onCreate: () => Promise<void>
  /** Abandon the current active game. */
  onDelete: () => Promise<void>
  /** Reload active game + graveyard. */
  onReload: () => Promise<void>
}

export function useCampaign(): CampaignHookResult {
  const [state, setState] = useState<CampaignListState>('loading')
  const [activeGame, setActiveGame] = useState<CampaignState | null>(null)
  const [graveyard, setGraveyard] = useState<GraveyardEntry[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const [game, grave] = await Promise.allSettled([getGame(), getGraveyard()])

      if (game.status === 'fulfilled') {
        setActiveGame(game.value)
      } else {
        const err = game.reason as unknown
        if (err instanceof ApiError && err.code === 'no_active_campaign') {
          setActiveGame(null)
        } else {
          throw err
        }
      }

      if (grave.status === 'fulfilled') {
        setGraveyard(grave.value)
      } else {
        setGraveyard([])
      }

      setState('ready')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load game data'
      setError(msg)
      setState('error')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const onCreate = useCallback(async (): Promise<void> => {
    await createGame()
    await load()
  }, [load])

  const onDelete = useCallback(async (): Promise<void> => {
    await deleteGame()
    await load()
  }, [load])

  const onReload = useCallback(async (): Promise<void> => {
    await load()
  }, [load])

  return { state, activeGame, graveyard, error, onCreate, onDelete, onReload }
}
