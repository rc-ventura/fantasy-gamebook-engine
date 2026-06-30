/**
 * ChoicesPanel — renders numbered choices and free-text input.
 *
 * The choices list comes entirely from the API scene — nothing is invented.
 * Accepts both numbered choice selection and free-text player input (FR-004).
 * Disabled when: loading, action in progress, or run ended.
 * Combat is now resolved inside the narrator's tool-use loop (ADR-029) and
 * delivered as narrated prose in the Scene — no separate combat controls.
 */

import { useState } from 'react'
import type { Choice } from '../types'
import LoadingState from './LoadingState'

interface ChoicesPanelProps {
  choices: Choice[]
  loading?: boolean
  /** True when an action (turn/combat) is in progress. */
  actionPending?: boolean
  /** True when the campaign is ended — no further choices. */
  isEnded?: boolean
  onChoose: (choiceId: string) => void | Promise<void>
  onFreeText: (text: string) => void | Promise<void>
}

export default function ChoicesPanel({
  choices,
  loading = false,
  actionPending = false,
  isEnded = false,
  onChoose,
  onFreeText,
}: ChoicesPanelProps) {
  const [freeText, setFreeText] = useState('')
  const disabled = loading || actionPending || isEnded

  if (loading) {
    return <LoadingState message="Preparing choices…" size="sm" />
  }

  if (isEnded) {
    return (
      <div
        style={{
          padding: 'var(--space-lg)',
          textAlign: 'center',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: 'var(--faint)',
        }}
      >
        Your adventure has concluded.
      </div>
    )
  }

  function handleChoose(id: string) {
    void Promise.resolve(onChoose(id))
  }

  function handleFreeTextSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = freeText.trim()
    if (!trimmed) return
    setFreeText('')
    void Promise.resolve(onFreeText(trimmed))
  }

  return (
    <section
      aria-label="Your choices"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-md)',
        padding: 'var(--space-lg)',
        background: 'var(--bg2)',
        border: '1px solid var(--panel-border)',
        borderRadius: 'var(--radius-md)',
      }}
    >
      {/* Section label */}
      {choices.length > 0 && (
        <div style={{
          fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.82rem',
          letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)',
        }}>
          What do you do?
        </div>
      )}

      {/* Numbered choices */}
      {choices.length > 0 && (
        <ol
          style={{
            listStyle: 'none',
            margin: 0,
            padding: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-sm)',
          }}
          aria-label="Numbered choices"
        >
          {choices.map((choice, i) => (
            <li key={choice.id}>
              <button
                onClick={() => handleChoose(choice.id)}
                disabled={disabled}
                aria-label={`Choice ${(i + 1).toString()}: ${choice.label}`}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '14px',
                  width: '100%',
                  background: 'var(--panel-bg)',
                  border: '1px solid var(--panel-border)',
                  borderRadius: '3px',
                  padding: '15px 17px',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  opacity: disabled ? 0.5 : 1,
                  transition: 'border-color var(--transition), transform 120ms',
                  textAlign: 'left',
                }}
                onMouseOver={(e) => {
                  if (!disabled) {
                    e.currentTarget.style.borderColor = 'var(--accent)'
                    e.currentTarget.style.transform = 'translateX(3px)'
                  }
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.borderColor = 'var(--panel-border)'
                  e.currentTarget.style.transform = ''
                }}
              >
                {/* Circular number badge */}
                <span
                  style={{
                    width: '27px', height: '27px', flexShrink: 0,
                    display: 'grid', placeItems: 'center',
                    border: '1px solid var(--panel-border)', borderRadius: '50%',
                    fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--accent)',
                  }}
                  aria-hidden="true"
                >
                  {i + 1}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: '1.1rem',
                    color: 'var(--panel-ink)',
                    lineHeight: 1.4,
                    paddingTop: '2px',
                  }}
                >
                  {choice.label}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}

      {/* Free-text input */}
      <form
        onSubmit={handleFreeTextSubmit}
        style={{
          display: 'flex',
          gap: 'var(--space-sm)',
          borderTop: choices.length > 0 ? '1px solid var(--line)' : 'none',
          paddingTop: choices.length > 0 ? 'var(--space-md)' : 0,
        }}
        aria-label="Free text input"
      >
        <input
          type="text"
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          disabled={disabled}
          placeholder={
            actionPending ? 'Awaiting the narrator…' : 'Or speak freely…'
          }
          aria-label="Free text action"
          style={{
            flex: 1,
            background: 'var(--bg)',
            border: '1px solid var(--panel-border)',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-sm) var(--space-md)',
            color: 'var(--ink)',
            fontFamily: 'var(--font-body)',
            fontSize: '0.95rem',
            outline: 'none',
            opacity: disabled ? 0.5 : 1,
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = 'var(--accent)'
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = 'var(--panel-border)'
          }}
        />
        <button
          type="submit"
          disabled={disabled || !freeText.trim()}
          aria-label="Submit free text action"
          style={{
            background: 'var(--accent)',
            color: 'var(--accent-ink)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            padding: 'var(--space-sm) var(--space-md)',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.75rem',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            cursor: disabled || !freeText.trim() ? 'not-allowed' : 'pointer',
            opacity: disabled || !freeText.trim() ? 0.5 : 1,
            transition: 'opacity var(--transition)',
            flexShrink: 0,
          }}
        >
          {actionPending ? '…' : 'Act'}
        </button>
      </form>
    </section>
  )
}
