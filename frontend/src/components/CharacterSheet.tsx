/**
 * CharacterSheet — renders real engine state for the hero.
 *
 * ALL values (skill, stamina, luck, gold, provisions) come from the API.
 * Nothing is computed client-side — the panel is a pure renderer of engine state.
 *
 * FR-007/008: every value shown reflects real engine state, never fabricated.
 */

import type { CharacterSheet as CharacterSheetType } from '../types'
import LoadingState from './LoadingState'
import EmptyState from './EmptyState'

interface CharacterSheetProps {
  character: CharacterSheetType | null | undefined
  loading?: boolean
}

interface AttributeRowProps {
  label: string
  current: number
  initial: number
  /** Colour hint: 'normal' | 'warning' | 'critical' based on current/initial ratio. */
  variant?: 'normal' | 'warning' | 'critical'
}

function AttributeRow({ label, current, initial, variant = 'normal' }: AttributeRowProps) {
  const colours: Record<'normal' | 'warning' | 'critical', string> = {
    normal: 'var(--ink)',
    warning: '#e8a33f',
    critical: '#c0392b',
  }
  const pct = initial > 0 ? (current / initial) * 100 : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            color: 'var(--muted)',
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.9rem',
            color: colours[variant],
            fontWeight: 'bold',
          }}
          aria-label={`${label}: ${current.toString()} of ${initial.toString()}`}
        >
          {current}/{initial}
        </span>
      </div>
      {/* Progress bar — visual only, never the source of truth */}
      <div
        style={{
          height: '3px',
          background: 'var(--line)',
          borderRadius: '2px',
          overflow: 'hidden',
        }}
        aria-hidden="true"
      >
        <div
          style={{
            height: '100%',
            width: `${Math.max(0, Math.min(100, pct)).toFixed(1)}%`,
            background: colours[variant],
            borderRadius: '2px',
            transition: 'width 0.3s ease',
          }}
        />
      </div>
    </div>
  )
}

function statVariant(current: number, initial: number): 'normal' | 'warning' | 'critical' {
  if (initial === 0) return 'normal'
  const ratio = current / initial
  if (ratio <= 0.25) return 'critical'
  if (ratio <= 0.5) return 'warning'
  return 'normal'
}

export default function CharacterSheet({ character, loading = false }: CharacterSheetProps) {
  if (loading) return <LoadingState message="Reading character sheet…" size="sm" />

  if (!character) {
    return (
      <EmptyState
        message="No character yet"
        hint="Create your hero to see their stats"
        icon="⚔"
      />
    )
  }

  return (
    <aside
      aria-label="Character sheet"
      style={{
        background: 'var(--panel-bg)',
        border: '1px solid var(--panel-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-md)',
      }}
    >
      {/* Header */}
      <div style={{ borderBottom: '1px solid var(--line)', paddingBottom: 'var(--space-sm)' }}>
        <h2
          style={{
            fontFamily: 'var(--font-title)',
            color: 'var(--accent)',
            fontSize: '0.95rem',
            letterSpacing: '0.08em',
            margin: 0,
          }}
        >
          {character.name ?? 'The Hero'}
        </h2>
        {!character.alive && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: '#c0392b',
            }}
          >
            — Fallen —
          </span>
        )}
      </div>

      {/* Core attributes — engine-produced values only */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
        <AttributeRow
          label="Skill"
          current={character.skill.current}
          initial={character.skill.initial}
          variant={statVariant(character.skill.current, character.skill.initial)}
        />
        <AttributeRow
          label="Stamina"
          current={character.stamina.current}
          initial={character.stamina.initial}
          variant={statVariant(character.stamina.current, character.stamina.initial)}
        />
        <AttributeRow
          label="Luck"
          current={character.luck.current}
          initial={character.luck.initial}
          variant={statVariant(character.luck.current, character.luck.initial)}
        />
      </div>

      {/* Resource stats */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 'var(--space-sm)',
          borderTop: '1px solid var(--line)',
          paddingTop: 'var(--space-sm)',
        }}
      >
        {[
          { label: 'Gold', value: character.gold },
          { label: 'Provisions', value: character.provisions },
        ].map(({ label, value }) => (
          <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.65rem',
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: 'var(--muted)',
              }}
            >
              {label}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '1rem',
                color: 'var(--panel-ink)',
                fontWeight: 'bold',
              }}
              aria-label={`${label}: ${value.toString()}`}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* Conditions */}
      {character.conditions.length > 0 && (
        <div
          style={{
            borderTop: '1px solid var(--line)',
            paddingTop: 'var(--space-sm)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-xs)',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--muted)',
            }}
          >
            Conditions
          </span>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {character.conditions.map((c) => (
              <li
                key={c}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.65rem',
                  color: 'var(--muted)',
                  background: 'var(--line)',
                  borderRadius: '2px',
                  padding: '1px 6px',
                }}
              >
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  )
}
