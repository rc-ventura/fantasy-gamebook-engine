/**
 * NarratorPanel — renders the current scene's narrative prose.
 *
 * Uses EB Garamond for body text (matching the prototype).
 * Renders loading/empty states when no scene is available.
 * Every paragraph of text comes from the API scene.narrative — nothing is invented client-side.
 */

import LoadingState from './LoadingState'
import EmptyState from './EmptyState'

interface NarratorPanelProps {
  /** The narrative prose from the API scene. Never client-invented. */
  narrative: string | null | undefined
  loading?: boolean
  /** True on terminal scenes (death or victory) — no further choices available. */
  isTerminal?: boolean
}

export default function NarratorPanel({ narrative, loading = false, isTerminal = false }: NarratorPanelProps) {
  if (loading) {
    return <LoadingState message="The narrator weaves the tale…" />
  }

  if (!narrative) {
    return (
      <EmptyState
        message="The tale has not yet begun."
        hint="Create a character to start your adventure."
        icon="📖"
      />
    )
  }

  // Split on double newlines for paragraph rendering.
  const paragraphs = narrative.split(/\n\n+/).filter(Boolean)

  return (
    <section
      aria-label="Narrator"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-md)',
        padding: 'var(--space-xl)',
        background: 'var(--panel-bg)',
        border: '1px solid var(--panel-border)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      {isTerminal && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            color: 'var(--faint)',
            borderBottom: '1px solid var(--line)',
            paddingBottom: 'var(--space-sm)',
            marginBottom: 'var(--space-sm)',
          }}
          aria-label="Adventure ended"
        >
          — End of Adventure —
        </div>
      )}
      {paragraphs.map((para, i) => (
        <p
          key={i}
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '1.125rem',
            color: 'var(--panel-ink)',
            lineHeight: 1.75,
            margin: 0,
          }}
        >
          {para}
        </p>
      ))}
    </section>
  )
}
