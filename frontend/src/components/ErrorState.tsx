/**
 * ErrorState — shown when an API error or unexpected failure occurs.
 *
 * Provides a clear, safe error state so the player never sees a broken
 * or unexplained screen. The player's last consistent state is preserved
 * on reload (no corrupted game state).
 */

interface ErrorStateProps {
  message: string
  onRetry?: () => void
  /** If true, the error is recoverable via onRetry. */
  recoverable?: boolean
}

export default function ErrorState({ message, onRetry, recoverable = true }: ErrorStateProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-md)',
        padding: 'var(--space-xl)',
        textAlign: 'center',
      }}
    >
      {/* Rune / warning glyph */}
      <span
        aria-hidden="true"
        style={{
          fontFamily: 'var(--font-title)',
          fontSize: '2.5rem',
          color: 'var(--accent)',
          opacity: 0.6,
        }}
      >
        ⚠
      </span>
      <p
        style={{
          fontFamily: 'var(--font-body)',
          color: 'var(--muted)',
          fontSize: '1rem',
          maxWidth: '360px',
          lineHeight: 1.6,
        }}
      >
        {message}
      </p>
      {recoverable && onRetry && (
        <button
          onClick={onRetry}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.75rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            background: 'transparent',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-sm) var(--space-lg)',
            cursor: 'pointer',
            transition: 'background var(--transition)',
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.background = 'rgba(217,122,60,0.12)'
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.background = 'transparent'
          }}
        >
          Try again
        </button>
      )}
    </div>
  )
}
