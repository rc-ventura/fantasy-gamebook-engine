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
  authenticated: boolean
  signIn: (token: string) => void
  signOut: () => void
}

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// Module-level state so signOut/signIn propagate across all hook instances.
// In mock mode, starts as true; flips to false when the user explicitly signs out.
let _auth: boolean = USE_MOCK ? true : isAuthenticated()
const _listeners = new Set<(v: boolean) => void>()

function broadcast(value: boolean) {
  _auth = value
  _listeners.forEach((fn) => fn(value))
}

export function useAuth(): AuthState {
  const [authenticated, setAuthenticated] = useState<boolean>(_auth)

  useEffect(() => {
    _listeners.add(setAuthenticated)
    // Non-mock: sync with sessionStorage in case another tab signed out.
    if (!USE_MOCK) setAuthenticated(isAuthenticated())
    return () => { _listeners.delete(setAuthenticated) }
  }, [])

  const signIn = useCallback((token: string) => {
    setAuthToken(token)
    broadcast(true)
  }, [])

  const signOut = useCallback(() => {
    clearAuthToken()
    broadcast(false)
  }, [])

  return { authenticated, signIn, signOut }
}
