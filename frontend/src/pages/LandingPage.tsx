/**
 * LandingPage — placeholder.
 *
 * Full implementation in T006 (app shell + routing) and T024 (professional styling pass).
 * Mirrors the Landing / Marketing screen from the Fantasy Gamebook prototype:
 *   - Hero: "The Grimoire of Claude Code" + feature grid + how-it-works steps
 *   - Same dark theme (--bg, --accent, --ink tokens)
 */
export default function LandingPage() {
  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: '1rem',
        padding: '2rem',
      }}
    >
      <h1
        style={{
          fontFamily: 'var(--font-title)',
          color: 'var(--accent)',
          fontSize: '3rem',
          letterSpacing: '0.08em',
          textAlign: 'center',
        }}
      >
        The Grimoire
      </h1>
      <p
        style={{
          fontFamily: 'var(--font-body)',
          color: 'var(--muted)',
          fontSize: '1.125rem',
          textAlign: 'center',
          maxWidth: '480px',
        }}
      >
        A Fighting Fantasy-style gamebook powered by an AI Game Master.
      </p>
      <p
        style={{
          fontFamily: 'var(--font-mono)',
          color: 'var(--faint)',
          fontSize: '0.75rem',
          textAlign: 'center',
        }}
      >
        {/* T006: replace with real navigation / CTA */}
        Professional UI coming in T006–T024 …
      </p>
    </main>
  )
}
