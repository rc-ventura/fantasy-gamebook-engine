/**
 * E2E: Full play loop in the browser (SC-004).
 *
 * Exercises: opening → make a choice → reach a new scene → combat → end-state.
 * Runs against mock mode (VITE_USE_MOCK=true) so no live backend is required.
 *
 * NOTE: These tests require the Vite dev server to be running on port 5173.
 * Run: npm run test:e2e
 *
 * Live backend integration (slice 003): when 003 is live, point
 * PLAYWRIGHT_BASE_URL at the running server and remove VITE_USE_MOCK.
 */

import { test, expect } from '@playwright/test'

test.describe('Play loop (mock mode)', () => {
  test.beforeEach(async ({ page }) => {
    // Start fresh each test
    await page.goto('/')
  })

  test('landing page renders the Grimoire hero', async ({ page }) => {
    await expect(page.getByText('The Grimoire of Claude Code')).toBeVisible()
    await expect(page.getByRole('button', { name: /begin your adventure/i })).toBeVisible()
  })

  test('landing CTA navigates to auth in mock mode', async ({ page }) => {
    await page.click('text=Begin Your Adventure')
    // In mock mode, always authenticated, so goes to dashboard
    await expect(page).toHaveURL(/\/(auth|dashboard)/)
  })

  test('dashboard shows campaigns after auth', async ({ page }) => {
    // Go directly to dashboard (mock mode = always authed)
    await page.goto('/dashboard')
    await expect(page.getByText('My Adventures')).toBeVisible()
  })

  test('can create a new adventure from dashboard', async ({ page }) => {
    await page.goto('/dashboard')
    await page.click('text=+ New Adventure')
    // Should navigate to play page
    await expect(page).toHaveURL(/\/play\//)
  })

  test('play page shows character creation when no character', async ({ page }) => {
    // Clear mock state to get no_character
    await page.goto('/dashboard')
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'no_character'))
    await page.goto('/play/mock-campaign-001')
    await expect(page.getByText('Create Your Hero')).toBeVisible()
    await expect(page.getByRole('button', { name: /roll & begin/i })).toBeVisible()
  })

  test('character creation rolls attributes from engine', async ({ page }) => {
    await page.goto('/play/mock-campaign-001')
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'no_character'))
    await page.reload()

    // Click Roll & Begin — engine rolls attributes
    await page.click('text=Roll & Begin')
    // Should show the character sheet with engine-rolled stats
    await expect(page.getByLabelText(/skill:/i)).toBeVisible({ timeout: 10000 })
  })

  test('narrator shows opening scene prose', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'opening'))
    await page.goto('/play/mock-campaign-001')
    await expect(page.getByLabel('Narrator')).toBeVisible({ timeout: 10000 })
  })

  test('choices panel shows numbered options from engine', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'opening'))
    await page.goto('/play/mock-campaign-001')
    // Engine produces 3 choices for the opening
    await expect(page.getByLabel('Your choices')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/take the left path/i)).toBeVisible()
  })

  test('making a choice advances the scene', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'opening'))
    await page.goto('/play/mock-campaign-001')
    await page.waitForSelector('[aria-label="Your choices"]')
    // Click choice 3 (Speak to the wounded traveller)
    await page.click('text=Speak to the wounded traveller')
    // Should show the exploring scene
    await expect(page.getByLabel('Narrator')).toContainText('Corvin', { timeout: 10000 })
  })

  test('character sheet shows engine-produced stats in sidebar', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'opening'))
    await page.goto('/play/mock-campaign-001')
    // Character sheet in sidebar
    await expect(page.getByLabel('Character sheet')).toBeVisible({ timeout: 10000 })
    // Skill stat from engine (10/10 in mock fixture)
    await expect(page.getByLabel(/skill: 10 of 10/i)).toBeVisible()
  })

  test('combat panel appears when in combat', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'in_combat'))
    await page.goto('/play/mock-campaign-001')
    await expect(page.getByLabel('Combat')).toBeVisible({ timeout: 10000 })
    await expect(page.getByLabel('Resolve combat round')).toBeVisible()
  })

  test('resolving a combat round shows engine-computed results', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'in_combat'))
    await page.goto('/play/mock-campaign-001')
    await page.waitForSelector('[aria-label="Combat"]')
    await page.click('[aria-label="Resolve combat round"]')
    // After round, should show engine-produced attack strengths
    await expect(page.getByLabel(/hero attack strength/i)).toBeVisible({ timeout: 10000 })
  })

  test('ended campaign shows conclusion and return button', async ({ page }) => {
    await page.evaluate(() => sessionStorage.setItem('mock_stage', 'ended'))
    await page.goto('/play/mock-campaign-001')
    await expect(page.getByLabelText('Adventure ended')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: /return to dashboard/i })).toBeVisible()
  })
})
