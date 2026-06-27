/**
 * NarratorPanel unit tests.
 *
 * Verifies that the panel renders narrative prose correctly and
 * shows the right loading/empty states.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import NarratorPanel from '../../../src/components/NarratorPanel'

describe('NarratorPanel', () => {
  it('renders narrative prose paragraphs', () => {
    // Use expression syntax (curly braces) so JS processes \n as actual newline.
    // JSX string attributes ("...") do NOT process escape sequences.
    render(<NarratorPanel narrative={"First paragraph.\n\nSecond paragraph."} />)
    expect(screen.getByText('First paragraph.')).toBeInTheDocument()
    expect(screen.getByText('Second paragraph.')).toBeInTheDocument()
  })

  it('shows loading state when loading=true', () => {
    render(<NarratorPanel narrative={null} loading={true} />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows empty state when narrative is null', () => {
    render(<NarratorPanel narrative={null} />)
    expect(screen.getByText(/tale has not yet begun/i)).toBeInTheDocument()
  })

  it('shows empty state when narrative is undefined', () => {
    render(<NarratorPanel narrative={undefined} />)
    expect(screen.getByText(/tale has not yet begun/i)).toBeInTheDocument()
  })

  it('shows terminal indicator when isTerminal=true', () => {
    render(<NarratorPanel narrative="The end." isTerminal={true} />)
    expect(screen.getByLabelText('Adventure ended')).toBeInTheDocument()
  })

  it('does not show terminal indicator by default', () => {
    render(<NarratorPanel narrative="Still going." />)
    expect(screen.queryByLabelText('Adventure ended')).not.toBeInTheDocument()
  })
})
