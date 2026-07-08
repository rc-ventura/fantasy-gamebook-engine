/**
 * CallbackPage — the OIDC redirect_uri target (slice 008).
 *
 * <AuthProvider> (main.tsx) processes the /callback?code=...&state=... round trip
 * automatically on mount; this page just waits for that to resolve and routes
 * onward. A replayed/bookmarked callback URL finds no matching pending sign-in
 * state in the library and surfaces as `auth.error` (FR-008).
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from 'react-oidc-context'

export default function CallbackPage() {
  const auth = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    if (auth.isLoading) return
    if (auth.error) {
      navigate('/auth', { replace: true, state: { error: auth.error.message } })
      return
    }
    if (auth.isAuthenticated) {
      navigate('/dashboard', { replace: true })
    }
  }, [auth.isLoading, auth.error, auth.isAuthenticated, navigate])

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.75rem',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        color: 'var(--muted)',
      }}
    >
      Signing you in…
    </div>
  )
}
