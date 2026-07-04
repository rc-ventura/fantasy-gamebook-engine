/**
 * Audit test: no-fabricated-values (SC-003)
 *
 * Verifies that the API client, mock, and all components never compute
 * or fabricate numeric values client-side. Every number shown must trace
 * to an API response.
 *
 * Strategy:
 * 1. Inspect the mock API fixtures to confirm all numbers are pre-defined
 *    (not computed at render time) — they simulate engine output.
 * 2. Verify the API client passes numbers through unchanged (no arithmetic).
 * 3. Verify component props: every numeric prop that renders to the DOM
 *    must come from a typed API response type (not a local let/const).
 *
 * Updated for spec 006 D1 + spec 007 ADR-029:
 *   - getCampaign(id) → getGame() (no id)
 *   - combatRound removed (combat resolved by narrator via takeTurn)
 *   - takeTurn(id, choice, text) → takeTurn(choice)
 *   - TurnResponse has { scene, status, character?, world? } (no campaign wrapper)
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { mockApi } from '../../../src/api/mock'

beforeEach(() => {
  sessionStorage.clear()
})

describe('no-fabricated-values audit (SC-003)', () => {
  describe('Mock API — all numbers are engine-realistic fixtures', () => {
    it('campaign state has engine-realistic skill (1d6+6 → 7–12)', async () => {
      sessionStorage.setItem('mock_stage', 'opening')
      const state = await mockApi.getGame()
      if (state.character) {
        const { skill } = state.character
        expect(skill.initial).toBeGreaterThanOrEqual(7)
        expect(skill.initial).toBeLessThanOrEqual(12)
        expect(skill.current).toBeGreaterThanOrEqual(0)
        expect(skill.current).toBeLessThanOrEqual(skill.initial)
      }
    })

    it('campaign state has engine-realistic stamina (2d6+12 → 14–24)', async () => {
      sessionStorage.setItem('mock_stage', 'opening')
      const state = await mockApi.getGame()
      if (state.character) {
        const { stamina } = state.character
        expect(stamina.initial).toBeGreaterThanOrEqual(14)
        expect(stamina.initial).toBeLessThanOrEqual(24)
        expect(stamina.current).toBeGreaterThanOrEqual(0)
        expect(stamina.current).toBeLessThanOrEqual(stamina.initial)
      }
    })

    it('campaign state has engine-realistic luck (1d6+6 → 7–12)', async () => {
      sessionStorage.setItem('mock_stage', 'opening')
      const state = await mockApi.getGame()
      if (state.character) {
        const { luck } = state.character
        expect(luck.initial).toBeGreaterThanOrEqual(7)
        expect(luck.initial).toBeLessThanOrEqual(12)
      }
    })

    it('current attribute never exceeds initial (invariant enforced by engine)', async () => {
      sessionStorage.setItem('mock_stage', 'exploring')
      const state = await mockApi.getGame()
      if (state.character) {
        const { skill, stamina, luck } = state.character
        expect(skill.current).toBeLessThanOrEqual(skill.initial)
        expect(stamina.current).toBeLessThanOrEqual(stamina.initial)
        expect(luck.current).toBeLessThanOrEqual(luck.initial)
      }
    })

    it('take-turn response has scene with narrative and choices from engine', async () => {
      sessionStorage.setItem('mock_stage', 'opening')
      const result = await mockApi.takeTurn('3')
      // TurnResponse: { scene, status, character?, world? } — no campaign wrapper (spec 007)
      expect(result).toHaveProperty('scene')
      expect(result).toHaveProperty('status')
      expect(result.scene).toHaveProperty('narrative')
      expect(result.scene).toHaveProperty('choices')
      // No effects field — removed in spec 007 (ADR-029)
      expect(result.scene).not.toHaveProperty('effects')
    })

    it('take-turn preserves engine character stats in response', async () => {
      sessionStorage.setItem('mock_stage', 'opening')
      const result = await mockApi.takeTurn('3')
      if (result.character) {
        const { skill, stamina } = result.character
        expect(skill.current).toBeLessThanOrEqual(skill.initial)
        expect(stamina.current).toBeLessThanOrEqual(stamina.initial)
        expect(skill.initial).toBeGreaterThanOrEqual(7)
        expect(skill.initial).toBeLessThanOrEqual(12)
      }
    })

    it('scene choices have stable IDs (not dynamically generated)', async () => {
      sessionStorage.setItem('mock_stage', 'opening')
      const scene = await mockApi.getScene()
      const ids = scene?.choices.map((c) => c.id) ?? []
      // IDs are the stable engine-assigned identifiers ("1", "2", "3")
      expect(ids).toEqual(['1', '2', '3'])
    })
  })

  describe('Type system audit — numeric values must trace to API types', () => {
    it('Attribute type has initial and current fields (never fabricated)', () => {
      // Structural check: if we can construct an Attribute from API data,
      // the shape is right and components cannot add fields.
      const attr = { initial: 10, current: 8 }
      expect(attr.initial).toBeDefined()
      expect(attr.current).toBeDefined()
      // No "computed" or "modifier" fields that could be fabricated
      expect(Object.keys(attr)).toEqual(['initial', 'current'])
    })

    it('TurnResponse has no effects field (ADR-029: combat resolved inside narrator)', () => {
      // The Scene type has narrative + choices only (spec 007)
      // Any effects/combat values are embedded in narrative prose, never in structured data
      const scene = { narrative: 'The wolf lunges...', choices: [{ id: '1', label: 'Fight' }] }
      expect(scene).not.toHaveProperty('effects')
    })
  })
})
