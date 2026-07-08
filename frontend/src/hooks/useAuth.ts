/**
 * useAuth — auth state hook (slice 008, ADR-034).
 *
 * Real sign-in is backed by react-oidc-context's useAuth() (session lives in
 * userManager, auth/oidcConfig.ts). The dev token-paste fallback (AuthPage.tsx,
 * gated to import.meta.env.DEV per FR-009) still works side-by-side via the same
 * sessionStorage('auth_token') mechanism it always used — FR-009 requires it to
 * remain available for local dev, not be replaced by real OIDC.
 *
 * Mock mode (VITE_USE_MOCK=true) is unaffected: fully offline, no OIDC provider
 * involved, same broadcast-based toggle as before this slice.
 */
import { useState, useCallback, useEffect } from 'react'
import { useAuth as useOidcAuth } from 'react-oidc-context'
import { setAuthToken, clearAuthToken } from '../api'

interface AuthState {
  authenticated: boolean
  /** True while react-oidc-context is still rehydrating a persisted session
   *  (e.g. right after a page reload) — callers MUST NOT treat `authenticated
   *  === false` as final until this is false (FR-004: a reload must not bounce
   *  a still-valid session to /auth before the stored session has a chance to
   *  load). Always false in mock mode and whenever the dev-token fallback
   *  already proves authenticated. */
  isLoading: boolean
  /** Real sign-in: call with no argument to start the OIDC redirect (FR-001).
   *  Dev-only fallback: call with a token to use the paste-a-token stub (FR-009). */
  signIn: (devToken?: string) => void
  signOut: () => void
}

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
const DEV_TOKEN_KEY = 'auth_token'

function hasDevToken(): boolean {
  return Boolean(import.meta.env.DEV) && sessionStorage.getItem(DEV_TOKEN_KEY) !== null
}

// Tracks the mock-mode toggle and the DEV-only paste-a-token fallback — real
// OIDC state comes from the library's own reactive useAuth() below.
let _devAuth: boolean = USE_MOCK ? true : hasDevToken()
const _listeners = new Set<(v: boolean) => void>()

function broadcast(value: boolean) {
  _devAuth = value
  _listeners.forEach((fn) => fn(value))
}

export function useAuth(): AuthState {
  const oidcAuth = useOidcAuth()
  const [devAuth, setDevAuth] = useState<boolean>(_devAuth)

  useEffect(() => {
    _listeners.add(setDevAuth)
    return () => {
      _listeners.delete(setDevAuth)
    }
  }, [])

  const signIn = useCallback(
    (devToken?: string) => {
      if (devToken) {
        setAuthToken(devToken)
        broadcast(true)
        return
      }
      void oidcAuth.signinRedirect()
    },
    [oidcAuth],
  )

  const signOut = useCallback(() => {
    clearAuthToken()
    broadcast(false)
    if (oidcAuth.isAuthenticated) void oidcAuth.removeUser()
  }, [oidcAuth])

  const authenticated = USE_MOCK ? devAuth : oidcAuth.isAuthenticated || devAuth
  // Dev-token auth is synchronous and mock mode is never loading — only the
  // real OIDC path has an async rehydration step to wait out.
  const isLoading = !USE_MOCK && !devAuth && oidcAuth.isLoading
  return { authenticated, isLoading, signIn, signOut }
}
