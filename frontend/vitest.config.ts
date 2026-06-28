import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

/**
 * Vitest configuration — separate from vite.config.ts to avoid
 * the 'test' key being rejected by the Vite UserConfigExport type.
 */
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },

  test: {
    // Use jsdom for DOM APIs (React component tests)
    environment: 'jsdom',
    // Make vitest globals (describe, it, expect, vi) available without explicit imports
    globals: true,
    // Run setup file before each test suite
    setupFiles: ['./src/test-setup.ts'],
    // Include unit tests under tests/unit/ and src/
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}', 'src/**/*.{test,spec}.{ts,tsx}'],
    // Exclude e2e tests (run via playwright separately)
    exclude: ['tests/e2e/**', 'node_modules/**', 'dist/**'],
  },
})
