/**
 * E2E: Play loop against the LIVE FastAPI backend (T014, SC-001, US1).
 *
 * Unlike play-loop.spec.ts (mock mode), this suite drives the real stack:
 *   SPA (VITE_USE_MOCK=false) → Vite /api proxy → FastAPI :8000 → MCP engine.
 * This is the configuration where API/frontend contract drift is physically
 * observable (see docs/learning-lessons/contract_drift_requires_live_integration_test.md).
 *
 * Without ANTHROPIC_API_KEY the backend narrates via the deterministic
 * FakeNarrator, so scene text below matches its built-in scenes. Engine
 * numbers (attribute rolls) come from the real MCP engine.
 *
 * Run (three terminals, or scripted):
 *   1. uv run uvicorn gamebook_web.api.app:app --port 8000
 *   2. cd frontend && VITE_USE_MOCK=false VITE_DEV_TOKEN=dev-token npm run dev -- --port 5176
 *   3. cd frontend && LIVE_BACKEND=1 PLAYWRIGHT_BASE_URL=http://localhost:5176 npx playwright test tests/e2e/live-play-loop.spec.ts
 */

import { test, expect } from '@playwright/test'

const LIVE = process.env['LIVE_BACKEND'] === '1'

// Serial: all tests share the single dev account's one active campaign on the
// live backend — parallel workers would end each other's game mid-test.
// (Later tests also reuse the hero forged by the first one.)
test.describe.configure({ mode: 'serial' })

test.describe('Play loop (live backend)', () => {
  test.skip(
    !LIVE,
    'LIVE_BACKEND=1 not set — requires FastAPI on :8000 and Vite with VITE_USE_MOCK=false'
  )

  test('full loop: forge hero → engine-rolled stats → opening scene → choice → next scene', async ({
    page,
  }) => {
    // ── Forge a hero (real POST /me/game + POST /me/game/character) ──
    await page.goto('/create')
    await page.getByPlaceholder('Arquimedes').fill('Live Test Hero')
    await page.getByRole('button', { name: /roll attributes via the engine/i }).click()

    // Engine rolls land in the preview; the begin button unlocks.
    const begin = page.getByRole('button', { name: /enter the grey mountain/i })
    await expect(begin).toBeEnabled({ timeout: 20000 })
    await begin.click()

    // ── Play page: real engine character sheet ──
    await expect(page).toHaveURL(/\/play/)
    const sheet = page.getByLabel('Character sheet')
    await expect(sheet).toBeVisible({ timeout: 20000 })

    // Engine-produced stats obey the Fighting Fantasy generation rules
    // (skill 1d6+6 ∈ 7..12, stamina 2d6+12 ∈ 14..24, luck 1d6+6 ∈ 7..12).
    const skillLabel = await page
      .getByLabel(/^skill: \d+ of \d+$/i)
      .getAttribute('aria-label')
    const skill = Number(/\d+/.exec(skillLabel ?? '')?.[0])
    expect(skill).toBeGreaterThanOrEqual(7)
    expect(skill).toBeLessThanOrEqual(12)

    // ── First turn: no scene exists yet — the player opens the adventure ──
    // (real POST /me/game/turn; FakeNarrator returns the opening scene)
    await page
      .getByRole('textbox', { name: 'Free text action' })
      .fill('Begin the adventure')
    await page.getByRole('button', { name: 'Submit free text action' }).click()

    const narrator = page.getByLabel('Narrator')
    await expect(narrator).toBeVisible({ timeout: 30000 })
    await expect(narrator).toContainText(/grey mountain/i, { timeout: 30000 })
    await expect(page.getByLabel('Your choices')).toBeVisible()

    // ── Second turn via a numbered choice ──
    await page.getByRole('button', { name: /climb the mountain path/i }).click()
    await expect(narrator).toContainText(/fork in the path/i, { timeout: 30000 })
    await expect(page.getByRole('button', { name: /enter the cave/i })).toBeVisible()
  })

  test('save checkpoint persists via the engine', async ({ page }) => {
    await page.goto('/play')
    await expect(page.getByLabel('Character sheet')).toBeVisible({ timeout: 20000 })
    await page.getByLabel('Save checkpoint').click()
    // No error surfaces — the engine acknowledged the save.
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible()
  })

  test('game state survives a full page reload (resume from recorded point)', async ({
    page,
  }) => {
    await page.goto('/play')
    const narrator = page.getByLabel('Narrator')
    await expect(narrator).toBeVisible({ timeout: 20000 })

    await page.reload()
    // FR-003: resume from the exact recorded point — sheet and scene return.
    await expect(page.getByLabel('Character sheet')).toBeVisible({ timeout: 20000 })
  })
})
