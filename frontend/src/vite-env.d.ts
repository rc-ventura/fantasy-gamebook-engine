/// <reference types="vite/client" />

/**
 * Vite environment variable types.
 * All VITE_* vars are available at build time via import.meta.env.
 */
interface ImportMetaEnv {
  /** Base URL for the API (defaults to /api, proxied to localhost:8000). */
  readonly VITE_API_BASE_URL?: string
  /** Dev auth stub token (slice 003) — dev-only fallback, gated behind import.meta.env.DEV. */
  readonly VITE_DEV_TOKEN?: string
  /** When 'true', all API calls use the deterministic mock handlers. */
  readonly VITE_USE_MOCK?: string
  /** When 'true', the SPA acquires/releases the play-session lease. Default off. */
  readonly VITE_SESSION_LEASE?: string
  /**
   * Browser-reachable base URL of the OIDC provider (slice 008) — where the SPA
   * sends the user and calls /auth, /token, /keys. Defaults to the local Dex
   * instance's host-published address.
   */
  readonly VITE_OIDC_AUTHORITY?: string
  /** OIDC client_id registered with the provider (slice 008). Defaults to 'gamebook'. */
  readonly VITE_OIDC_CLIENT_ID?: string
  /**
   * The `iss` claim value actually baked into issued tokens (slice 008). Only
   * needed when this differs from VITE_OIDC_AUTHORITY, as it does for local Dex:
   * Dex's configured issuer is a container-network hostname (`dex:5556`, matching
   * OIDC_ISSUER on the backend) that the browser cannot resolve, so the browser
   * must reach Dex at a different, host-published URL than the one baked into its
   * tokens. Defaults to the local Dex container-network issuer when
   * VITE_OIDC_AUTHORITY is unset; otherwise defaults to VITE_OIDC_AUTHORITY itself
   * (the normal case for any real provider, where issuer == authority).
   */
  readonly VITE_OIDC_ISSUER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
