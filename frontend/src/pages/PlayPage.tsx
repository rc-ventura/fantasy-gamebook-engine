/**
 * PlayPage — the full play loop.
 *
 * Renders:
 *   - NarratorPanel  (scene narration)
 *   - ChoicesPanel   (numbered choices + free text)
 *   - CharacterSheet (sidebar — real engine state)
 *   - Inventory      (sidebar — real engine state)
 *   - MapPanel       (sidebar — real engine state)
 *   - CombatPanel    (shown when campaign.combat.active is true)
 *   - SessionConflict modal (when 409 not_session_holder)
 *
 * All values shown come from the API — nothing is fabricated client-side.
 * The play loop wires: create/resume → take turn → combat → end-state.
 */

import { useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGame } from '../hooks/useGame'
import { createCharacter } from '../api'
import NarratorPanel from '../components/NarratorPanel'
import ChoicesPanel from '../components/ChoicesPanel'
import CharacterSheetPanel from '../components/CharacterSheet'
import InventoryPanel from '../components/Inventory'
import MapPanelComp from '../components/MapPanel'
import CombatPanel from '../components/CombatPanel'
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
    onCombatRound,
    onFlee,
    onTakeover,
    onReload,
    onSave,
  } = useGame(campaignId)

  const [creatingCharacter, setCreatingCharacter] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

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
  const combat = campaign?.combat
  const isEnded = campaign?.status === 'ended'
  const inCombat = combat?.active === true
  const isTerminal = isEnded || (!inCombat && scene?.choices.length === 0 && !!scene?.narrative)
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
            position: 'sticky',
            top: 0,
            zIndex: 50,
            background: 'var(--bg2)',
            borderBottom: '1px solid var(--line)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: 'var(--space-sm) var(--space-xl)',
          }}
        >
          <button
            onClick={() => { void navigate('/dashboard') }}
            style={{
              background: 'transparent',
              color: 'var(--muted)',
              border: 'none',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.7rem',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            ← Dashboard
          </button>

          <span
            style={{
              fontFamily: 'var(--font-title)',
              color: 'var(--accent)',
              fontSize: '0.85rem',
              letterSpacing: '0.1em',
            }}
          >
            THE GRIMOIRE
          </span>

          <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
            {character && (
              <>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.65rem',
                    color: 'var(--muted)',
                    letterSpacing: '0.05em',
                  }}
                  aria-label={`Skill: ${character.skill.current.toString()}, Stamina: ${character.stamina.current.toString()}, Luck: ${character.luck.current.toString()}`}
                >
                  SK {character.skill.current} · ST {character.stamina.current} · LK {character.luck.current}
                </span>
              </>
            )}
            <button
              onClick={() => { void onSave() }}
              disabled={actionPending || isEnded}
              title="Save checkpoint"
              style={{
                background: 'transparent',
                color: 'var(--faint)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 10px',
                fontFamily: 'var(--font-mono)',
                fontSize: '0.65rem',
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                cursor: 'pointer',
              }}
              aria-label="Save checkpoint"
            >
              Save
            </button>
          </div>
        </header>

        {/* ── Play area ── */}
        <main
          style={{
            flex: 1,
            display: 'grid',
            gridTemplateColumns: '1fr 280px',
            gridTemplateRows: 'auto',
            gap: 'var(--space-lg)',
            padding: 'var(--space-xl)',
            maxWidth: '1100px',
            margin: '0 auto',
            width: '100%',
            alignItems: 'start',
          }}
        >
          {/* ── Left column: narrator + choices + combat ── */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-lg)',
            }}
          >
            <NarratorPanel
              narrative={scene?.narrative}
              loading={isDataLoading || creatingCharacter}
              isTerminal={isTerminal}
            />

            {/* Inline action error */}
            {error && actionState === 'error' && (
              <div
                role="alert"
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '0.9rem',
                  color: '#c0392b',
                  padding: 'var(--space-sm) var(--space-md)',
                  background: 'rgba(192,57,43,0.1)',
                  border: '1px solid rgba(192,57,43,0.3)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {error}
              </div>
            )}

            {inCombat ? (
              <CombatPanel
                combat={combat ?? null}
                loading={isDataLoading}
                actionPending={actionPending}
                onCombatRound={(testLuck) => { void onCombatRound(testLuck) }}
                onFlee={() => { void onFlee() }}
              />
            ) : (
              <ChoicesPanel
                choices={scene?.choices ?? []}
                loading={isDataLoading}
                actionPending={actionPending}
                isEnded={isEnded}
                inCombat={inCombat}
                onChoose={(id) => { void onChoose(id) }}
                onFreeText={(text) => { void onFreeText(text) }}
              />
            )}

            {isEnded && (
              <div style={{ textAlign: 'center', paddingTop: 'var(--space-md)' }}>
                <button
                  onClick={() => { void navigate('/dashboard') }}
                  style={{
                    background: 'var(--accent)',
                    color: 'var(--accent-ink)',
                    border: 'none',
                    borderRadius: 'var(--radius-sm)',
                    padding: 'var(--space-sm) var(--space-xl)',
                    fontFamily: 'var(--font-title)',
                    fontSize: '0.85rem',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                  }}
                >
                  Return to Dashboard
                </button>
              </div>
            )}
          </div>

          {/* ── Right column: sidebar panels ── */}
          <aside
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-md)',
              position: 'sticky',
              top: '60px',
            }}
          >
            <CharacterSheetPanel
              character={character}
              loading={isDataLoading || creatingCharacter}
            />
            <InventoryPanel
              character={character}
              loading={isDataLoading || creatingCharacter}
            />
            <MapPanelComp
              world={world}
              loading={isDataLoading}
            />
          </aside>
        </main>
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
