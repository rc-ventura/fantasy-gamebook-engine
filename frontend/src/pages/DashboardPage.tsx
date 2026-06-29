import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useCampaign } from '../hooks/useCampaign'
import { getAccount, getCampaign } from '../api'
import type { Account, CampaignState, CampaignSummary } from '../types'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'

type Theme = 'ember' | 'candle'

function getTheme(): Theme {
  return (localStorage.getItem('gb_theme') as Theme | null) ?? 'ember'
}

function applyTheme(t: Theme) {
  document.documentElement.classList.toggle('theme-candle', t === 'candle')
  localStorage.setItem('gb_theme', t)
}

// Derive a display name from an account (email prefix or generic)
function accountName(account: Account | null): string {
  if (!account?.email) return 'Adventurer'
  const prefix = account.email.split('@')[0]
  return prefix.charAt(0).toUpperCase() + prefix.slice(1)
}

const ADVENTURE_MODULES = [
  {
    glyph: '▲',
    title: 'Ignarok — The Grey Mountain',
    desc: 'The debut module. Six zones, one archmage.',
    locked: false,
  },
  {
    glyph: '≈',
    title: 'The Drowned Coast',
    desc: 'Coming soon',
    locked: true,
  },
  {
    glyph: '◆',
    title: 'Ashfall Reliquary',
    desc: 'Coming soon',
    locked: true,
  },
]

function registryStats(campaigns: CampaignSummary[]) {
  const total = campaigns.length
  const active = campaigns.filter((c) => c.status === 'active').length
  const ended = campaigns.filter((c) => c.status === 'ended').length
  return [
    { label: 'Campaigns', value: total, color: 'var(--ink)' },
    { label: 'Active', value: active, color: 'var(--accent)' },
    { label: 'Completed', value: ended, color: 'var(--muted)' },
    { label: 'Modules', value: 1, color: 'var(--luck)' },
  ]
}

