/**
 * Inventory / Backpack panel — renders real engine state.
 *
 * ALL inventory items come from the API CharacterSheet.inventory.
 * The frontend never adds, removes, or fabricates items client-side.
 *
 * FR-007/008: every value shown reflects real engine state.
 */

import type { CharacterSheet } from '../types'
import LoadingState from './LoadingState'
import EmptyState from './EmptyState'

interface InventoryProps {
  character: CharacterSheet | null | undefined
  loading?: boolean
}

export default function Inventory({ character, loading = false }: InventoryProps) {
  if (loading) return <LoadingState message="Loading backpack…" size="sm" />

  if (!character) {
    return (
      <EmptyState
        message="No character yet"
        hint="Create your hero first"
        icon="🎒"
      />
    )
  }

  return (
    <section
      aria-label="Backpack / Inventory"
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
        Backpack
      </h2>

      {character.inventory.length === 0 ? (
        <EmptyState
          message="Your backpack is empty"
          hint="Items found during the adventure appear here"
          icon="🎒"
        />
      ) : (
        <ul
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-xs)',
          }}
          aria-label="Inventory items"
        >
          {character.inventory.map((item) => (
            <li
              key={item.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: 'var(--space-xs) var(--space-sm)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg)',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '0.9rem',
                  color: 'var(--panel-ink)',
                }}
              >
                {item.name}
              </span>
              {item.quantity !== undefined && item.quantity !== 1 && (
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.75rem',
                    color: 'var(--panel-muted)',
                  }}
                  aria-label={`Quantity: ${item.quantity.toString()}`}
                >
                  ×{item.quantity}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
