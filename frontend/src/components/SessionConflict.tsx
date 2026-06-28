/**
 * SessionConflict — shown when the API returns 409 not_session_holder.
 *
 * Implements the single-active-session UX (FR-013):
 * The second tab/device is read-only until it explicitly takes over.
 * This prompt allows the player to claim the write lease.
 */

interface SessionConflictProps {
  onTakeover: () => void | Promise<void>
  loading?: boolean
}

export default function SessionConflict({ onTakeover, loading = false }: SessionConflictProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Session conflict"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(21,17,13,0.92)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 'var(--space-xl)',
      }}
    >
      <div
        style={{
          background: 'var(--panel-bg)',
          border: '1px solid var(--accent)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-2xl)',
          maxWidth: '440px',
          width: '100%',
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-lg)',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            fontFamily: 'var(--font-title)',
            fontSize: '2rem',
            color: 'var(--accent)',
          }}
        >
          ⚔
        </span>
        <h2
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '1.25rem',
            letterSpacing: '0.05em',
          }}
        >
          Another Session Is Active
        </h2>
        <p
          style={{
            fontFamily: 'var(--font-body)',
            color: 'var(--panel-muted)',
            fontSize: '1rem',
            lineHeight: 1.65,
          }}
        >
          This campaign is currently open in another tab or device. You may
          view it in read-only mode, or take over to continue playing here.
        </p>
        <p
          style={{
            fontFamily: 'var(--font-mono)',
            color: 'var(--faint)',
            fontSize: '0.75rem',
          }}
        >
          Taking over will make the other session read-only.
        </p>
        <button
          onClick={() => { void Promise.resolve(onTakeover()) }}
          disabled={loading}
          aria-busy={loading}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.8rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            background: 'var(--accent)',
            color: 'var(--accent-ink)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-sm) var(--space-xl)',
            cursor: loading ? 'wait' : 'pointer',
            opacity: loading ? 0.6 : 1,
            transition: 'opacity var(--transition)',
          }}
        >
          {loading ? 'Taking over…' : 'Take Over Session'}
        </button>
      </div>
    </div>
  )
}