function chronicle(campaigns: CampaignSummary[]): string[] {
  const entries: string[] = []
  const active = campaigns.find((c) => c.status === 'active')
  if (active) {
    const d = new Date(active.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    entries.push(`Last session · ${d} — Grey Mountain Expedition`)
  }
  if (campaigns.length > 0) {
    const d = new Date(campaigns[0].created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    entries.push(`Account created · joined the Grimoire ${d}`)
  }
  if (entries.length === 0) entries.push('Your chronicle is empty — begin an adventure.')
  return entries
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { signOut } = useAuth()
  const { state, campaigns, error, onCreate, onDelete, onReload } = useCampaign()
  const [account, setAccount] = useState<Account | null>(null)
  const [activeCampaignState, setActiveCampaignState] = useState<CampaignState | null>(null)
  const [theme, setTheme] = useState<Theme>(getTheme)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    getAccount().then(setAccount).catch(() => null)
  }, [])

  // Fetch full state for the active campaign to show hero stats
  useEffect(() => {
    const active = campaigns.find((c) => c.status === 'active')
    if (!active) { setActiveCampaignState(null); return }
    getCampaign(active.id).then(setActiveCampaignState).catch(() => null)
  }, [campaigns])

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'ember' ? 'candle' : 'ember'))
  }, [])

  function handleCreate() {
    void navigate('/create')
  }

  function handleSignOut() {
    signOut()
    navigate('/')
  }

  const activeCampaign = campaigns.find((c) => c.status === 'active')
  const name = accountName(account)
  const initial = name.charAt(0).toUpperCase()
  const stats = registryStats(campaigns)
  const events = chronicle(campaigns)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>

      {/* ── Sticky header ── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 30,
        background: 'var(--bg2)', borderBottom: '1px solid var(--line)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '0 var(--space-xl)', height: '64px',
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ color: 'var(--accent)', fontSize: '1.05rem' }}>◆</span>
          <span style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.86rem', letterSpacing: '0.12em', color: 'var(--ink)' }}>
            THE GRIMOIRE
          </span>
        </div>

        {/* Right cluster: theme + user */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Theme pill */}
          <div style={{ display: 'flex', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: '20px', padding: '3px' }}>
            {(['ember', 'candle'] as Theme[]).map((t) => (
              <button key={t} onClick={() => setTheme(t)} style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.64rem', letterSpacing: '0.06em', textTransform: 'uppercase',
                padding: '5px 12px', border: 'none', borderRadius: '16px', cursor: 'pointer',
                background: theme === t ? 'var(--accent)' : 'transparent',
                color: theme === t ? 'var(--accent-ink)' : 'var(--muted)',
                transition: 'all var(--transition)',
              }}>
                {t === 'ember' ? 'Emberfall' : 'Candlewax'}
              </button>
            ))}
          </div>

          {/* User section */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingLeft: '16px', borderLeft: '1px solid var(--line)' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%',
              background: 'var(--accent)', color: 'var(--accent-ink)',
              display: 'grid', placeItems: 'center',
              fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '0.9rem',
            }}>
              {initial}
            </div>
            {account && (
              <div style={{ lineHeight: 1.15 }}>
                <div style={{ fontFamily: 'var(--font-body)', fontSize: '0.98rem', color: 'var(--ink)' }}>{name}</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--faint)' }}>{account.email}</div>
              </div>
            )}
            <button onClick={handleSignOut} style={{
              marginLeft: '8px',
              fontFamily: 'var(--font-mono)', fontSize: '0.64rem', letterSpacing: '0.1em', textTransform: 'uppercase',
              background: 'transparent', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)',
              padding: '7px 11px', color: 'var(--muted)', cursor: 'pointer',
            }}>
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* ── Main content ── */}
      <div style={{ flex: 1, maxWidth: '1080px', margin: '0 auto', padding: '46px 30px 70px', width: '100%' }}>

        {/* Page heading */}
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '12px' }}>
          Welcome back, {name}
        </div>
        <h1 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: 'clamp(2.2rem, 4.4vw, 3.2rem)', lineHeight: 1.05, margin: '0 0 8px', color: 'var(--ink)' }}>
          The Hall of Heroes
        </h1>
        <p style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '1.2rem', color: 'var(--muted)', margin: '0 0 38px' }}>
          Choose an adventure, resume your run, or forge a new hero.
        </p>

        {state === 'loading' && <LoadingState message="Loading your campaigns…" />}
        {state === 'error' && <ErrorState message={error ?? 'Failed to load campaigns'} onRetry={() => { void onReload() }} />}

        {state === 'ready' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '22px', alignItems: 'start' }}>

            {/* ── Left column ── */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '22px' }}>

              {/* Active campaign card */}
              {activeCampaign ? (
                <div style={{
                  background: 'var(--panel-bg)', border: '1px solid var(--accent)',
                  borderRadius: '6px', padding: '28px', position: 'relative', overflow: 'hidden',
                }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '12px' }}>
                    Active campaign · Ignarok
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '20px', flexWrap: 'wrap' }}>
                    <div>
                      <h2 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.7rem', color: 'var(--panel-ink)', margin: '0 0 6px' }}>
                        {activeCampaignState?.character?.name ?? 'Grey Mountain Expedition'}
                        {activeCampaignState?.world ? ` · ${activeCampaignState.world.location.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}` : ''}
                      </h2>
                      <div style={{ display: 'flex', gap: '18px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--panel-muted)' }}>
                        {activeCampaignState?.character && (
                          <>
                            <span>Stamina <span style={{ color: 'var(--stamina)' }}>{activeCampaignState.character.stamina.current}/{activeCampaignState.character.stamina.initial}</span></span>
                            <span>Luck <span style={{ color: 'var(--luck)' }}>{activeCampaignState.character.luck.current}/{activeCampaignState.character.luck.initial}</span></span>
                            <span>Gold <span style={{ color: 'var(--gold)' }}>{activeCampaignState.character.gold}</span></span>
                          </>
                        )}
                        {!activeCampaignState?.character && (
                          <span>Last played <span style={{ color: 'var(--panel-ink)' }}>{new Date(activeCampaign.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span></span>
                        )}
                      </div>
                    </div>
                    <button onClick={() => { void navigate(`/play/${activeCampaign.id}`) }} style={{
                      fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.92rem', letterSpacing: '0.04em',
                      padding: '14px 28px', background: 'var(--accent)', color: 'var(--accent-ink)',
                      border: 'none', borderRadius: '3px', cursor: 'pointer', whiteSpace: 'nowrap',
                    }}>
                      Continue your run →
                    </button>
                  </div>
                </div>
              ) : campaigns.length === 0 ? (
                <EmptyState message="No adventures yet" hint="Forge a hero to begin your journey into the Grey Mountain" icon="◆" />
              ) : null}

              {/* Adventure modules */}
              <div>
                <div style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1.05rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '14px' }}>
                  Adventure modules
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {ADVENTURE_MODULES.map((mod) => (
                    <div key={mod.title} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px',
                      background: 'var(--panel-bg)',
                      border: `1px solid ${mod.locked ? 'var(--panel-border)' : 'var(--panel-border)'}`,
                      borderRadius: '5px', padding: '18px 20px',
                      opacity: mod.locked ? 0.6 : 1,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <span style={{
                          width: '40px', height: '40px', display: 'grid', placeItems: 'center',
                          background: 'var(--bg2)', border: '1px solid var(--panel-border)', borderRadius: '4px',
                          color: mod.locked ? 'var(--faint)' : 'var(--accent)', fontSize: '1.1rem',
                        }}>
                          {mod.glyph}
                        </span>
                        <div>
                          <div style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1.1rem', color: 'var(--panel-ink)' }}>
                            {mod.title}
                          </div>
                          <div style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '1rem', color: 'var(--panel-muted)', marginTop: '2px' }}>
                            {mod.desc}
                          </div>
                        </div>
                      </div>
                      {mod.locked ? (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--faint)', padding: '9px 14px', border: '1px solid var(--line)', borderRadius: '3px' }}>
                          Locked
                        </span>
                      ) : (
                        <button onClick={() => { void handleCreate() }} style={{
                          fontFamily: 'var(--font-mono)', fontSize: '0.66rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                          padding: '9px 18px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: '3px', cursor: 'pointer',
                        }}>
                          Play →
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Forge / Graveyard */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <button onClick={() => { void handleCreate() }} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
                  padding: '18px', background: 'transparent',
                  border: '1px dashed var(--line)', borderRadius: '5px',
                  color: 'var(--accent)', fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1rem', letterSpacing: '0.04em', cursor: 'pointer',
                }}>
                  ⚔ Forge a new hero
                </button>
                <button onClick={() => { void navigate('/graveyard') }} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
                  padding: '18px', background: 'transparent',
                  border: '1px dashed var(--line)', borderRadius: '5px',
                  color: 'var(--muted)', fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1rem', letterSpacing: '0.04em', cursor: 'pointer',
                }}
                onMouseOver={(e) => { e.currentTarget.style.borderColor = 'var(--muted)' }}
                onMouseOut={(e) => { e.currentTarget.style.borderColor = 'var(--line)' }}
                >
                  ⚰ Visit the Graveyard
                </button>
              </div>
            </div>

            {/* ── Right sidebar ── */}
            <aside style={{ background: 'var(--bg2)', border: '1px solid var(--line)', borderRadius: '6px', padding: '24px' }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: '16px' }}>
                Account registry
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '22px' }}>
                {stats.map((s) => (
                  <div key={s.label} style={{ background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: '4px', padding: '14px', textAlign: 'center' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 600, color: s.color }}>
                      {s.value}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: '4px' }}>
                      {s.label}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: '12px' }}>
                Recent chronicle
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '11px' }}>
                {events.map((entry, i) => (
                  <div key={i} style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', fontFamily: 'var(--font-body)', fontSize: '1rem', color: 'var(--muted)', lineHeight: 1.4 }}>
                    <span style={{ color: 'var(--accent)', fontSize: '0.7rem', marginTop: '5px', flexShrink: 0 }}>◆</span>
                    <span>{entry}</span>
                  </div>
                ))}
              </div>

              {/* All campaigns list */}
              {campaigns.length > 0 && (
                <div style={{ marginTop: '22px', borderTop: '1px solid var(--line)', paddingTop: '16px' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: '10px' }}>
                    All campaigns
                  </div>
                  {campaigns.map((c) => (
                    <div key={c.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: c.status === 'active' ? 'var(--accent)' : 'var(--faint)' }}>
                        {c.id.slice(0, 8)}… · {c.status}
                      </span>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button onClick={() => { void navigate(`/play/${c.id}`) }} style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: '0.64rem', cursor: 'pointer', padding: '2px 6px' }}>
                          Resume
                        </button>
                        <button onClick={() => { void onDelete(c.id) }} style={{ background: 'transparent', border: 'none', color: 'var(--faint)', fontFamily: 'var(--font-mono)', fontSize: '0.64rem', cursor: 'pointer', padding: '2px 6px' }}>
                          ✕
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
    </div>
  )
}
