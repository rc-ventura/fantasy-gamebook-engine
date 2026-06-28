/**
 * CombatPanel unit tests.
 *
 * Verifies that engine-produced combat values render correctly,
 * resolve round / flee buttons fire callbacks, and states work.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CombatPanel from '../../../src/components/CombatPanel'
import type { CombatState } from '../../../src/types'

const ACTIVE_COMBAT: CombatState = {
  participants: [
    { name: 'Aldric', skill: 10, stamina: 18 },
    { name: 'Dire Wolf', skill: 8, stamina: 6 },
  ],
  rounds: [],
  flee_allowed: false,
  active: true,
}

const COMBAT_WITH_ROUND: CombatState = {
  ...ACTIVE_COMBAT,
  rounds: [
    {
      hero_attack: 16,
      enemy_attack: 11,
      hero_damage: 2,
      enemy_damage: 0,
    },
  ],
}

describe('CombatPanel', () => {
  it('renders combatant names from engine', () => {
    render(<CombatPanel combat={ACTIVE_COMBAT} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByText('Aldric')).toBeInTheDocument()
    expect(screen.getByText('Dire Wolf')).toBeInTheDocument()
  })

  it('renders combatant stamina values from engine', () => {
    render(<CombatPanel combat={ACTIVE_COMBAT} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByLabelText('Hero stamina: 18')).toBeInTheDocument()
    expect(screen.getByLabelText('Enemy stamina: 6')).toBeInTheDocument()
  })

  it('renders Resolve Round button', () => {
    render(<CombatPanel combat={ACTIVE_COMBAT} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByLabelText('Resolve combat round')).toBeInTheDocument()
  })

  it('calls onCombatRound(false) on resolve click', () => {
    const onCombatRound = vi.fn()
    render(<CombatPanel combat={ACTIVE_COMBAT} onCombatRound={onCombatRound} onFlee={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('Resolve combat round'))
    expect(onCombatRound).toHaveBeenCalledWith(false)
  })

  it('calls onCombatRound(true) on resolve+luck click', () => {
    const onCombatRound = vi.fn()
    render(<CombatPanel combat={ACTIVE_COMBAT} onCombatRound={onCombatRound} onFlee={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('Resolve round and test luck'))
    expect(onCombatRound).toHaveBeenCalledWith(true)
  })

  it('does not show Flee button when flee_allowed=false', () => {
    render(<CombatPanel combat={ACTIVE_COMBAT} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.queryByLabelText('Attempt to flee combat')).not.toBeInTheDocument()
  })

  it('shows Flee button when flee_allowed=true', () => {
    render(<CombatPanel combat={{ ...ACTIVE_COMBAT, flee_allowed: true }} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByLabelText('Attempt to flee combat')).toBeInTheDocument()
  })

  it('renders engine-produced round results', () => {
    render(<CombatPanel combat={COMBAT_WITH_ROUND} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    // Attack strengths from the engine
    expect(screen.getByLabelText('Hero attack strength: 16')).toBeInTheDocument()
    expect(screen.getByLabelText('Enemy attack strength: 11')).toBeInTheDocument()
    // Damage from the engine
    expect(screen.getByLabelText('Enemy took 2 damage')).toBeInTheDocument()
  })

  it('shows loading state when loading=true', () => {
    render(<CombatPanel combat={null} loading={true} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows empty state when no combat is active', () => {
    render(<CombatPanel combat={null} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByText(/no combat in progress/i)).toBeInTheDocument()
  })

  it('shows victory outcome', () => {
    const ended: CombatState = { ...ACTIVE_COMBAT, active: false, outcome: 'victory' }
    render(<CombatPanel combat={ended} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByLabelText('Combat ended: victory')).toBeInTheDocument()
  })

  it('disables buttons when actionPending=true', () => {
    render(<CombatPanel combat={ACTIVE_COMBAT} actionPending={true} onCombatRound={vi.fn()} onFlee={vi.fn()} />)
    expect(screen.getByLabelText('Resolve combat round')).toBeDisabled()
    expect(screen.getByLabelText('Resolve round and test luck')).toBeDisabled()
  })
})
