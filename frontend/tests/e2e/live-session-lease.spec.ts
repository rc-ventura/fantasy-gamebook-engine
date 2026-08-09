/**
 * E2E: Session-lease exclusivity against the LIVE backend (issue #15).
 *
 * Two independent browser contexts (~two devices/tabs) sharing the same
 * dev account. The backend enforces single-active-writer via LeaseService
 * (ADR-023/031/032) — this only exercises for real with DATABASE_URL set.
 *
 * Empirically verified (see LeaseService.acquire): a same-account re-acquire
 * always succeeds and silently rotates the token, so whichever tab acts
 * LAST becomes the holder; the other becomes stale and sees 409 on its next
 * mutating request. "Take Over Session" reclaims it (client.ts's
 * takeoverSession() re-acquires — see its docstring for why the dedicated
 * /takeover endpoint can't be used from a dispossessed tab).
 *
 * Run (three terminals, or scripted):
 *   1. DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost:5433/gamebook \
 *      POSTGRES_SSL_MODE=disable GAMEBOOK_DEV_MODE=1 \
 *      uv run uvicorn gamebook_web.api.app:app --port 8000
 *   2. cd frontend && VITE_USE_MOCK=false VITE_DEV_TOKEN=dev-token VITE_SESSION_LEASE=true \
 *      npm run dev -- --port 5176
 *   3. cd frontend && LIVE_BACKEND=1 PLAYWRIGHT_BASE_URL=http://localhost:5176 \
 *      npx playwright test tests/e2e/live-session-lease.spec.ts
 */

import { test, expect, request as playwrightRequest } from '@playwright/test'

const LIVE = process.env['LIVE_BACKEND'] === '1'
const API_BASE = process.env['LIVE_API_BASE_URL'] ?? 'http://localhost:8000'
const DEV_TOKEN = 'dev-token'

test.describe('Session-lease exclusivity (live backend, issue #15)', () => {
  test.skip(
    !LIVE,
    'LIVE_BACKEND=1 not set — requires FastAPI on :8000 (DATABASE_URL set) and Vite with VITE_USE_MOCK=false'
  )

  test.beforeAll(async () => {
    // Bootstrap a campaign + character directly via the API so both tabs can
    // go straight to /play without depending on the character-creation UI.
    const api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      extraHTTPHeaders: { Authorization: `Bearer ${DEV_TOKEN}` },
    })
    await api.post('/me/game', { data: {} }).catch(() => undefined) // ok if one already exists
    await api.post('/me/game/character', { data: {} }).catch(() => undefined) // ok if one already exists
    await api.dispose()
  })

  test('second tab silently becomes the writer; the first is read-only until it takes over', async ({
    browser,
  }) => {
    const contextA = await browser.newContext()
    const contextB = await browser.newContext()
    // Prime the dev-auth-stub token client.ts/tokenBridge.ts read from
    // sessionStorage (DEV builds only) — skips the interactive login screen
    // so each context authenticates as the same dev account independently.
    await contextA.addInitScript((token) => sessionStorage.setItem('auth_token', token), DEV_TOKEN)
    await contextB.addInitScript((token) => sessionStorage.setItem('auth_token', token), DEV_TOKEN)
    const pageA = await contextA.newPage()
    const pageB = await contextB.newPage()

    try {
      // Tab A loads first — acquires the lease.
      await pageA.goto('/play')
      const saveA = pageA.getByLabel('Save checkpoint')
      await expect(saveA).toBeVisible({ timeout: 20000 })

      // Tab B loads second — same account, so acquire() succeeds and
      // silently rotates the lease token, invalidating A's.
      await pageB.goto('/play')
      const saveB = pageB.getByLabel('Save checkpoint')
      await expect(saveB).toBeVisible({ timeout: 20000 })
      await expect(pageB.getByRole('dialog', { name: 'Session conflict' })).not.toBeVisible()

      // Tab A's next mutating request (save) is rejected 409 — surfaced as
      // the SessionConflict overlay, not a silent failure.
      await saveA.click()
      const conflictA = pageA.getByRole('dialog', { name: 'Session conflict' })
      await expect(conflictA).toBeVisible({ timeout: 10000 })

      // Tab A takes over — reclaims the lease.
      await pageA.getByRole('button', { name: /take over session/i }).click()
      await expect(conflictA).not.toBeVisible({ timeout: 10000 })

      // Tab A can now act freely again.
      await saveA.click()
      await expect(pageA.getByRole('dialog', { name: 'Session conflict' })).not.toBeVisible()

      // The exclusivity flipped: Tab B is now the stale one.
      await saveB.click()
      await expect(pageB.getByRole('dialog', { name: 'Session conflict' })).toBeVisible({
        timeout: 10000,
      })
    } finally {
      await contextA.close()
      await contextB.close()
    }
  })
})
