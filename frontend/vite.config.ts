import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },

  server: {
    port: 5173,
    proxy: {
      // Proxy /api/* → FastAPI backend on localhost:8000
      // The /api prefix is stripped so backend sees /campaigns/..., /me, etc.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },

  // Dev auth stub token (VITE_DEV_TOKEN) is exposed to client code via Vite's
  // built-in env handling: set it in .env.local (gitignored) and read it through
  // import.meta.env.VITE_DEV_TOKEN. When slice 004 delivers real OIDC, only
  // .env.local changes; no component changes. No `define` wiring needed — a
  // manual define would be replaced at config-eval time and bypass .env.local.

  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
