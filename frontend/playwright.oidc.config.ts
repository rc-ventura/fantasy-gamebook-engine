import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E configuration for the real OIDC login flow (slice 008).
 *
 * Unlike playwright.config.ts, this does NOT start a mock-mode dev server —
 * spec 008's own acceptance criteria (SC-005) require driving the flow against
 * a real Dex + real backend, with zero mocks. Start the stack yourself first:
 *
 *   docker compose --profile gameobs up -d --build
 *   npm run test:e2e:oidc
 *
 * Or against a native dev server + Dex + backend: set PLAYWRIGHT_BASE_URL.
 */
export default defineConfig({
  testDir: './tests/e2e-oidc',
  fullyParallel: true,
  forbidOnly: !!process.env['CI'],
  retries: process.env['CI'] ? 2 : 0,
  workers: process.env['CI'] ? 1 : undefined,
  reporter: 'list',

  use: {
    baseURL: process.env['PLAYWRIGHT_BASE_URL'] ?? 'http://localhost:8080',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
