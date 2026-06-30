import { useState, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'

type Theme = 'ember' | 'candle'
type PlayTab = 'story' | 'map' | 'backpack' | 'saves'
function getTheme(): Theme { return (localStorage.getItem('gb_theme') as Theme | null) ?? 'ember' }
function applyTheme(t: Theme) { document.documentElement.classList.toggle('theme-candle', t === 'candle'); localStorage.setItem('gb_theme', t) }
function fmtLocation(loc: string): string { return loc.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) }

import { useGame } from '../hooks/useGame'
import { createCharacter } from '../api'
import NarratorPanel from '../components/NarratorPanel'
import ChoicesPanel from '../components/ChoicesPanel'
import CharacterSheetPanel from '../components/CharacterSheet'
import InventoryPanel from '../components/Inventory'
import MapPanelComp from '../components/MapPanel'
import SessionConflict from '../components/SessionConflict'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'

export default function PlayPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const campaignId = id ?? ''

  const {
    loadState,
    actionState,
    campaign,
    error,
    sessionConflict,
    onChoose,
    onFreeText,
    onTakeover,
    onReload,
    onSave,
  } = useGame(campaignId)

  const [creatingCharacter, setCreatingCharacter] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [theme, setTheme] = useState<Theme>(getTheme)
  const [tab, setTab] = useState<PlayTab>('story')

  useEffect(() => { applyTheme(theme) }, [theme])

  const handleCreateCharacter = useCallback(async () => {
    setCreatingCharacter(true)
    setCreateError(null)
    try {
      await createCharacter(campaignId)
      await onReload()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create character')
    } finally {
      setCreatingCharacter(false)
    }
  }, [campaignId, onReload])

  // Capture before any TypeScript narrowing via early returns
  const isDataLoading = loadState === 'loading'

  if (isDataLoading) {
    return (
      <div style={fullPageCenter}>
        <LoadingState message="Loading your adventure…" size="lg" />
      </div>
    )
  }

  if (loadState === 'error') {
    return (
      <div style={fullPageCenter}>
        <ErrorState
          message={error ?? 'Failed to load campaign'}
          onRetry={() => { void onReload() }}
        />
      </div>
    )
  }

  const scene = campaign?.current_scene
  const character = campaign?.character
  const world = campaign?.world
  const isEnded = campaign?.status === 'ended'
  const isTerminal = isEnded || (scene?.choices.length === 0 && !!scene?.narrative)
  const actionPending = actionState === 'pending'

  // No character yet — offer character creation.
  if (!character && !creatingCharacter && loadState === 'ready') {
    return (
      <div style={fullPageCenter}>
        <div
          style={{
            background: 'var(--panel-bg)',
            border: '1px solid var(--panel-border)',
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
            style={{
              fontFamily: 'var(--font-title)',
              fontSize: '3rem',
              color: 'var(--accent)',
            }}
            aria-hidden="true"
          >
            ◆
          </span>
          <h1
            style={{
              fontFamily: 'var(--font-title)',
              color: 'var(--accent)',
              fontSize: '1.25rem',
              letterSpacing: '0.06em',
              margin: 0,
            }}
          >
            Create Your Hero
          </h1>
          <p
            style={{
              fontFamily: 'var(--font-body)',
              color: 'var(--muted)',
              fontSize: '1rem',
              lineHeight: 1.65,
              margin: 0,
            }}
          >
            The engine will roll your attributes:
            SKILL (1d6+6), STAMINA (2d6+12), LUCK (1d6+6).
            No numbers are invented — every stat comes from the engine.
          </p>
          {createError && (
            <p
              role="alert"
              style={{ fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: '#c0392b', margin: 0 }}
            >
              {createError}
            </p>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            <button
              onClick={() => { void handleCreateCharacter() }}
              disabled={creatingCharacter}
              style={{
                background: 'var(--accent)',
                color: 'var(--accent-ink)',
                border: 'none',
                borderRadius: 'var(--radius-sm)',
                padding: 'var(--space-md)',
                fontFamily: 'var(--font-title)',
                fontSize: '0.9rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                cursor: creatingCharacter ? 'wait' : 'pointer',
                opacity: creatingCharacter ? 0.6 : 1,
              }}
              aria-label="Roll character attributes and start adventure"
            >
              {creatingCharacter ? 'Rolling attributes…' : 'Roll & Begin'}
            </button>
            <button
              onClick={() => { void navigate('/dashboard') }}
              style={{
                background: 'transparent',
                color: 'var(--muted)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-sm)',
                padding: 'var(--space-sm)',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.7rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
            >
              ← Back to Dashboard
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Session conflict overlay */}
      {sessionConflict && (
        <SessionConflict
          onTakeover={() => { void onTakeover() }}
          loading={actionPending}
        />
      )}

      {/* Page shell */}
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
            position: 'sticky', top: 0, zIndex: 50,
            background: 'var(--bg2)', borderBottom: '1px solid var(--line)',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '0 22px', height: '62px',
          }}
        >
          {/* Left: back + brand + location */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px', minWidth: '220px' }}>
            <button
              onClick={() => { void navigate('/dashboard') }}
              style={{ background: 'transparent', color: 'var(--muted)', border: 'none', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer', padding: 0 }}
            >
              ← Dashboard
            </button>
            {world && (
              <div style={{ borderLeft: '1px solid var(--line)', paddingLeft: '14px' }}>
                <div style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.86rem', letterSpacing: '0.08em', color: 'var(--ink)' }}>FANTASY GAMEBOOK</div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', letterSpacing: '0.06em', color: 'var(--faint)' }}>
                  {fmtLocation(world.location)}{typeof world.flags['turn'] === 'number' ? ` · Turn ${world.flags['turn'] as number}` : ''}
                </div>
              </div>
            )}
          </div>

          {/* Center: tab nav */}
          <nav style={{ display: 'flex', gap: '4px', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: '4px', padding: '4px' }}>
            {(['story', 'map', 'backpack', 'saves'] as PlayTab[]).map((t) => (
              <button key={t} onClick={() => setTab(t)} style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.68rem', letterSpacing: '0.06em', textTransform: 'capitalize',
                padding: '6px 14px', border: 'none', borderRadius: '3px', cursor: 'pointer',
                background: tab === t ? 'var(--panel-bg)' : 'transparent',
                color: tab === t ? 'var(--accent)' : 'var(--muted)',
                borderBottom: tab === t ? '1px solid var(--accent)' : '1px solid transparent',
                transition: 'all var(--transition)',
              }}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </nav>

          {/* Right: theme + stats + save */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: '220px', justifyContent: 'flex-end' }}>
            <div style={{ display: 'flex', background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: '20px', padding: '3px' }}>
              {(['ember', 'candle'] as Theme[]).map((t) => (
                <button key={t} onClick={() => setTheme(t)} style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.6rem', letterSpacing: '0.06em', textTransform: 'uppercase',
                  padding: '4px 10px', border: 'none', borderRadius: '16px', cursor: 'pointer',
                  background: theme === t ? 'var(--accent)' : 'transparent',
                  color: theme === t ? 'var(--accent-ink)' : 'var(--muted)',
                  transition: 'all var(--transition)',
                }}>
                  {t === 'ember' ? 'Emberfall' : 'Candlewax'}
                </button>
              ))}
            </div>
            {character && (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--muted)', letterSpacing: '0.05em' }}
                aria-label={`Skill: ${character.skill.current.toString()}, Stamina: ${character.stamina.current.toString()}, Luck: ${character.luck.current.toString()}`}>
                SK {character.skill.current} · ST {character.stamina.current} · LK {character.luck.current}
              </span>
            )}
            <button onClick={() => { void onSave() }} disabled={actionPending || isEnded} title="Save checkpoint"
              style={{ background: 'transparent', color: 'var(--faint)', border: '1px solid var(--line)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontFamily: 'var(--font-mono)', fontSize: '0.65rem', letterSpacing: '0.06em', textTransform: 'uppercase', cursor: 'pointer' }}
              aria-label="Save checkpoint">
              Save
            </button>
          </div>
        </header>

        {/* ── Play area ── */}
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 312px', gap: 0, minHeight: 0 }}>

          {/* ── Main content (tab-switched) ── */}
          <main style={{ padding: '44px 36px 80px', overflowY: 'auto' }}>
            <div style={{ maxWidth: '680px', margin: '0 auto' }}>

              {/* Story tab */}
              {tab === 'story' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
                  {/* § Scene header */}
                  {world && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '26px' }}>
                      <span style={{ fontFamily: 'var(--font-title)', fontSize: '1.4rem', color: 'var(--accent)' }}>§</span>
                      <span style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1.05rem', letterSpacing: '0.06em', color: 'var(--ink)' }}>
                        {fmtLocation(world.location)}
                      </span>
                      <span style={{ flex: 1, height: '1px', background: 'var(--line)' }} />
                      {typeof world.flags['turn'] === 'number' && (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', letterSpacing: '0.1em', color: 'var(--faint)' }}>
                          TURN {world.flags['turn'] as number}
                        </span>
                      )}
                    </div>
                  )}

                  <NarratorPanel narrative={scene?.narrative} loading={isDataLoading || creatingCharacter} isTerminal={isTerminal} />

                  {error && actionState === 'error' && (
                    <div role="alert" style={{ fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: '#c0392b', padding: 'var(--space-sm) var(--space-md)', background: 'rgba(192,57,43,0.1)', border: '1px solid rgba(192,57,43,0.3)', borderRadius: 'var(--radius-sm)' }}>
                      {error}
                    </div>
                  )}

                  <ChoicesPanel choices={scene?.choices ?? []} loading={isDataLoading} actionPending={actionPending}
                    isEnded={isEnded}
                    onChoose={(id) => { void onChoose(id) }} onFreeText={(text) => { void onFreeText(text) }} />

                  {isEnded && (
                    <div style={{ textAlign: 'center', paddingTop: 'var(--space-md)' }}>
                      <button onClick={() => { void navigate('/dashboard') }} style={{ background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: 'var(--radius-sm)', padding: 'var(--space-sm) var(--space-xl)', fontFamily: 'var(--font-title)', fontSize: '0.85rem', letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer' }}>
                        Return to Dashboard
                      </button>
                    </div>
                  )}

                  {/* Engine note */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--faint)', letterSpacing: '0.04em', marginTop: 'var(--space-sm)' }}>
                    <span style={{ display: 'inline-grid', placeItems: 'center', width: '18px', height: '18px', border: '1px solid var(--line)', borderRadius: '3px', color: 'var(--accent)' }}>⚂</span>
                    Numbers come from the engine. The narrator only describes what the dice decide.
                  </div>
                </div>
              )}

              {/* Map tab */}
              {tab === 'map' && (
                <div>
                  <h2 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.7rem', color: 'var(--ink)', margin: '0 0 6px' }}>The Grey Mountain</h2>
                  <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.05rem', color: 'var(--muted)', margin: '0 0 34px' }}>
                    {world ? `${world.visited.length} zone${world.visited.length !== 1 ? 's' : ''} visited.` : 'No world data.'}
                  </p>
                  <MapPanelComp world={world} loading={isDataLoading} />
                </div>
              )}

              {/* Backpack tab */}
              {tab === 'backpack' && (
                <div>
                  <h2 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.7rem', color: 'var(--ink)', margin: '0 0 6px' }}>Backpack</h2>
                  <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.05rem', color: 'var(--muted)', margin: '0 0 26px' }}>
                    Everything {character?.name ?? 'your hero'} carries into the dark.
                  </p>
                  {character && (
                    <div style={{ display: 'flex', gap: '12px', marginBottom: '26px' }}>
                      <div style={{ flex: 1, background: 'var(--panel-bg)', border: '1px solid var(--panel-border)', borderRadius: '4px', padding: '16px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontFamily: 'var(--font-title)', fontSize: '0.86rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--gold)' }}>Gold</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 600, color: 'var(--panel-ink)' }}>{character.gold}</span>
                      </div>
                      <div style={{ flex: 1, background: 'var(--panel-bg)', border: '1px solid var(--panel-border)', borderRadius: '4px', padding: '16px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontFamily: 'var(--font-title)', fontSize: '0.86rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--stamina)' }}>Provisions</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 600, color: 'var(--panel-ink)' }}>{character.provisions}</span>
                      </div>
                    </div>
                  )}
                  <InventoryPanel character={character} loading={isDataLoading || creatingCharacter} />
                </div>
              )}

              {/* Saves tab */}
              {tab === 'saves' && (
                <div>
                  <h2 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.7rem', color: 'var(--ink)', margin: '0 0 6px' }}>Checkpoints</h2>
                  <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.05rem', color: 'var(--muted)', margin: '0 0 26px' }}>
                    Progress is persisted by the engine — atomic, never half-written.
                  </p>
                  <button onClick={() => { void onSave() }} disabled={actionPending || isEnded} style={{
                    fontFamily: 'var(--font-mono)', fontSize: '0.78rem', letterSpacing: '0.14em', textTransform: 'uppercase',
                    padding: '13px 24px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: '3px', cursor: actionPending || isEnded ? 'not-allowed' : 'pointer', opacity: actionPending || isEnded ? 0.6 : 1,
                  }}>
                    Save checkpoint now
                  </button>
                </div>
              )}
            </div>
          </main>

          {/* ── Right sidebar: Character Sheet only (always visible) ── */}
          <aside style={{ borderLeft: '1px solid var(--line)', background: 'var(--bg2)', padding: '26px 22px', overflowY: 'auto' }}>
            <CharacterSheetPanel character={character} loading={isDataLoading || creatingCharacter} />
          </aside>
        </div>
      </div>
    </>
  )
}

const fullPageCenter: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg)',
  padding: 'var(--space-xl)',
}
