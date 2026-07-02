/**
 * ChoicesPanel free-text validation tests (T111, FR-058).
 *
 * Empty / whitespace-only submissions are rejected, the submit button stays
 * disabled until real input exists, and length is capped at 1000 chars.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChoicesPanel from '../../../src/components/ChoicesPanel'

function renderPanel(onFreeText = vi.fn()) {
  render(
    <ChoicesPanel choices={[]} onChoose={vi.fn()} onFreeText={onFreeText} />
  )
  return {
    onFreeText,
    input: screen.getByLabelText('Free text action'),
    submit: screen.getByRole('button', { name: 'Submit free text action' }),
    form: screen.getByLabelText('Free text input'),
  }
}

describe('ChoicesPanel free-text validation', () => {
  it('disables the submit button when the input is empty', () => {
    const { submit } = renderPanel()
    expect(submit).toBeDisabled()
  })

  it('keeps the submit button disabled for whitespace-only input', () => {
    const { input, submit } = renderPanel()
    fireEvent.change(input, { target: { value: '   ' } })
    expect(submit).toBeDisabled()
  })

  it('enables the submit button once real text is entered', () => {
    const { input, submit } = renderPanel()
    fireEvent.change(input, { target: { value: 'search the room' } })
    expect(submit).toBeEnabled()
  })

  it('does not submit empty or whitespace-only text on form submit', () => {
    const { input, form, onFreeText } = renderPanel()
    fireEvent.submit(form)
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.submit(form)
    expect(onFreeText).not.toHaveBeenCalled()
  })

  it('trims the submitted text', () => {
    const { input, form, onFreeText } = renderPanel()
    fireEvent.change(input, { target: { value: '  open the chest  ' } })
    fireEvent.submit(form)
    expect(onFreeText).toHaveBeenCalledWith('open the chest')
  })

  it('caps input length at 1000 characters via the maxLength attribute', () => {
    const { input } = renderPanel()
    expect(input).toHaveAttribute('maxLength', '1000')
  })
})
