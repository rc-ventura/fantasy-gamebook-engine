import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// Must match auth/oidcConfig.ts's own default — both need the same fallback
// since one configures the runtime OIDC client and the other configures the
// static CSP meta tag that must allow reaching it.
const DEFAULT_OIDC_AUTHORITY = 'http://localhost:5556/dex'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const oidcOrigin = new URL(env.VITE_OIDC_AUTHORITY || DEFAULT_OIDC_AUTHORITY).origin

  return {
    plugins: [
      react(),
      {
        name: 'inject-oidc-csp-connect-src',
        transformIndexHtml(html: string) {
          // index.html's CSP connect-src is 'self' only (T098, FR-052) — the
          // OIDC token-endpoint fetch (slice 008) needs the provider's origin
          // added, resolved from the same VITE_OIDC_AUTHORITY value the JS
          // runtime config uses, so there's one source of truth per deploy.
          return html.replace("connect-src 'self'", `connect-src 'self' ${oidcOrigin}`)
        },
      },
    ],

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
    // import.meta.env.VITE_DEV_TOKEN. No `define` wiring needed — a manual define
    // would be replaced at config-eval time and bypass .env.local.

    build: {
      outDir: 'dist',
      // Disable source maps in production to avoid leaking internals (T097, FR-051).
      // In dev mode Vite serves them in-memory — no file written.
      sourcemap: false,
    },
  }
})
