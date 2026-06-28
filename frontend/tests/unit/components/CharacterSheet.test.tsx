/**
 * CharacterSheet unit tests.
 *
 * Verifies that the panel renders engine-produced stats and
 * shows loading/empty states.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CharacterSheet from '../../../src/components/CharacterSheet'
import type { CharacterSheet as CharacterSheetType } from '../../../src/types'

const MOCK_CHARACTER: CharacterSheetType = {
  name: 'Aldric',
  skill: { initial: 10, current: 10 },
  stamina: { initial: 20, current: 14 },
  luck: { initial: 9, current: 7 },
  gold: 15,
  provisions: 8,
  inventory: [],
  conditions: [],
  alive: true,
}

describe('CharacterSheet', () => {
  it('renders character name', () => {
    render(<CharacterSheet character={MOCK_CHARACTER} />)
    expect(screen.getByText('Aldric')).toBeInTheDocument()
  })

  it('renders skill attribute from engine', () => {
    render(<CharacterSheet character={MOCK_CHARACTER} />)
    // 10/10 is the engine-produced skill value
    expect(screen.getByLabelText('Skill: 10 of 10')).toBeInTheDocument()
  })

  it('renders stamina attribute from engine', () => {
    render(<CharacterSheet character={MOCK_CHARACTER} />)
    expect(screen.getByLabelText('Stamina: 14 of 20')).toBeInTheDocument()
  })

  it('renders luck attribute from engine', () => {
    render(<CharacterSheet character={MOCK_CHARACTER} />)
    expect(screen.getByLabelText('Luck: 7 of 9')).toBeInTheDocument()
  })

  it('renders gold from engine', () => {
    render(<CharacterSheet character={MOCK_CHARACTER} />)
    expect(screen.getByLabelText('Gold: 15')).toBeInTheDocument()
  })

  it('renders provisions from engine', () => {
    render(<CharacterSheet character={MOCK_CHARACTER} />)
    expect(screen.getByLabelText('Provisions: 8')).toBeInTheDocument()
  })

  it('shows loading state when loading=true', () => {
    render(<CharacterSheet character={null} loading={true} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows empty state when character is null', () => {
    render(<CharacterSheet character={null} />)
    expect(screen.getByText(/no character yet/i)).toBeInTheDocument()
  })

  it('shows fallen indicator when character is not alive', () => {
    render(<CharacterSheet character={{ ...MOCK_CHARACTER, alive: false }} />)
    expect(screen.getByText(/fallen/i)).toBeInTheDocument()
  })

  it('renders conditions when present', () => {
    render(<CharacterSheet character={{ ...MOCK_CHARACTER, conditions: ['Poisoned', 'Blinded'] }} />)
    expect(screen.getByText('Poisoned')).toBeInTheDocument()
    expect(screen.getByText('Blinded')).toBeInTheDocument()
  })
})
