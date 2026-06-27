/**
 * AuthPage — Sign-in / Register panel.
 *
 * Auth seam: uses the dev auth stub from slice 003 until slice 004 ships real OIDC.
 * The seam design ensures the real OIDC provider swaps in without touching the play loop.
 *
 * Dev auth stub: any non-empty token is accepted (the backend validates via VITE_DEV_TOKEN).
 * In VITE_USE_MOCK mode, sign-in always succeeds with a mock token.
 *
 * Matches the prototype's centered card design on the same dark theme.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

type TabId = 'signin' | 'register'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'
const DEV_TOKEN = (() => {
  const t = import.meta.env.VITE_DEV_TOKEN
  return typeof t === 'string' && t.length > 0 ? t : 'dev-token-grimoire'
})()

export default function AuthPage() {
  const navigate = useNavigate()
  const { signIn } = useAuth()
  const [tab, setTab] = useState<TabId>('signin')
  const [token, setToken] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (USE_MOCK) {
        // Mock mode: sign in immediately with a mock token.
        signIn('mock-token-dev')
        navigate('/dashboard')
        return
      }
      // Dev auth stub: accept the token provided (or the VITE_DEV_TOKEN env var).
      const authToken = token.trim() || DEV_TOKEN
      if (!authToken) {
        setError('Please enter an auth token.')
        return
      }
      signIn(authToken)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setLoading(false)
    }
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
      }}
    >
      {/* Glyph */}
      <div
        style={{
          fontFamily: 'var(--font-title)',
          fontSize: '3rem',
          color: 'var(--accent)',
          marginBottom: 'var(--space-lg)',
        }}
        aria-hidden="true"
      >
        ◆
      </div>

      {/* Card */}
      <div
        style={{
          background: 'var(--panel-bg)',
          border: '1px solid var(--panel-border)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-2xl)',
          width: '100%',
          maxWidth: '400px',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-lg)',
        }}
      >
        <h1
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '1.25rem',
            letterSpacing: '0.08em',
            textAlign: 'center',
            margin: 0,
          }}
        >
          The Grimoire
        </h1>

        {/* Tabs */}
        <div
          role="tablist"
          aria-label="Authentication mode"
          style={{
            display: 'flex',
            borderBottom: '1px solid var(--line)',
            gap: 0,
          }}
        >
          {(['signin', 'register'] as TabId[]).map((t) => (
            <button
              key={t}
              role="tab"
              aria-selected={tab === t}
              onClick={() => { setTab(t); setError(null) }}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
                color: tab === t ? 'var(--accent)' : 'var(--muted)',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.7rem',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                padding: 'var(--space-sm) 0',
                cursor: 'pointer',
                transition: 'all var(--transition)',
              }}
            >
              {t === 'signin' ? 'Sign In' : 'Register'}
            </button>
          ))}
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}
          aria-label={tab === 'signin' ? 'Sign in form' : 'Register form'}
        >
          {tab === 'register' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
              <label
                htmlFor="auth-email"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}
              >
                Email
              </label>
              <input
                id="auth-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="adventurer@example.com"
                autoComplete="email"
                style={{
                  background: 'var(--bg)',
                  border: '1px solid var(--panel-border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: 'var(--space-sm) var(--space-md)',
                  color: 'var(--ink)',
                  fontFamily: 'var(--font-body)',
                  fontSize: '1rem',
                  outline: 'none',
                }}
                onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--panel-border)' }}
              />
            </div>
          )}

          {!USE_MOCK && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
              <label
                htmlFor="auth-token"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}
              >
                Dev Auth Token
              </label>
              <input
                id="auth-token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={`Default: ${DEV_TOKEN.slice(0, 6)}…`}
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
                onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
                onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--panel-border)' }}
              />
              <span
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--faint)', lineHeight: 1.4 }}
              >
                Dev auth stub — set VITE_DEV_TOKEN in .env.local.
                Real OIDC lands in slice 004.
              </span>
            </div>
          )}

          {USE_MOCK && (
            <p
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--faint)', textAlign: 'center', lineHeight: 1.5 }}
            >
              Mock mode active — sign-in auto-succeeds.
            </p>
          )}

          {error && (
            <p
              role="alert"
              style={{ fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: '#c0392b', margin: 0 }}
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            aria-busy={loading}
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
              cursor: loading ? 'wait' : 'pointer',
              opacity: loading ? 0.6 : 1,
              transition: 'opacity var(--transition)',
            }}
          >
            {loading ? 'Entering…' : tab === 'signin' ? 'Enter the Grimoire' : 'Create Account'}
          </button>
        </form>

        <p
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.85rem',
            color: 'var(--faint)',
            textAlign: 'center',
            margin: 0,
          }}
        >
          {tab === 'signin' ? "Don't have an account? " : 'Already have an account? '}
          <button
            onClick={() => { setTab(tab === 'signin' ? 'register' : 'signin'); setError(null) }}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--accent)',
              fontFamily: 'var(--font-body)',
              fontSize: '0.85rem',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            {tab === 'signin' ? 'Register' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  )
}
