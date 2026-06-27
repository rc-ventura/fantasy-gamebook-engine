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

  define: {
    // Dev auth stub token — consumed by the API client.
    // Override in .env.local: VITE_DEV_TOKEN=<your-token>
    // When slice 004 delivers real OIDC, only .env.local changes; no component changes.
    'import.meta.env.VITE_DEV_TOKEN': JSON.stringify(
      process.env['VITE_DEV_TOKEN'] ?? 'dev-stub-token',
    ),
  },

  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
