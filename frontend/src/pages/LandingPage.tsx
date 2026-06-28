/**
 * LandingPage — Marketing / Hero screen.
 *
 * Matches the "Fantasy Gamebook" prototype design:
 *   - Hero: "The Grimoire of Claude Code" headline + tagline
 *   - Feature grid: three pillars of the experience
 *   - How-it-works: three steps
 *   - CTA: Begin Your Adventure → /auth (or /dashboard if authed)
 *
 * Design tokens from index.css: --bg, --accent, --ink, --font-title, --font-body, --font-mono
 */

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const FEATURES = [
  {
    icon: '◆',
    title: 'Engine-Authoritative',
    body: 'Every dice roll, luck test, and combat outcome is computed by the engine — never invented by the narrator or the UI.',
  },
  {
    icon: '📖',
    title: 'AI Narration',
    body: 'A Claude-powered Game Master weaves your unique story across the Grey Mountain, reacting to every choice you make.',
  },
  {
    icon: '⚔',
    title: 'Full Combat System',
    body: 'Fight creatures, test your luck, and flee when overwhelmed — with Fighting Fantasy rules enforced by the engine.',
  },
]

const STEPS = [
  { n: '01', label: 'Create your hero', detail: 'Attributes are rolled by the engine (SKILL 1d6+6, STAMINA 2d6+12, LUCK 1d6+6).' },
  { n: '02', label: 'Enter the Grimoire', detail: 'The AI narrator describes the world and offers numbered choices or free text.' },
  { n: '03', label: 'Reach your destiny', detail: 'Defeat Malachar or fall to the mountain — every number on screen is engine-real.' },
]

export default function LandingPage() {
  const navigate = useNavigate()
  const { authenticated } = useAuth()

  function handleCta() {
    if (authenticated) {
      void navigate('/dashboard')
    } else {
      void navigate('/auth')
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* ── Nav ── */}
      <nav
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: 'var(--space-lg) var(--space-2xl)',
          borderBottom: '1px solid var(--line)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '1rem',
            letterSpacing: '0.1em',
          }}
        >
          THE GRIMOIRE
        </span>
        <button
          onClick={() => { void navigate(authenticated ? '/dashboard' : '/auth') }}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            background: 'transparent',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-sm)',
            padding: '6px var(--space-md)',
            cursor: 'pointer',
          }}
        >
          {authenticated ? 'Dashboard' : 'Sign In'}
        </button>
      </nav>

      {/* ── Hero ── */}
      <header
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 'var(--space-2xl) var(--space-xl)',
          textAlign: 'center',
          flex: 1,
          gap: 'var(--space-xl)',
          maxWidth: '800px',
          margin: '0 auto',
          width: '100%',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-title)',
            fontSize: '5rem',
            color: 'var(--accent)',
            lineHeight: 1,
          }}
          aria-hidden="true"
        >
          ◆
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: 'clamp(2rem, 5vw, 3.5rem)',
            letterSpacing: '0.06em',
            lineHeight: 1.15,
          }}
        >
          The Grimoire of Claude Code
        </h1>
        <p
          style={{
            fontFamily: 'var(--font-body)',
            color: 'var(--muted)',
            fontSize: '1.2rem',
            lineHeight: 1.7,
            maxWidth: '560px',
          }}
        >
          A Fighting Fantasy–style gamebook powered by an AI Game Master.
          Every number on screen was rolled by the engine — never invented in prose.
        </p>
        <button
          onClick={handleCta}
          style={{
            fontFamily: 'var(--font-title)',
            fontSize: '0.9rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            background: 'var(--accent)',
            color: 'var(--accent-ink)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-md) var(--space-2xl)',
            cursor: 'pointer',
            transition: 'background var(--transition)',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.background = 'var(--accent-hover)'
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = 'var(--accent)'
          }}
        >
          Begin Your Adventure
        </button>
      </header>

      {/* ── Features ── */}
      <section
        style={{
          padding: 'var(--space-2xl) var(--space-xl)',
          borderTop: '1px solid var(--line)',
          background: 'var(--bg2)',
        }}
        aria-label="Features"
      >
        <h2
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '1rem',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            textAlign: 'center',
            marginBottom: 'var(--space-xl)',
          }}
        >
          Why the Grimoire
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: 'var(--space-lg)',
            maxWidth: '900px',
            margin: '0 auto',
          }}
        >
          {FEATURES.map((f) => (
            <div
              key={f.title}
              style={{
                background: 'var(--panel-bg)',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-lg)',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-sm)',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-title)',
                  fontSize: '1.5rem',
                  color: 'var(--accent)',
                }}
                aria-hidden="true"
              >
                {f.icon}
              </span>
              <h3
                style={{
                  fontFamily: 'var(--font-title)',
                  color: 'var(--ink)',
                  fontSize: '0.9rem',
                  letterSpacing: '0.05em',
                  margin: 0,
                }}
              >
                {f.title}
              </h3>
              <p
                style={{
                  fontFamily: 'var(--font-body)',
                  color: 'var(--muted)',
                  fontSize: '0.9rem',
                  lineHeight: 1.65,
                  margin: 0,
                }}
              >
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section
        style={{
          padding: 'var(--space-2xl) var(--space-xl)',
          borderTop: '1px solid var(--line)',
        }}
        aria-label="How it works"
      >
        <h2
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '1rem',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            textAlign: 'center',
            marginBottom: 'var(--space-xl)',
          }}
        >
          How It Works
        </h2>
        <ol
          style={{
            listStyle: 'none',
            margin: '0 auto',
            padding: 0,
            maxWidth: '700px',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-lg)',
          }}
        >
          {STEPS.map((s) => (
            <li
              key={s.n}
              style={{
                display: 'flex',
                gap: 'var(--space-lg)',
                alignItems: 'flex-start',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.7rem',
                  color: 'var(--accent)',
                  letterSpacing: '0.1em',
                  minWidth: '2rem',
                  paddingTop: '0.2rem',
                  flexShrink: 0,
                }}
                aria-hidden="true"
              >
                {s.n}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span
                  style={{
                    fontFamily: 'var(--font-title)',
                    color: 'var(--ink)',
                    fontSize: '1rem',
                    letterSpacing: '0.04em',
                  }}
                >
                  {s.label}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    color: 'var(--muted)',
                    fontSize: '0.9rem',
                    lineHeight: 1.6,
                  }}
                >
                  {s.detail}
                </span>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* ── Footer ── */}
      <footer
        style={{
          borderTop: '1px solid var(--line)',
          padding: 'var(--space-lg) var(--space-xl)',
          textAlign: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.65rem',
          letterSpacing: '0.08em',
          color: 'var(--faint)',
        }}
      >
        THE GRIMOIRE OF CLAUDE CODE · Fantasy Gamebook Engine · Slice 005
      </footer>
    </div>
  )
}
