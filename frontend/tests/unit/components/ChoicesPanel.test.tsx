/**
 * ChoicesPanel unit tests.
 *
 * Verifies choices render, selection fires callbacks, and free text works.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChoicesPanel from '../../../src/components/ChoicesPanel'
import type { Choice } from '../../../src/types'

const CHOICES: Choice[] = [
  { id: '1', label: 'Go left' },
  { id: '2', label: 'Go right' },
]

describe('ChoicesPanel', () => {
  it('renders numbered choices', () => {
    render(
      <ChoicesPanel
        choices={CHOICES}
        onChoose={vi.fn()}
        onFreeText={vi.fn()}
      />
    )
    expect(screen.getByText('Go left')).toBeInTheDocument()
    expect(screen.getByText('Go right')).toBeInTheDocument()
  })

  it('calls onChoose with the choice id when a choice is clicked', () => {
    const onChoose = vi.fn()
    render(
      <ChoicesPanel
        choices={CHOICES}
        onChoose={onChoose}
        onFreeText={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('Go left'))
    expect(onChoose).toHaveBeenCalledWith('1')
  })

  it('shows loading state', () => {
    render(
      <ChoicesPanel
        choices={[]}
        loading={true}
        onChoose={vi.fn()}
        onFreeText={vi.fn()}
      />
    )
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows ended message when isEnded=true', () => {
    render(
      <ChoicesPanel
        choices={[]}
        isEnded={true}
        onChoose={vi.fn()}
        onFreeText={vi.fn()}
      />
    )
    expect(screen.getByText(/adventure has concluded/i)).toBeInTheDocument()
  })

  it('shows combat message when inCombat=true', () => {
    render(
      <ChoicesPanel
        choices={[]}
        inCombat={true}
        onChoose={vi.fn()}
        onFreeText={vi.fn()}
      />
    )
    expect(screen.getByText(/combat in progress/i)).toBeInTheDocument()
  })

  it('disables choices when actionPending=true', () => {
    render(
      <ChoicesPanel
        choices={CHOICES}
        actionPending={true}
        onChoose={vi.fn()}
        onFreeText={vi.fn()}
      />
    )
    const buttons = screen.getAllByRole('button')
    buttons.forEach((btn) => {
      if (btn.getAttribute('aria-label')?.startsWith('Choice')) {
        expect(btn).toBeDisabled()
      }
    })
  })

  it('submits free text on form submit', () => {
    const onFreeText = vi.fn()
    render(
      <ChoicesPanel
        choices={[]}
        onChoose={vi.fn()}
        onFreeText={onFreeText}
      />
    )
    const input = screen.getByLabelText('Free text action')
    fireEvent.change(input, { target: { value: 'I search the room' } })
    fireEvent.submit(screen.getByLabelText('Free text input'))
    expect(onFreeText).toHaveBeenCalledWith('I search the room')
  })
})
