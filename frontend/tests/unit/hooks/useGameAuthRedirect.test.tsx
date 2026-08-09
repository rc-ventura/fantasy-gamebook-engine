/**
 * useGame auth-redirect tests (T110, SC-035/SC-036).
 *
 * 401/403 API errors and an expired session lease must both hard-redirect
 * the player to /auth instead of leaving the play screen in a broken state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { ApiError } from '../../../src/types'
import type { CampaignState } from '../../../src/types'

vi.mock('../../../src/api', () => ({
  getGame: vi.fn(),
  takeTurn: vi.fn(),
  acquireSession: vi.fn(),
  takeoverSession: vi.fn(),
  releaseSession: vi.fn().mockResolvedValue(undefined),
  saveGame: vi.fn(),
}))

vi.mock('../../../src/utils/navigation', () => ({
  redirectToAuth: vi.fn(),
}))

import { getGame, takeTurn, acquireSession } from '../../../src/api'
import { redirectToAuth } from '../../../src/utils/navigation'
import { useGame } from '../../../src/hooks/useGame'

const READY_STATE: CampaignState = { status: 'active' }

describe('useGame auth redirects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllEnvs()
  })

  it('redirects to /auth when the initial load gets a 401', async () => {
    vi.stubEnv('VITE_SESSION_LEASE', 'false')
    vi.mocked(getGame).mockRejectedValue(new ApiError(401, 'unauthenticated', 'nope'))

    renderHook(() => useGame())

    await waitFor(() => {
      expect(redirectToAuth).toHaveBeenCalled()
    })
  })

  it('redirects to /auth when a turn gets a 403', async () => {
    vi.stubEnv('VITE_SESSION_LEASE', 'false')
    vi.mocked(getGame).mockResolvedValue(READY_STATE)
    vi.mocked(takeTurn).mockRejectedValue(new ApiError(403, 'forbidden', 'nope'))

    const { result } = renderHook(() => useGame())
    await waitFor(() => {
      expect(result.current.loadState).toBe('ready')
    })

    await act(async () => {
      await result.current.onChoose('1')
    })
    expect(redirectToAuth).toHaveBeenCalled()
  })

  it('redirects to /auth when the session lease is expired', async () => {
    vi.stubEnv('VITE_SESSION_LEASE', 'true')
    vi.mocked(acquireSession).mockResolvedValue({
      session_token: 'lease-token',
      expires_at: new Date(Date.now() - 60_000).toISOString(), // already expired
    })
    vi.mocked(getGame).mockResolvedValue(READY_STATE)

    const { result } = renderHook(() => useGame())
    await waitFor(() => {
      expect(result.current.loadState).toBe('ready')
    })

    await act(async () => {
      await result.current.onChoose('1')
    })
    expect(redirectToAuth).toHaveBeenCalled()
    expect(takeTurn).not.toHaveBeenCalled()
  })

  it('does not redirect while the lease is still valid', async () => {
    vi.stubEnv('VITE_SESSION_LEASE', 'true')
    vi.mocked(acquireSession).mockResolvedValue({
      session_token: 'lease-token',
      expires_at: new Date(Date.now() + 30 * 60_000).toISOString(),
    })
    vi.mocked(getGame).mockResolvedValue(READY_STATE)
    vi.mocked(takeTurn).mockResolvedValue({
      scene: { narrative: 'You proceed.', choices: [] },
      status: 'active',
    })

    const { result } = renderHook(() => useGame())
    await waitFor(() => {
      expect(result.current.loadState).toBe('ready')
    })

    await act(async () => {
      await result.current.onChoose('1')
    })
    expect(redirectToAuth).not.toHaveBeenCalled()
    expect(takeTurn).toHaveBeenCalledWith({ choice: '1' })
  })

  it('skips lease acquisition entirely when VITE_SESSION_LEASE is off', async () => {
    vi.stubEnv('VITE_SESSION_LEASE', 'false')
    vi.mocked(getGame).mockResolvedValue(READY_STATE)

    const { result } = renderHook(() => useGame())
    await waitFor(() => {
      expect(result.current.loadState).toBe('ready')
    })
    expect(acquireSession).not.toHaveBeenCalled()
  })

  it('onStart takes the opening turn with no choice', async () => {
    vi.stubEnv('VITE_SESSION_LEASE', 'false')
    vi.mocked(getGame).mockResolvedValue(READY_STATE)
    vi.mocked(takeTurn).mockResolvedValue({
      scene: { narrative: 'You stand at the mountain base.', choices: [{ id: '1', label: 'Climb' }] },
      status: 'active',
    })

    const { result } = renderHook(() => useGame())
    await waitFor(() => {
      expect(result.current.loadState).toBe('ready')
    })

    await act(async () => {
      await result.current.onStart()
    })
    // Opening turn sends an empty body — no choice.
    expect(takeTurn).toHaveBeenCalledWith({})
    expect(result.current.campaign?.current_scene?.narrative).toContain('mountain base')
  })
})
