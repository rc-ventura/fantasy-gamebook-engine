/**
 * useAuth seam tests (slice 008, ADR-034).
 *
 * Mocks react-oidc-context's useAuth() to drive the wrapped hook through the
 * signed-out → pending → signed-in → loading(reload) transitions without a
 * real Dex instance. The live/no-mocks proof of the actual flow is
 * tests/e2e-oidc/oidc-login.spec.ts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const mockOidcAuth = {
  isAuthenticated: false,
  isLoading: false,
  error: undefined as { message: string } | undefined,
  signinRedirect: vi.fn(),
  removeUser: vi.fn(),
}

vi.mock('react-oidc-context', () => ({
  useAuth: () => mockOidcAuth,
}))

vi.mock('../../../src/api', () => ({
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
}))

describe('useAuth (slice 008 seam)', () => {
  beforeEach(() => {
    vi.unstubAllEnvs()
    sessionStorage.clear()
    mockOidcAuth.isAuthenticated = false
    mockOidcAuth.isLoading = false
    mockOidcAuth.error = undefined
    mockOidcAuth.signinRedirect.mockClear()
    mockOidcAuth.removeUser.mockClear()
  })

  afterEach(() => {
    vi.resetModules()
  })

  it('is unauthenticated and not loading by default (signed-out)', async () => {
    const { useAuth } = await import('../../../src/hooks/useAuth')
    const { result } = renderHook(() => useAuth())
    expect(result.current.authenticated).toBe(false)
    expect(result.current.isLoading).toBe(false)
  })

  it('signIn() with no argument starts the real OIDC redirect', async () => {
    const { useAuth } = await import('../../../src/hooks/useAuth')
    const { result } = renderHook(() => useAuth())
    act(() => {
      result.current.signIn()
    })
    expect(mockOidcAuth.signinRedirect).toHaveBeenCalledTimes(1)
  })

  it('reflects the library isAuthenticated flag once signed in', async () => {
    mockOidcAuth.isAuthenticated = true
    const { useAuth } = await import('../../../src/hooks/useAuth')
    const { result } = renderHook(() => useAuth())
    expect(result.current.authenticated).toBe(true)
  })

  it('reports isLoading while the library is still rehydrating a session (reload)', async () => {
    mockOidcAuth.isAuthenticated = false
    mockOidcAuth.isLoading = true
    const { useAuth } = await import('../../../src/hooks/useAuth')
    const { result } = renderHook(() => useAuth())
    // FR-004: a caller (ProtectedRoute) must not treat this as "signed out"
    // while a persisted session might still be loading.
    expect(result.current.isLoading).toBe(true)
    expect(result.current.authenticated).toBe(false)
  })

  it('is never "loading" in mock mode, regardless of the library state', async () => {
    vi.stubEnv('VITE_USE_MOCK', 'true')
    mockOidcAuth.isLoading = true
    const { useAuth } = await import('../../../src/hooks/useAuth')
    const { result } = renderHook(() => useAuth())
    expect(result.current.isLoading).toBe(false)
    expect(result.current.authenticated).toBe(true)
  })

  it('signOut() clears the OIDC session', async () => {
    mockOidcAuth.isAuthenticated = true
    const { useAuth } = await import('../../../src/hooks/useAuth')
    const { result } = renderHook(() => useAuth())
    act(() => {
      result.current.signOut()
    })
    expect(mockOidcAuth.removeUser).toHaveBeenCalledTimes(1)
  })
})
