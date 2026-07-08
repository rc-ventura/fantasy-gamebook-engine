/**
 * AuthPage — Sign-in panel (slice 008, ADR-034).
 *
 * Primary path (FR-001): a real "Login" redirect to the OIDC provider (Dex
 * locally; any OIDC-compliant provider in production) — no in-app token entry,
 * no in-app registration (account creation is the identity provider's own
 * responsibility, per spec 008's Assumptions).
 *
 * Dev-only fallback (FR-009): the paste-a-token stub remains available behind
 * import.meta.env.DEV for local development without a running Dex instance —
 * absent entirely from a production build.
 *
 * Mock mode (VITE_USE_MOCK=true): sign-in always auto-succeeds, no provider
 * involved — unaffected by this slice.
 */

import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
const SHOW_DEV_FALLBACK = Boolean(import.meta.env.DEV) && !USE_MOCK

export default function AuthPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { signIn } = useAuth()
  const [devToken, setDevToken] = useState('')
  const [showDevFallback, setShowDevFallback] = useState(false)
  const routedError = (location.state as { error?: string } | null)?.error ?? null
  const [error, setError] = useState<string | null>(routedError)

  function handleLogin() {
    setError(null)
    if (USE_MOCK) {
      signIn('mock-token-dev')
      void navigate('/dashboard')
      return
    }
    signIn()
  }

  function handleDevTokenSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const token = devToken.trim() || (import.meta.env.VITE_DEV_TOKEN ?? '')
    if (!token) {
      setError('Enter a dev token or set VITE_DEV_TOKEN.')
      return
    }
    signIn(token)
    void navigate('/dashboard')
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-xl)',
        position: 'relative',
      }}
    >
      {/* Back link */}
      <button
        onClick={() => { void navigate('/') }}
        style={{
          position: 'absolute', top: '26px', left: '34px',
          fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.1em', textTransform: 'uppercase',
          background: 'transparent', border: 'none', color: 'var(--faint)', cursor: 'pointer',
        }}
      >
        ← Back to the Grimoire
      </button>

      {/* Glyph */}
      <div
        style={{
          fontFamily: 'var(--font-title)',
          fontSize: '1.3rem',
          color: 'var(--accent)',
          marginBottom: 'var(--space-sm)',
          textAlign: 'center',
        }}
        aria-hidden="true"
      >
        ◆
      </div>
      <div style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.7rem', color: 'var(--ink)', marginBottom: '4px', textAlign: 'center' }}>
        Return to the Grimoire
      </div>
      <div style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '1.05rem', color: 'var(--muted)', marginBottom: 'var(--space-lg)', textAlign: 'center' }}>
        Sign in to resume your campaigns.
      </div>

      {/* Card */}
      <div
        style={{
          background: 'var(--panel-bg)',
          border: '1px solid var(--panel-border)',
          borderRadius: '5px',
          padding: '32px',
          width: '100%',
          maxWidth: '430px',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-lg)',
          boxShadow: '0 30px 70px rgba(0,0,0,.4)',
        }}
      >
        {error && (
          <p
            role="alert"
            style={{ fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: '#c0392b', margin: 0 }}
          >
            {error}
          </p>
        )}

        {USE_MOCK ? (
          <p
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--faint)', textAlign: 'center', lineHeight: 1.5 }}
          >
            Mock mode active — sign-in auto-succeeds.
          </p>
        ) : null}

        <button
          type="button"
          onClick={handleLogin}
          style={{
            background: 'var(--accent)',
            color: 'var(--accent-ink)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-md)',
            fontFamily: 'var(--font-title)',
            fontSize: '0.85rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            cursor: 'pointer',
          }}
        >
          Login
        </button>

        <p
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.85rem',
            color: 'var(--faint)',
            textAlign: 'center',
            margin: 0,
          }}
        >
          New to the Grey Mountain? Login takes you to sign-in — create your account there.
        </p>

        {SHOW_DEV_FALLBACK && (
          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 'var(--space-md)' }}>
            <button
              type="button"
              onClick={() => { setShowDevFallback((v) => !v) }}
              style={{
                background: 'none', border: 'none', color: 'var(--faint)',
                fontFamily: 'var(--font-mono)', fontSize: '0.65rem', letterSpacing: '0.08em',
                textTransform: 'uppercase', cursor: 'pointer', padding: 0,
              }}
            >
              {showDevFallback ? '▾' : '▸'} Dev auth stub (local only)
            </button>
            {showDevFallback && (
              <form
                onSubmit={handleDevTokenSubmit}
                style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)', marginTop: 'var(--space-sm)' }}
                aria-label="Dev token sign-in"
              >
                <label
                  htmlFor="auth-token"
                  style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}
                >
                  Dev Auth Token
                </label>
                <input
                  id="auth-token"
                  type="password"
                  value={devToken}
                  onChange={(e) => { setDevToken(e.target.value) }}
                  placeholder="Default: VITE_DEV_TOKEN"
                  autoComplete="current-password"
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--panel-border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 'var(--space-sm) var(--space-md)',
                    color: 'var(--ink)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.9rem',
                    outline: 'none',
                  }}
                />
                <button
                  type="submit"
                  style={{
                    background: 'transparent',
                    color: 'var(--muted)',
                    border: '1px solid var(--panel-border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: 'var(--space-sm)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                  }}
                >
                  Sign in with dev token
                </button>
              </form>
            )}
          </div>
        )}
      </div>

      <p style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.64rem', letterSpacing: '0.06em', color: 'var(--faint)', marginTop: '20px' }}>
        Your character sheets &amp; campaigns persist to your account.
      </p>
    </div>
  )
}
