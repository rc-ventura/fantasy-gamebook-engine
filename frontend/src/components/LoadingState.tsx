/**
 * LoadingState — shown while an async operation is in flight.
 * Used in every panel to prevent frozen or unexplained screens.
 */

interface LoadingStateProps {
  message?: string
  size?: 'sm' | 'md' | 'lg'
}

export default function LoadingState({ message = 'Loading…', size = 'md' }: LoadingStateProps) {
  const sizes: Record<'sm' | 'md' | 'lg', number> = { sm: 20, md: 36, lg: 56 }
  const px = sizes[size]

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-md)',
        padding: 'var(--space-xl)',
        color: 'var(--muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: '0.8rem',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}
      role="status"
      aria-label={message}
    >
      {/* Animated spinner using CSS border trick */}
      <svg
        width={px}
        height={px}
        viewBox="0 0 36 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        style={{ animation: 'spin 1s linear infinite' }}
      >
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
        <circle
          cx="18"
          cy="18"
          r="15"
          stroke="var(--faint)"
          strokeWidth="3"
          fill="none"
        />
        <path
          d="M18 3 A15 15 0 0 1 33 18"
          stroke="var(--accent)"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      <span>{message}</span>
    </div>
  )
}
