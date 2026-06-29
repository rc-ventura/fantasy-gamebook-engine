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
    tag: '/game-master',
    title: 'The Narrator',
    body: 'Claude opens your sheet, narrates in second person, offers numbered choices and compacts the story as it grows.',
  },
  {
    tag: 'MCP · 18 tools',
    title: 'The Engine',
    body: 'A deterministic Python core owns dice, attributes, luck tests and combat math. Reproducible, seedable, never improvised.',
  },
  {
    tag: '/ignarok',
    title: 'The Adventure',
    body: 'Six zones of the Grey Mountain, a full bestiary, and one archmage to defeat. Swap the module to play a different tale.',
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
      <header style={{
        position: 'sticky', top: 0, zIndex: 30,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 40px', height: '66px',
        background: 'rgba(21,17,13,.82)', backdropFilter: 'blur(10px)',
        borderBottom: '1px solid var(--line)',
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ color: 'var(--accent)', fontSize: '1.1rem' }}>◆</span>
          <span style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.92rem', letterSpacing: '0.12em', color: 'var(--ink)' }}>
            THE GRIMOIRE
          </span>
        </div>
        {/* Center nav links */}
        <nav style={{ display: 'flex', gap: '30px', fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)' }}>
          <a href="#concept" style={{ color: 'inherit', textDecoration: 'none', cursor: 'pointer' }}>The Concept</a>
          <a href="#engine" style={{ color: 'inherit', textDecoration: 'none', cursor: 'pointer' }}>The Engine</a>
          <a href="#modules" style={{ color: 'inherit', textDecoration: 'none', cursor: 'pointer' }}>Modules</a>
        </nav>
        {/* Right CTAs */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={() => { void navigate(authenticated ? '/dashboard' : '/auth') }}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase',
              padding: '9px 16px', background: 'transparent', border: '1px solid var(--line)', borderRadius: '3px', color: 'var(--ink)', cursor: 'pointer',
            }}
            onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
            onMouseOut={(e) => { e.currentTarget.style.borderColor = 'var(--line)' }}
          >
            {authenticated ? 'Dashboard' : 'Log in'}
          </button>
          {!authenticated && (
            <button
              onClick={() => { void navigate('/auth') }}
              style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase',
                padding: '9px 16px', background: 'var(--accent)', border: 'none', borderRadius: '3px', color: 'var(--accent-ink)', cursor: 'pointer',
              }}
              onMouseOver={(e) => { e.currentTarget.style.filter = 'brightness(1.08)' }}
              onMouseOut={(e) => { e.currentTarget.style.filter = '' }}
            >
              Create account
            </button>
          )}
        </div>
      </header>

      {/* ── Hero ── */}
      <section
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          padding: '84px 24px 70px',
        }}
      >
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.74rem', letterSpacing: '0.32em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '22px' }}>
          The Grimoire of Claude Code
        </div>
        <h1 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: 'clamp(2.8rem, 6.4vw, 4.8rem)', lineHeight: 1.03, margin: '0 0 20px', color: 'var(--ink)', maxWidth: '880px' }}>
          The Fantasy Gamebook
        </h1>
        <p style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '1.4rem', color: 'var(--muted)', margin: '0 0 14px' }}>
          "You are the hero. Claude narrates. The engine decides."
        </p>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.18rem', lineHeight: 1.6, color: 'var(--muted)', maxWidth: '600px', margin: '0 0 36px' }}>
          A solo-play, Fighting Fantasy–style gamebook where an AI improvises the story — but every dice roll, stat change and combat outcome is decided by a deterministic engine.
        </p>
        <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', justifyContent: 'center', marginBottom: '18px' }}>
          <button
            onClick={handleCta}
            style={{
              fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.95rem', letterSpacing: '0.04em',
              padding: '16px 34px', background: 'var(--accent)', color: 'var(--accent-ink)',
              border: 'none', borderRadius: '3px', cursor: 'pointer',
            }}
            onMouseOver={(e) => { e.currentTarget.style.filter = 'brightness(1.08)' }}
            onMouseOut={(e) => { e.currentTarget.style.filter = '' }}
          >
            {authenticated ? 'Return to the Hall →' : 'Create your account →'}
          </button>
          {!authenticated && (
            <button
              onClick={() => { void navigate('/auth') }}
              style={{
                fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.95rem', letterSpacing: '0.04em',
                padding: '16px 34px', background: 'transparent', color: 'var(--ink)',
                border: '1px solid var(--line)', borderRadius: '3px', cursor: 'pointer',
              }}
              onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
              onMouseOut={(e) => { e.currentTarget.style.borderColor = 'var(--line)' }}
            >
              Log in
            </button>
          )}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', letterSpacing: '0.08em', color: 'var(--faint)' }}>
          No setup · Your campaigns are saved to your account
        </div>
      </section>

      {/* ── Product screenshot placeholder ── */}
      <div style={{ maxWidth: '840px', width: '100%', margin: '0 auto', padding: '0 24px' }}>
        <div style={{
          position: 'relative', border: '1px solid var(--line)', borderRadius: '5px', overflow: 'hidden',
          height: '330px',
          background: 'repeating-linear-gradient(135deg, rgba(217,122,60,.05) 0 12px, transparent 12px 24px), var(--bg2)',
        }}>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
            <span style={{ fontSize: '2.2rem', color: 'var(--accent)', opacity: 0.7 }}>◆</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.74rem', letterSpacing: '0.12em', color: 'var(--faint)', textTransform: 'uppercase' }}>
              product screenshot · the play interface
            </span>
          </div>
          <div style={{ position: 'absolute', inset: 0, boxShadow: 'inset 0 0 110px rgba(0,0,0,.55)' }} />
        </div>
      </div>

      {/* ── § The Concept ── */}
      <section style={{ maxWidth: '920px', margin: '0 auto', padding: '40px 24px 30px', textAlign: 'center', borderTop: '1px solid var(--line)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.28em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '20px' }}>
          § The Concept
        </div>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.5rem', lineHeight: 1.55, color: 'var(--ink)', margin: '0 auto', maxWidth: '740px' }}>
          The AI handles <em style={{ color: 'var(--accent)' }}>language and story</em>. The engine handles <em style={{ color: 'var(--accent)' }}>math and state</em>. The narrator never invents a number and never rolls a die in prose — every outcome flows through the MCP server.
        </p>
      </section>

      {/* ── Features ── */}
      <section
        style={{
          padding: 'var(--space-2xl) var(--space-xl)',
          borderTop: '1px solid var(--line)',
          background: 'var(--bg2)',
        }}
        aria-label="Features"
      >
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.28em', textTransform: 'uppercase', color: 'var(--accent)', textAlign: 'center', marginBottom: 'var(--space-xl)' }}>
          § The Engine
        </div>
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
                borderRadius: '5px',
                padding: '28px 24px',
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', letterSpacing: '0.1em', color: 'var(--accent)', marginBottom: '14px' }}>
                {f.tag}
              </div>
              <h3 style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1.25rem', color: 'var(--panel-ink)', margin: '0 0 10px' }}>
                {f.title}
              </h3>
              <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.08rem', lineHeight: 1.55, color: 'var(--panel-muted)', margin: 0 }}>
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

      {/* ── CTA band ── */}
      <section style={{ maxWidth: '1060px', margin: '50px auto 0', padding: '0 24px 60px' }}>
        <div style={{
          background: `repeating-linear-gradient(135deg, rgba(217,122,60,.06) 0 12px, transparent 12px 24px), var(--bg2)`,
          border: '1px solid var(--accent)', borderRadius: '6px', padding: '54px 40px', textAlign: 'center',
        }}>
          <h2 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '2.1rem', color: 'var(--ink)', margin: '0 0 12px' }}>
            Begin your adventure
          </h2>
          <p style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '1.2rem', color: 'var(--muted)', margin: '0 0 26px' }}>
            "You stand at the foot of the Grey Mountain. The wind smells of ash and old iron."
          </p>
          <button
            onClick={handleCta}
            style={{
              fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.95rem', letterSpacing: '0.04em',
              padding: '16px 36px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: '3px', cursor: 'pointer',
            }}
            onMouseOver={(e) => { e.currentTarget.style.filter = 'brightness(1.08)' }}
            onMouseOut={(e) => { e.currentTarget.style.filter = '' }}
          >
            {authenticated ? 'Return to the Hall →' : 'Create your account →'}
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer style={{
        maxWidth: '1060px', margin: '0 auto', padding: '46px 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.08em', color: 'var(--faint)', textTransform: 'uppercase',
      }}>
        <span><span style={{ color: 'var(--accent)' }}>◆</span> The Grimoire of Claude Code</span>
        <span>MCP · 18 Tools · 162+ Tests</span>
      </footer>
    </div>
  )
}
