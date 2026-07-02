/**
 * API client unit tests.
 *
 * Tests the typed API client in mock mode (VITE_USE_MOCK=true is set in vite.config.ts test env).
 * Verifies that all API functions return correctly-typed responses and that errors are
 * propagated as ApiError instances.
 *
 * Updated for spec 006 D1 (backend-scoped routes /me/game/...):
 *   - no listCampaigns, createCampaign, getCampaign(id), combatRound
 *   - createGame(), getGame(), takeTurn(choice), acquireSession(), takeoverSession() (no id params)
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { ApiError } from '../../../src/types'

// We test the mock API directly since VITE_USE_MOCK is not injected at test time
// (it's a build-time env var). The mock tests prove the contract shape.
import { mockApi } from '../../../src/api/mock'

beforeEach(() => {
  sessionStorage.clear()
})

describe('Mock API contract', () => {
  it('getAccount returns an account with id and optional email', async () => {
    const account = await mockApi.getAccount()
    expect(account).toHaveProperty('id')
    expect(typeof account.id).toBe('string')
    expect(account.id.length).toBeGreaterThan(0)
  })

  it('createGame returns campaign_id and active status', async () => {
    const result = await mockApi.createGame()
    expect(result).toHaveProperty('campaign_id')
    expect(result).toHaveProperty('status')
    expect(result.status).toBe('active')
    expect(typeof result.campaign_id).toBe('string')
    expect(result.campaign_id.length).toBeGreaterThan(0)
  })

  it('getGame returns campaign state', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const state = await mockApi.getGame()
    expect(state).toHaveProperty('status')
    expect(state.status).toBe('active')
  })

  it('getGame in opening stage has a character', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const state = await mockApi.getGame()
    expect(state.character).toBeDefined()
    expect(state.character?.alive).toBe(true)
  })

  it('getGame throws no_active_campaign when stage is ended', async () => {
    sessionStorage.setItem('mock_stage', 'ended')
    await expect(mockApi.getGame()).rejects.toMatchObject({ code: 'no_active_campaign' })
  })

  it('createCharacter returns a character sheet', async () => {
    const character = await mockApi.createCharacter('Aldric')
    expect(character).toHaveProperty('skill')
    expect(character).toHaveProperty('stamina')
    expect(character).toHaveProperty('luck')
    expect(character).toHaveProperty('gold')
    expect(character).toHaveProperty('provisions')
    expect(character).toHaveProperty('inventory')
    expect(character).toHaveProperty('alive')
    expect(character.alive).toBe(true)
  })

  it('getScene returns a scene with narrative and choices', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const scene = await mockApi.getScene()
    expect(scene).toHaveProperty('narrative')
    expect(scene).toHaveProperty('choices')
    expect(typeof scene?.narrative).toBe('string')
    expect(scene?.narrative.length).toBeGreaterThan(0)
    expect(Array.isArray(scene?.choices)).toBe(true)
  })

  it('takeTurn returns a TurnResponse with scene and status', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const result = await mockApi.takeTurn('3')
    expect(result).toHaveProperty('scene')
    expect(result).toHaveProperty('status')
    expect(result.scene).toHaveProperty('narrative')
    expect(result.scene).toHaveProperty('choices')
    expect(typeof result.scene.narrative).toBe('string')
  })

  it('acquireSession returns a session lease', async () => {
    const lease = await mockApi.acquireSession()
    expect(lease).toHaveProperty('session_token')
    expect(lease).toHaveProperty('expires_at')
    expect(typeof lease.session_token).toBe('string')
    expect(lease.session_token.length).toBeGreaterThan(0)
  })

  it('takeoverSession returns a new session lease', async () => {
    const lease = await mockApi.takeoverSession()
    expect(lease).toHaveProperty('session_token')
    expect(lease.session_token).toContain('takeover')
  })
})

describe('ApiError class', () => {
  it('is an instance of Error', () => {
    const err = new ApiError(404, 'not_found', 'Campaign not found')
    expect(err instanceof Error).toBe(true)
    expect(err instanceof ApiError).toBe(true)
  })

  it('has the correct code and status', () => {
    const err = new ApiError(409, 'not_session_holder', 'Session conflict')
    expect(err.code).toBe('not_session_holder')
    expect(err.status).toBe(409)
    expect(err.message).toBe('Session conflict')
  })

  it('has the correct name', () => {
    const err = new ApiError(401, 'unauthenticated', 'Unauthorized')
    expect(err.name).toBe('ApiError')
  })
})
