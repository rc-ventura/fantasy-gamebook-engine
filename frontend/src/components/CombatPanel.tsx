/**
 * CombatPanel — renders engine-computed combat state.
 *
 * ALL combat values (attack strengths, damage, luck results) come from the API.
 * The frontend never rolls dice or computes combat math client-side.
 * Offers "Resolve Round" (with optional luck test) and "Flee" (if allowed).
 *
 * FR-005: surfaces combat encounters with optional luck tests and a clear final outcome.
 * FR-007/008: every value reflects real engine state.
 */

import type { CombatState } from '../types'
import LoadingState from './LoadingState'
import EmptyState from './EmptyState'

interface CombatPanelProps {
  combat: CombatState | null | undefined
  loading?: boolean
  actionPending?: boolean
  onCombatRound: (testLuck: boolean) => void | Promise<void>
  onFlee: () => void | Promise<void>
}

export default function CombatPanel({
  combat,
  loading = false,
  actionPending = false,
  onCombatRound,
  onFlee,
}: CombatPanelProps) {
  if (loading) return <LoadingState message="Combat loading…" size="sm" />

  if (!combat || !combat.active) {
    if (combat?.outcome) {
      const outcomeLabel: Record<'victory' | 'defeat' | 'fled', string> = {
        victory: '⚔ Victory!',
        defeat: '☠ Defeated',
        fled: '💨 Fled',
      }
      const outcomeColour: Record<'victory' | 'defeat' | 'fled', string> = {
        victory: 'var(--accent)',
        defeat: '#c0392b',
        fled: 'var(--muted)',
      }
      return (
        <div
          style={{
            background: 'var(--panel-bg)',
            border: '1px solid var(--panel-border)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-lg)',
            textAlign: 'center',
          }}
          role="status"
          aria-label={`Combat ended: ${combat.outcome}`}
        >
          <span
            style={{
              fontFamily: 'var(--font-title)',
              fontSize: '1.1rem',
              color: outcomeColour[combat.outcome],
              letterSpacing: '0.05em',
            }}
          >
            {outcomeLabel[combat.outcome]}
          </span>
        </div>
      )
    }
    return (
      <EmptyState
        message="No combat in progress"
        hint="Combat begins when the narrator triggers an encounter"
        icon="⚔"
      />
    )
  }

  const hero = combat.participants[0]
  const enemy = combat.participants[1]
  const latestRound = combat.rounds.length > 0 ? combat.rounds[combat.rounds.length - 1] : null

  function handleRound(testLuck: boolean) {
    void Promise.resolve(onCombatRound(testLuck))
  }

  function handleFlee() {
    void Promise.resolve(onFlee())
  }

  return (
    <section
      aria-label="Combat"
      style={{
        background: 'var(--panel-bg)',
        border: '1px solid var(--accent)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-md)',
      }}
    >
      <h2
        style={{
          fontFamily: 'var(--font-title)',
          color: 'var(--accent)',
          fontSize: '0.9rem',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          margin: 0,
          borderBottom: '1px solid var(--line)',
          paddingBottom: 'var(--space-sm)',
        }}
      >
        ⚔ Combat
      </h2>

      {/* Combatants */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto 1fr',
          gap: 'var(--space-sm)',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <span
            style={{ fontFamily: 'var(--font-title)', fontSize: '0.8rem', color: 'var(--accent)', letterSpacing: '0.05em' }}
          >
            {hero?.name ?? 'Hero'}
          </span>
          <span
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--muted)' }}
            aria-label={`Hero stamina: ${hero?.stamina.toString() ?? '?'}`}
          >
            STAMINA {hero?.stamina ?? '?'}
          </span>
        </div>

        <span
          style={{ fontFamily: 'var(--font-title)', fontSize: '1rem', color: 'var(--faint)' }}
          aria-hidden="true"
        >
          vs
        </span>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', textAlign: 'right' }}>
          <span
            style={{ fontFamily: 'var(--font-title)', fontSize: '0.8rem', color: 'var(--muted)', letterSpacing: '0.05em' }}
          >
            {enemy?.name ?? 'Enemy'}
          </span>
          <span
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--muted)' }}
            aria-label={`Enemy stamina: ${enemy?.stamina.toString() ?? '?'}`}
          >
            STAMINA {enemy?.stamina ?? '?'}
          </span>
        </div>
      </div>

      {/* Latest round result — engine-produced numbers */}
      {latestRound && (
        <div
          style={{
            background: 'var(--bg)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-sm)',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
          aria-label="Last round result"
        >
          <span
            style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--faint)' }}
          >
            Round {combat.rounds.length}
          </span>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-xs)' }}>
            <span
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--ink)' }}
              aria-label={`Hero attack strength: ${latestRound.hero_attack.toString()}`}
            >
              Hero AS: {latestRound.hero_attack}
            </span>
            <span
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--muted)' }}
              aria-label={`Enemy attack strength: ${latestRound.enemy_attack.toString()}`}
            >
              Enemy AS: {latestRound.enemy_attack}
            </span>
            {latestRound.hero_damage > 0 && (
              <span
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--accent)' }}
                aria-label={`Enemy took ${latestRound.hero_damage.toString()} damage`}
              >
                Enemy −{latestRound.hero_damage} ST
              </span>
            )}
            {latestRound.enemy_damage > 0 && (
              <span
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: '#c0392b' }}
                aria-label={`Hero took ${latestRound.enemy_damage.toString()} damage`}
              >
                Hero −{latestRound.enemy_damage} ST
              </span>
            )}
            {latestRound.luck_used === true && (
              <span
                style={{
                  gridColumn: '1 / -1',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.7rem',
                  color: latestRound.luck_result === 'lucky' ? 'var(--accent)' : 'var(--muted)',
                }}
                aria-label={`Luck test: ${latestRound.luck_result ?? 'unknown'}`}
              >
                Luck: {latestRound.luck_result === 'lucky' ? '★ Lucky' : '✦ Unlucky'}
              </span>
            )}
          </div>
        </div>
      )}

      {combat.rounds.length > 0 && (
        <span
          style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', letterSpacing: '0.08em', color: 'var(--faint)' }}
          aria-label={`Rounds fought: ${combat.rounds.length.toString()}`}
        >
          {combat.rounds.length} round{combat.rounds.length === 1 ? '' : 's'} fought
        </span>
      )}

      {/* Combat actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
        <button
          onClick={() => handleRound(false)}
          disabled={actionPending}
          aria-label="Resolve combat round"
          style={{
            background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none',
            borderRadius: 'var(--radius-sm)', padding: 'var(--space-sm) var(--space-md)',
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', letterSpacing: '0.08em',
            textTransform: 'uppercase', cursor: actionPending ? 'wait' : 'pointer',
            opacity: actionPending ? 0.6 : 1, transition: 'opacity var(--transition)',
          }}
        >
          {actionPending ? 'Resolving…' : 'Resolve Round'}
        </button>

        <button
          onClick={() => handleRound(true)}
          disabled={actionPending}
          aria-label="Resolve round and test luck"
          style={{
            background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-sm)', padding: 'var(--space-sm) var(--space-md)',
            fontFamily: 'var(--font-mono)', fontSize: '0.75rem', letterSpacing: '0.08em',
            textTransform: 'uppercase', cursor: actionPending ? 'wait' : 'pointer',
            opacity: actionPending ? 0.6 : 1, transition: 'opacity var(--transition)',
          }}
        >
          Resolve + Test Luck
        </button>

        {combat.flee_allowed && (
          <button
            onClick={handleFlee}
            disabled={actionPending}
            aria-label="Attempt to flee combat"
            style={{
              background: 'transparent', color: 'var(--muted)', border: '1px solid var(--line)',
              borderRadius: 'var(--radius-sm)', padding: 'var(--space-sm) var(--space-md)',
              fontFamily: 'var(--font-mono)', fontSize: '0.75rem', letterSpacing: '0.08em',
              textTransform: 'uppercase', cursor: actionPending ? 'wait' : 'pointer',
              opacity: actionPending ? 0.6 : 1, transition: 'opacity var(--transition)',
            }}
          >
            Flee (costs 2 STAMINA)
          </button>
        )}
      </div>
    </section>
  )
}
