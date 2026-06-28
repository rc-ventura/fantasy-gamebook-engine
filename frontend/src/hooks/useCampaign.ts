/**
 * useCampaign — campaign list and management hook.
 *
 * Used by the Dashboard page to list, create, and delete campaigns.
 * All data comes from the API — no client-side fabrication.
 */

import { useState, useEffect, useCallback } from 'react'
import type { CampaignSummary } from '../types'
import { listCampaigns, createCampaign, deleteCampaign } from '../api'

export type CampaignListState = 'loading' | 'ready' | 'error'

export interface CampaignHookResult {
  state: CampaignListState
  campaigns: CampaignSummary[]
  error: string | null
  /** Create a new campaign and return its ID. */
  onCreate: () => Promise<string>
  /** Delete a campaign by ID. */
  onDelete: (id: string) => Promise<void>
  /** Reload the campaign list. */
  onReload: () => Promise<void>
}

export function useCampaign(): CampaignHookResult {
  const [state, setState] = useState<CampaignListState>('loading')
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const list = await listCampaigns()
      setCampaigns(list)
      setState('ready')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load campaigns'
      setError(msg)
      setState('error')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const onCreate = useCallback(async (): Promise<string> => {
    const summary = await createCampaign()
    await load()
    return summary.id
  }, [load])

  const onDelete = useCallback(
    async (id: string): Promise<void> => {
      await deleteCampaign(id)
      await load()
    },
    [load]
  )

  const onReload = useCallback(async (): Promise<void> => {
    await load()
  }, [load])

  return { state, campaigns, error, onCreate, onDelete, onReload }
}
