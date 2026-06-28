/**
 * MapPanel — renders world state (current location + visited zones).
 *
 * ALL location data comes from the API WorldState.
 * The frontend never invents locations or movement.
 *
 * FR-007/008: every value shown reflects real engine state.
 */

import type { WorldState } from '../types'
import LoadingState from './LoadingState'
import EmptyState from './EmptyState'

interface MapPanelProps {
  world: WorldState | null | undefined
  loading?: boolean
}

export default function MapPanel({ world, loading = false }: MapPanelProps) {
  if (loading) return <LoadingState message="Reading the map…" size="sm" />

  if (!world) {
    return (
      <EmptyState
        message="The world is uncharted"
        hint="Begin your adventure to reveal the map"
        icon="🗺"
      />
    )
  }

  function formatLocation(loc: string): string {
    return loc.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }

  return (
    <section
      aria-label="World map"
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
      <h2
        style={{
          fontFamily: 'var(--font-title)',
          color: 'var(--accent)',
          fontSize: '0.9rem',
          letterSpacing: '0.08em',
          margin: 0,
          borderBottom: '1px solid var(--line)',
          paddingBottom: 'var(--space-sm)',
        }}
      >
        World
      </h2>

      {/* Current location */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.65rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            color: 'var(--muted)',
          }}
        >
          Current Location
        </span>
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '1rem',
            color: 'var(--accent)',
          }}
          aria-label={`Current location: ${formatLocation(world.location)}`}
        >
          {formatLocation(world.location)}
        </span>
      </div>

      {/* Visited zones */}
      {world.visited.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--muted)',
            }}
          >
            Visited
          </span>
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: '2px',
            }}
            aria-label="Visited locations"
          >
            {world.visited.map((loc) => (
              <li
                key={loc}
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '0.85rem',
                  color: loc === world.location ? 'var(--accent)' : 'var(--panel-muted)',
                  paddingLeft: 'var(--space-sm)',
                  borderLeft: loc === world.location
                    ? '2px solid var(--accent)'
                    : '2px solid var(--line)',
                }}
                aria-current={loc === world.location ? 'location' : undefined}
              >
                {formatLocation(loc)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Active world flags (non-internal ones only) */}
      {Object.keys(world.flags).length > 0 && (
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
            World Flags
          </span>
          <ul
            style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: '4px' }}
            aria-label="World flags"
          >
            {Object.entries(world.flags).map(([key, val]) => (
              <li
                key={key}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6rem',
                  color: 'var(--muted)',
                  background: 'var(--line)',
                  borderRadius: '2px',
                  padding: '1px 6px',
                }}
                aria-label={`${key}: ${String(val)}`}
              >
                {key.replace(/_/g, '-')}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
