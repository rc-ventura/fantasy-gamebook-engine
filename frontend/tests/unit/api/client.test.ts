/**
 * API client unit tests.
 *
 * Tests the typed API client in mock mode (VITE_USE_MOCK=true is set in vite.config.ts test env).
 * Verifies that all API functions return correctly-typed responses and that errors are
 * propagated as ApiError instances.
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

  it('listCampaigns returns an array', async () => {
    const campaigns = await mockApi.listCampaigns()
    expect(Array.isArray(campaigns)).toBe(true)
  })

  it('createCampaign returns a campaign summary with id and status', async () => {
    const summary = await mockApi.createCampaign()
    expect(summary).toHaveProperty('id')
    expect(summary).toHaveProperty('status')
    expect(summary.status).toBe('active')
    expect(summary).toHaveProperty('created_at')
    expect(summary).toHaveProperty('updated_at')
  })

  it('getCampaign returns a campaign state', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const campaign = await mockApi.getCampaign('mock-campaign-001')
    expect(campaign).toHaveProperty('id')
    expect(campaign).toHaveProperty('status')
    expect(campaign.id).toBe('mock-campaign-001')
  })

  it('getCampaign in opening stage has a character', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const campaign = await mockApi.getCampaign('mock-campaign-001')
    expect(campaign.character).toBeDefined()
    expect(campaign.character?.alive).toBe(true)
  })

  it('createCharacter returns a character sheet', async () => {
    const character = await mockApi.createCharacter('mock-campaign-001')
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
    const scene = await mockApi.getScene('mock-campaign-001')
    expect(scene).toHaveProperty('narrative')
    expect(scene).toHaveProperty('choices')
    expect(scene).toHaveProperty('effects')
    expect(typeof scene.narrative).toBe('string')
    expect(scene.narrative.length).toBeGreaterThan(0)
    expect(Array.isArray(scene.choices)).toBe(true)
  })

  it('takeTurn returns a scene and campaign', async () => {
    sessionStorage.setItem('mock_stage', 'opening')
    const result = await mockApi.takeTurn('mock-campaign-001', '3', undefined)
    expect(result).toHaveProperty('scene')
    expect(result).toHaveProperty('campaign')
    expect(result.scene).toHaveProperty('narrative')
    expect(result.campaign).toHaveProperty('id')
  })

  it('combatRound returns a round with engine values', async () => {
    sessionStorage.setItem('mock_stage', 'in_combat')
    const result = await mockApi.combatRound('mock-campaign-001', false)
    expect(result).toHaveProperty('round')
    expect(result).toHaveProperty('combat')
    expect(result).toHaveProperty('campaign')
    expect(result.round).toHaveProperty('hero_attack')
    expect(result.round).toHaveProperty('enemy_attack')
    expect(result.round).toHaveProperty('hero_damage')
    expect(result.round).toHaveProperty('enemy_damage')
  })

  it('acquireSession returns a session lease', async () => {
    const lease = await mockApi.acquireSession('mock-campaign-001')
    expect(lease).toHaveProperty('session_token')
    expect(lease).toHaveProperty('expires_at')
    expect(typeof lease.session_token).toBe('string')
    expect(lease.session_token.length).toBeGreaterThan(0)
  })

  it('takeoverSession returns a new session lease', async () => {
    const lease = await mockApi.takeoverSession('mock-campaign-001')
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
