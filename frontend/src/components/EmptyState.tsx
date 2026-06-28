/**
 * EmptyState — shown when a panel has no data yet (no character, empty inventory, etc.).
 * Gives the player a clear, helpful message instead of a blank or broken layout.
 */

interface EmptyStateProps {
  /** Short description of what's missing. */
  message: string
  /** Optional hint or call-to-action. */
  hint?: string
  /** Optional glyph / icon shown above the message. */
  icon?: string
}

export default function EmptyState({ message, hint, icon = '◆' }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-sm)',
        padding: 'var(--space-xl)',
        textAlign: 'center',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          fontFamily: 'var(--font-title)',
          fontSize: '1.5rem',
          color: 'var(--faint)',
        }}
      >
        {icon}
      </span>
      <p
        style={{
          fontFamily: 'var(--font-body)',
          color: 'var(--muted)',
          fontSize: '0.95rem',
          lineHeight: 1.5,
        }}
      >
        {message}
      </p>
      {hint && (
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            color: 'var(--faint)',
            fontSize: '0.75rem',
            letterSpacing: '0.05em',
          }}
        >
          {hint}
        </p>
      )}
    </div>
  )
}
