/**
 * E2E: real OIDC login flow (slice 008, spec 008 User Story 1 + edge cases).
 *
 * Runs against a real Dex + real backend — no mocks (SC-005). Requires the
 * `gameobs` compose stack (or Dex + backend + `npm run dev`) already running:
 *
 *   docker compose --profile gameobs up -d --build
 *   npm run test:e2e:oidc
 *
 * Credentials are Dex's static test fixtures (docker/dex/config.yaml) — local
 * dev only, not production secrets.
 */

import { test, expect } from '@playwright/test'

const PLAYER_EMAIL = 'player1@example.com'
const PLAYER_PASSWORD = 'gamebook-test-1'

async function loginAsPlayer1(page: import('@playwright/test').Page) {
  await page.goto('/auth')
  await page.getByRole('button', { name: 'Login' }).click()
  await expect(page).toHaveURL(/localhost:5556\/dex\//)
  await page.getByRole('textbox', { name: 'email address' }).fill(PLAYER_EMAIL)
  await page.getByRole('textbox', { name: 'Password' }).fill(PLAYER_PASSWORD)
  await page.getByRole('button', { name: 'Login' }).click()
}

test.describe('Real OIDC login (User Story 1)', () => {
  test('Login redirects to the real Dex sign-in page, no in-app token entry', async ({ page }) => {
    await page.goto('/auth')
    // FR-001/FR-003: no token-entry UI in a production build.
    await expect(page.getByLabel(/dev auth token/i)).toHaveCount(0)
    await page.getByRole('button', { name: 'Login' }).click()
    await expect(page).toHaveURL(/localhost:5556\/dex\/auth/)
    await expect(page.getByRole('heading', { name: /log in to your account/i })).toBeVisible()
  })

  test('completing sign-in on Dex lands back in the app authenticated', async ({ page }) => {
    await loginAsPlayer1(page)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    // The first authenticated call (account summary) must have actually succeeded —
    // not just a client-side navigation.
    await expect(page.getByText('Welcome back', { exact: false })).toBeVisible()
  })

  test('invalid credentials are handled entirely on Dex\'s own page', async ({ page }) => {
    await page.goto('/auth')
    await page.getByRole('button', { name: 'Login' }).click()
    await page.getByRole('textbox', { name: 'email address' }).fill(PLAYER_EMAIL)
    await page.getByRole('textbox', { name: 'Password' }).fill('wrong-password')
    await page.getByRole('button', { name: 'Login' }).click()
    // Dex shows its own error and keeps the player on its page to retry —
    // never silently lands back in the app.
    await expect(page).toHaveURL(/localhost:5556\/dex\//)
  })

  test('a replayed /callback URL fails cleanly, no double sign-in (FR-008)', async ({ page }) => {
    await loginAsPlayer1(page)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    const spentCallbackUrl = await page.evaluate(() => {
      const key = Object.keys(sessionStorage).find((k) => k.startsWith('oidc.user:'))
      // The spent authorization code/state aren't recoverable after success —
      // this test instead proves a bookmarked/replayed callback URL with a
      // stale state value is rejected, which is the same failure path.
      return key ? 'has-session' : 'no-session'
    })
    expect(spentCallbackUrl).toBe('has-session')

    await page.goto('/callback?code=stale-code&state=stale-state-that-was-never-issued')
    await expect(page).toHaveURL(/\/auth/, { timeout: 10000 })
    await expect(page.getByRole('alert')).toBeVisible()
  })

  test('signing out clears the session and protects routes again', async ({ page }) => {
    await loginAsPlayer1(page)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    await page.getByRole('button', { name: 'Log out' }).click()
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/auth/)
  })

  test('no client secret appears in the token exchange request', async ({ page }) => {
    let tokenRequestBody = ''
    page.on('request', (req) => {
      if (req.url().includes('/dex/token') && req.method() === 'POST') {
        tokenRequestBody = req.postData() ?? ''
      }
    })
    await loginAsPlayer1(page)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    expect(tokenRequestBody).toContain('code_verifier')
    expect(tokenRequestBody).not.toContain('client_secret')
    expect(tokenRequestBody).not.toContain('gamebook-secret-dev')
  })
})

test.describe('Session persistence (User Story 2)', () => {
  test('a signed-in session survives a page reload', async ({ page }) => {
    await loginAsPlayer1(page)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    await page.reload()
    await expect(page).toHaveURL(/\/dashboard/)
    await expect(page.getByText('Welcome back', { exact: false })).toBeVisible()
  })

  test('a cleared session routes back to /auth, not a broken state', async ({ page }) => {
    await loginAsPlayer1(page)
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    await page.evaluate(() => sessionStorage.clear())
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/auth/)
  })
})
