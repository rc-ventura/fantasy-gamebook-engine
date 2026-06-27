/**
 * DashboardPage — Campaign list / "My Adventures" screen.
 *
 * Shows only the signed-in player's campaigns (FR-011).
 * Allows creating new campaigns and resuming existing ones.
 * Matches the prototype's dashboard design with sticky header + campaign cards.
 */

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useCampaign } from '../hooks/useCampaign'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'

export default function DashboardPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const { state, campaigns, error, onCreate, onDelete, onReload } = useCampaign()

  async function handleCreate() {
    try {
      const id = await onCreate()
      navigate(`/play/${id}`)
    } catch {
      // Error is surfaced via the hook's error state
    }
  }

  function handleResume(id: string) {
    navigate(`/play/${id}`)
  }

  function handleSignOut() {
    signOut()
    navigate('/')
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
      {/* ── Sticky header ── */}
      <header
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 100,
          background: 'var(--bg2)',
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: 'var(--space-md) var(--space-2xl)',
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
        <nav style={{ display: 'flex', gap: 'var(--space-md)', alignItems: 'center' }}>
          <button
            onClick={() => { void handleCreate() }}
            style={{
              background: 'var(--accent)',
              color: 'var(--accent-ink)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: '6px var(--space-md)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.7rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
            aria-label="New adventure"
          >
            + New Adventure
          </button>
          <button
            onClick={() => { void handleSignOut() }}
            style={{
              background: 'transparent',
              color: 'var(--muted)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--radius-sm)',
              padding: '6px var(--space-md)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.7rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
            aria-label="Sign out"
          >
            Sign Out
          </button>
        </nav>
      </header>

      {/* ── Main content ── */}
      <main
        style={{
          flex: 1,
          padding: 'var(--space-2xl)',
          maxWidth: '900px',
          margin: '0 auto',
          width: '100%',
        }}
      >
        <h1
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '1.5rem',
            letterSpacing: '0.06em',
            marginBottom: 'var(--space-xl)',
          }}
        >
          My Adventures
        </h1>

        {state === 'loading' && <LoadingState message="Loading your campaigns…" />}

        {state === 'error' && (
          <ErrorState
            message={error ?? 'Failed to load campaigns'}
            onRetry={() => { void onReload() }}
          />
        )}

        {state === 'ready' && campaigns.length === 0 && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 'var(--space-xl)',
              paddingTop: 'var(--space-2xl)',
            }}
          >
            <EmptyState
              message="No adventures yet"
              hint="Start a new campaign to begin your journey into the Grey Mountain"
              icon="◆"
            />
            <button
              onClick={() => { void handleCreate() }}
              style={{
                background: 'var(--accent)',
                color: 'var(--accent-ink)',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                padding: 'var(--space-md) var(--space-2xl)',
                fontFamily: 'var(--font-title)',
                fontSize: '0.9rem',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              Begin an Adventure
            </button>
          </div>
        )}

        {state === 'ready' && campaigns.length > 0 && (
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-md)',
            }}
            aria-label="Campaign list"
          >
            {campaigns.map((campaign) => {
              const isEnded = campaign.status === 'ended'
              const updatedAt = new Date(campaign.updated_at)
              const dateStr = updatedAt.toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
              })
              return (
                <li
                  key={campaign.id}
                  style={{
                    background: 'var(--panel-bg)',
                    border: '1px solid var(--panel-border)',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-lg)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 'var(--space-md)',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
                      <span
                        style={{
                          fontFamily: 'var(--font-title)',
                          color: isEnded ? 'var(--muted)' : 'var(--ink)',
                          fontSize: '1rem',
                          letterSpacing: '0.04em',
                        }}
                      >
                        Grey Mountain Expedition
                      </span>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.6rem',
                          letterSpacing: '0.08em',
                          textTransform: 'uppercase',
                          color: isEnded ? 'var(--faint)' : 'var(--accent)',
                          background: isEnded ? 'var(--line)' : 'rgba(217,122,60,0.15)',
                          borderRadius: '2px',
                          padding: '1px 6px',
                        }}
                        aria-label={`Status: ${campaign.status}`}
                      >
                        {campaign.status}
                      </span>
                    </div>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.65rem',
                        color: 'var(--faint)',
                        letterSpacing: '0.05em',
                      }}
                    >
                      Last played {dateStr} · ID: {campaign.id.slice(0, 8)}
                    </span>
                  </div>

                  <div style={{ display: 'flex', gap: 'var(--space-sm)', flexShrink: 0 }}>
                    <button
                      onClick={() => { void handleResume(campaign.id) }}
                      aria-label={isEnded ? `View ended campaign ${campaign.id}` : `Resume campaign ${campaign.id}`}
                      style={{
                        background: isEnded ? 'transparent' : 'var(--accent)',
                        color: isEnded ? 'var(--muted)' : 'var(--accent-ink)',
                        border: isEnded ? '1px solid var(--line)' : 'none',
                        borderRadius: 'var(--radius-sm)',
                        padding: '6px var(--space-md)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.7rem',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        cursor: 'pointer',
                      }}
                    >
                      {isEnded ? 'View' : 'Resume'}
                    </button>
                    <button
                      onClick={() => { void onDelete(campaign.id) }}
                      aria-label={`Delete campaign ${campaign.id}`}
                      style={{
                        background: 'transparent',
                        color: 'var(--faint)',
                        border: '1px solid var(--line)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '6px var(--space-md)',
                        fontFamily: 'var(--font-mono)',
                        fontSize: '0.7rem',
                        letterSpacing: '0.08em',
                        textTransform: 'uppercase',
                        cursor: 'pointer',
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </main>
    </div>
  )
}
