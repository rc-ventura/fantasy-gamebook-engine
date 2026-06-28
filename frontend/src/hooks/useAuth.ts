/**
 * useAuth — auth state hook.
 *
 * Auth seam: the dev auth stub stores a token in sessionStorage.
 * When slice 004 ships real OIDC, only this hook changes — zero play-loop
 * component changes. The seam is the setTokenProvider() call in the API client.
 *
 * Dev auth stub: the token is set in sessionStorage under 'auth_token'.
 * In VITE_USE_MOCK mode the token is always considered present (no real auth needed).
 */

import { useState, useCallback, useEffect } from 'react'
import { setAuthToken, clearAuthToken, isAuthenticated } from '../api'

interface AuthState {
  /** True when the user has a valid auth token. */
  authenticated: boolean
  /** Sign in with a dev token (dev auth stub — replaced by OIDC in slice 004). */
  signIn: (token: string) => void
  /** Sign out and clear the stored token. */
  signOut: () => void
}

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export function useAuth(): AuthState {
  // In mock mode, always authenticated; in real mode, check for a stored token.
  const [authenticated, setAuthenticated] = useState<boolean>(
    USE_MOCK ? true : isAuthenticated()
  )

  useEffect(() => {
    // Sync auth state with sessionStorage on mount (handles tab restoration).
    if (!USE_MOCK) {
      setAuthenticated(isAuthenticated())
    }
  }, [])

  const signIn = useCallback((token: string) => {
    setAuthToken(token)
    setAuthenticated(true)
  }, [])

  const signOut = useCallback(() => {
    clearAuthToken()
    setAuthenticated(false)
  }, [])

  return { authenticated, signIn, signOut }
}
