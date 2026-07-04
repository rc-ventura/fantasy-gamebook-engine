/**
 * E2E: Full play loop in the browser (SC-004; updated for spec 006 D1 routes
 * and spec 007 combat-as-prose).
 *
 * Exercises: landing → dashboard → hero creation → opening scene → choice →
 * new scene → combat resolved inside the turn (ADR-029) → victory prose.
 * Runs against mock mode (VITE_USE_MOCK=true) so no live backend is required.
 *
 * Current UI contract:
 *   - Routes are /play, /create, /graveyard — no campaign_id in URLs (D1).
 *   - There is NO combat panel: combat resolves inside the narrator's tool-use
 *     loop and arrives as narrated prose in the Scene (spec 007, ADR-029).
 *   - Mock stage machine: sessionStorage 'mock_stage' ∈
 *     no_character | opening | exploring | in_combat | ended.
 *
 * Live backend integration is a separate suite (live-play-loop.spec.ts, T014).
 */

import { test, expect } from '@playwright/test'

/** Set the mock stage; must run on the app origin, so goto('/') first. */
async function setStage(page: import('@playwright/test').Page, stage: string) {
  await page.goto('/')
  await page.evaluate((s) => sessionStorage.setItem('mock_stage', s), stage)
}

test.describe('Play loop (mock mode)', () => {
  test('landing page renders the Grimoire hero', async ({ page }) => {
    await page.goto('/')
    await expect(
      page.getByText('The Grimoire of Claude Code', { exact: true })
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: /begin your adventure/i })
    ).toBeVisible()
  })

  test('landing CTA navigates to auth or dashboard', async ({ page }) => {
    await page.goto('/')
    // CTA label depends on auth state: mock mode is always authenticated.
    // The same CTA appears in the hero and the CTA band — either works.
    await page
      .getByRole('button', { name: /return to the hall|create your account/i })
      .first()
      .click()
    await expect(page).toHaveURL(/\/(auth|dashboard)/)
  })

  test('dashboard shows the Hall of Heroes', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(
      page.getByRole('heading', { name: 'The Hall of Heroes' })
    ).toBeVisible()
  })

  test('forge a new hero navigates to hero creation', async ({ page }) => {
    await page.goto('/dashboard')
    // Button role, not text: the page subtitle also contains "forge a new hero".
    // Forge creates a fresh game (mock ~1s of simulated latency) then navigates.
    await page.getByRole('button', { name: /forge a new hero/i }).click()
    await expect(page).toHaveURL(/\/create/, { timeout: 15000 })
  })

  test('play page shows hero creation when no character exists', async ({ page }) => {
    await setStage(page, 'no_character')
    await page.goto('/play')
    await expect(page.getByText('Create Your Hero')).toBeVisible({ timeout: 10000 })
    await expect(
      page.getByRole('button', { name: /roll character attributes/i })
    ).toBeVisible()
  })

  test('character creation rolls attributes from the engine', async ({ page }) => {
    await setStage(page, 'no_character')
    await page.goto('/play')
    await page.getByRole('button', { name: /roll character attributes/i }).click()
    // Engine-rolled stats land in the sidebar character sheet.
    await expect(page.getByLabel('Character sheet')).toBeVisible({ timeout: 15000 })
  })

  test('narrator shows opening scene prose', async ({ page }) => {
    await setStage(page, 'opening')
    await page.goto('/play')
    await expect(page.getByLabel('Narrator')).toBeVisible({ timeout: 10000 })
  })

  test('choices panel shows numbered options from the scene', async ({ page }) => {
    await setStage(page, 'opening')
    await page.goto('/play')
    await expect(page.getByLabel('Your choices')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/take the left path/i)).toBeVisible()
  })

  test('making a choice advances the scene', async ({ page }) => {
    await setStage(page, 'opening')
    await page.goto('/play')
    await page.getByText('Speak to the wounded traveller').click()
    // The exploring scene introduces Corvin.
    await expect(page.getByLabel('Narrator')).toContainText('Corvin', { timeout: 15000 })
  })

  test('character sheet shows engine-produced stats in the sidebar', async ({ page }) => {
    await setStage(page, 'opening')
    await page.goto('/play')
    await expect(page.getByLabel('Character sheet')).toBeVisible({ timeout: 10000 })
    // Skill 10/10 from the mock fixture — engine values, never invented (Principle I).
    await expect(page.getByLabel(/skill: 10 of 10/i)).toBeVisible()
  })

  test('combat arrives as narrated prose inside the turn (ADR-029)', async ({ page }) => {
    await setStage(page, 'opening')
    await page.goto('/play')
    // Choice 1 (the Whispering Wood path) triggers the Dire Wolf encounter.
    await page.getByRole('button', { name: /take the left path/i }).click()
    await expect(page.getByLabel('Narrator')).toContainText('Dire Wolf', { timeout: 15000 })
    // No per-round combat UI exists — the free-text form is the only control.
    await expect(page.getByLabel('Free text input')).toBeVisible()
  })

  test('resolving combat via a turn narrates the real outcome', async ({ page }) => {
    await setStage(page, 'in_combat')
    await page.goto('/play')
    const input = page.getByRole('textbox', { name: 'Free text action' })
    await input.fill('Fight the Dire Wolf')
    await page.getByRole('button', { name: 'Submit free text action' }).click()
    // Victory prose comes back from the turn — combat resolved inside it.
    await expect(page.getByLabel('Narrator')).toContainText('The Dire Wolf falls', {
      timeout: 15000,
    })
  })

  test('graveyard lists fallen heroes', async ({ page }) => {
    await page.goto('/graveyard')
    // Route renders (content depends on mock graveyard fixtures).
    await expect(page).toHaveURL(/\/graveyard/)
  })
})
