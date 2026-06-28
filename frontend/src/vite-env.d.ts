/// <reference types="vite/client" />

/**
 * Vite environment variable types.
 * All VITE_* vars are available at build time via import.meta.env.
 */
interface ImportMetaEnv {
  /** Base URL for the API (defaults to /api, proxied to localhost:8000). */
  readonly VITE_API_BASE_URL?: string
  /** Dev auth stub token (slice 003). Replaced by real OIDC in slice 004. */
  readonly VITE_DEV_TOKEN?: string
  /** When 'true', all API calls use the deterministic mock handlers. */
  readonly VITE_USE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
