import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCampaign, createCharacter, deleteCampaign } from '../api'
import type { CharacterSheet } from '../types'

type Step = 'compose' | 'rolling' | 'preview'

export default function CreateHeroPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [step, setStep] = useState<Step>('compose')
  const [stats, setStats] = useState<CharacterSheet | null>(null)
  const [error, setError] = useState<string | null>(null)
  const campaignIdRef = useRef<string | null>(null)

  const canRoll = name.trim().length > 0 && step !== 'rolling'

  async function handleRoll() {
    if (!canRoll) return
    setStep('rolling')
    setError(null)

    // Delete previous attempt if re-rolling
    if (campaignIdRef.current) {
      await deleteCampaign(campaignIdRef.current).catch(() => null)
      campaignIdRef.current = null
    }

    try {
      const campaign = await createCampaign()
      const id = campaign.id
      campaignIdRef.current = id
      const sheet = await createCharacter(id, name.trim())
      setStats(sheet)
      setStep('preview')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Engine roll failed — try again.')
      setStep('compose')
    }
  }

  async function handleBegin() {
    if (!campaignIdRef.current) return
    void navigate(`/play/${campaignIdRef.current}`)
  }

  async function handleBack() {
    // Clean up campaign if created but not confirmed
    if (campaignIdRef.current) {
      await deleteCampaign(campaignIdRef.current).catch(() => null)
      campaignIdRef.current = null
    }
    void navigate('/dashboard')
  }

  const rolling = step === 'rolling'
  const previewing = step === 'preview' && stats !== null

  const STATS = stats
    ? [
        { label: 'Skill',   value: stats.skill.initial,   color: 'var(--skill)',   formula: '1d6 + 6' },
        { label: 'Stamina', value: stats.stamina.initial, color: 'var(--stamina)', formula: '2d6 + 12' },
        { label: 'Luck',    value: stats.luck.initial,    color: 'var(--luck)',    formula: '1d6 + 6' },
      ]
    : [
        { label: 'Skill',   value: null, color: 'var(--skill)',   formula: '1d6 + 6' },
        { label: 'Stamina', value: null, color: 'var(--stamina)', formula: '2d6 + 12' },
        { label: 'Luck',    value: null, color: 'var(--luck)',    formula: '1d6 + 6' },
      ]

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '48px 24px',
    }}>
      <div style={{
        width: '100%', maxWidth: '560px',
        background: 'var(--panel-bg)', border: '1px solid var(--panel-border)',
        borderRadius: '5px', padding: '40px',
        boxShadow: '0 30px 70px rgba(0,0,0,.4)',
        animation: 'gbIn .45s ease both',
      }}>
        {/* Label */}
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.26em',
          textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '10px',
        }}>
          New Campaign
        </div>

        {/* Title */}
        <h2 style={{
          fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.9rem',
          margin: '0 0 6px', color: 'var(--panel-ink)',
        }}>
          Forge your hero
        </h2>
        <p style={{
          fontFamily: 'var(--font-body)', fontSize: '1.05rem', color: 'var(--panel-muted)',
          margin: '0 0 26px', lineHeight: 1.5,
        }}>
          Name your adventurer, then let the engine roll your fate. Attributes are rolled by the dice — never chosen, never narrated.
        </p>

        {/* Name input */}
        <label style={{
          display: 'block', fontFamily: 'var(--font-mono)', fontSize: '0.7rem',
          letterSpacing: '0.16em', textTransform: 'uppercase', color: 'var(--panel-muted)', marginBottom: '8px',
        }}>
          Hero name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void handleRoll() }}
          placeholder="Arquimedes"
          disabled={rolling}
          style={{
            width: '100%', padding: '13px 14px',
            background: 'var(--bg2)', border: '1px solid var(--panel-border)',
            borderRadius: '3px', color: 'var(--ink)',
            fontFamily: 'var(--font-body)', fontSize: '1.1rem',
            marginBottom: '26px', outline: 'none',
            opacity: rolling ? 0.6 : 1,
          }}
          onFocus={(e) => { e.currentTarget.style.borderColor = 'var(--accent)' }}
          onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--panel-border)' }}
          autoFocus
        />

        {/* Stat boxes */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '14px' }}>
          {STATS.map(({ label, value, color, formula }) => (
            <div key={label} style={{
              background: 'var(--bg2)', border: '1px solid var(--panel-border)',
              borderRadius: '3px', padding: '16px 12px', textAlign: 'center',
              transition: 'border-color .2s',
              borderColor: previewing ? color : undefined,
            }}>
              <div style={{
                fontFamily: 'var(--font-title)', fontSize: '0.78rem', letterSpacing: '0.1em',
                textTransform: 'uppercase', color, marginBottom: '8px',
              }}>
                {label}
              </div>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: '2rem', fontWeight: 600,
                color: 'var(--panel-ink)', minHeight: '2.4rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {rolling ? (
                  <span style={{ fontSize: '1.2rem', opacity: 0.4, animation: 'gbFlick 0.6s ease infinite' }}>⚄</span>
                ) : value !== null ? (
                  value
                ) : (
                  <span style={{ color: 'var(--faint)', fontSize: '1.4rem' }}>—</span>
                )}
              </div>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--faint)', marginTop: '4px',
              }}>
                {formula}
              </div>
            </div>
          ))}
        </div>

        {/* Roll button */}
        <button
          onClick={() => { void handleRoll() }}
          disabled={!canRoll}
          style={{
            width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.78rem',
            letterSpacing: '0.14em', textTransform: 'uppercase',
            padding: '13px', background: 'transparent',
            border: `1px dashed ${canRoll ? 'var(--accent)' : 'var(--faint)'}`,
            borderRadius: '3px', color: canRoll ? 'var(--accent)' : 'var(--faint)',
            cursor: canRoll ? 'pointer' : 'not-allowed', marginBottom: '24px',
            transition: 'border-color .15s, color .15s',
          }}
          onMouseOver={(e) => { if (canRoll) e.currentTarget.style.borderColor = 'var(--accent-hover)' }}
          onMouseOut={(e) => { if (canRoll) e.currentTarget.style.borderColor = 'var(--accent)' }}
        >
          {rolling ? 'Rolling…' : previewing ? '⚄ Re-roll attributes' : '⚄ Roll attributes via the engine'}
        </button>

        {/* Error */}
        {error && (
          <p role="alert" style={{
            fontFamily: 'var(--font-body)', fontSize: '0.9rem', color: '#c0392b',
            margin: '0 0 16px',
          }}>
            {error}
          </p>
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={() => { void handleBack() }}
            disabled={rolling}
            style={{
              fontFamily: 'var(--font-body)', fontSize: '1rem',
              padding: '13px 18px', background: 'transparent',
              border: '1px solid var(--panel-border)', borderRadius: '3px',
              color: 'var(--panel-muted)', cursor: rolling ? 'not-allowed' : 'pointer',
              opacity: rolling ? 0.5 : 1,
            }}
          >
            Back
          </button>
          <button
            onClick={() => { void handleBegin() }}
            disabled={!previewing || rolling}
            style={{
              flex: 1, fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.92rem',
              letterSpacing: '0.04em', padding: '13px',
              background: previewing ? 'var(--accent)' : 'var(--faint)',
              color: previewing ? 'var(--accent-ink)' : 'var(--bg)',
              border: 'none', borderRadius: '3px',
              cursor: previewing ? 'pointer' : 'not-allowed',
              transition: 'filter .15s, background .2s',
            }}
            onMouseOver={(e) => { if (previewing) e.currentTarget.style.filter = 'brightness(1.08)' }}
            onMouseOut={(e) => { e.currentTarget.style.filter = '' }}
          >
            Enter the Grey Mountain →
          </button>
        </div>
      </div>
    </div>
  )
}
