import { useState, useEffect, useRef } from 'react'
import type { CharacterSheet, CombatState } from '../types'
import LoadingState from './LoadingState'

interface CombatPanelProps {
  combat: CombatState | null | undefined
  character?: CharacterSheet | null
  loading?: boolean
  actionPending?: boolean
  onCombatRound: (testLuck: boolean) => void | Promise<void>
  onFlee: () => void | Promise<void>
}

interface LogLine { text: string; color: string }

function buildLog(combat: CombatState): LogLine[] {
  const lines: LogLine[] = []
  combat.rounds.forEach((r, i) => {
    lines.push({
      text: `Round ${i + 1}: Attack strength — you ${r.hero_attack} · foe ${r.enemy_attack}`,
      color: 'var(--faint)',
    })
    if (r.hero_attack > r.enemy_attack) {
      const dmg = r.hero_damage
      lines.push({ text: `You struck the enemy for ${dmg} stamina.`, color: 'var(--ink)' })
    } else if (r.enemy_attack > r.hero_attack) {
      const dmg = r.enemy_damage
      lines.push({ text: `The enemy struck you for ${dmg} stamina.`, color: 'var(--danger)' })
    } else {
      lines.push({ text: 'Blades clashed — neither side wounded.', color: 'var(--muted)' })
    }
    if (r.luck_used) {
      const lucky = r.luck_result === 'lucky'
      lines.push({
        text: lucky ? '★ Luck was with you — modified damage applied.' : '✦ Luck failed — modified damage applied.',
        color: lucky ? 'var(--luck)' : 'var(--muted)',
      })
    }
  })
  return lines
}

export default function CombatPanel({
  combat,
  character,
  loading = false,
  actionPending = false,
  onCombatRound,
  onFlee,
}: CombatPanelProps) {
  const [testLuck, setTestLuck] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)

  // Auto-scroll log to bottom when new rounds arrive
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [combat?.rounds.length])

  // Reset luck toggle after each resolved round
  const prevRoundsLen = useRef(0)
  useEffect(() => {
    const len = combat?.rounds.length ?? 0
    if (len > prevRoundsLen.current) setTestLuck(false)
    prevRoundsLen.current = len
  }, [combat?.rounds.length])

  if (loading) return <LoadingState message="Entering combat…" size="sm" />

  if (!combat || !combat.active) {
    if (!combat?.outcome) return null
    const label = { victory: '⚔ Victory!', defeat: '☠ Defeated', fled: '💨 Fled' }[combat.outcome]
    const color = { victory: 'var(--accent)', defeat: 'var(--danger)', fled: 'var(--muted)' }[combat.outcome]
    return (
      <div style={{
        background: 'var(--panel-bg)', border: '1px solid var(--panel-border)',
        borderRadius: '4px', padding: '18px', textAlign: 'center',
      }}>
        <button
          onClick={() => { void Promise.resolve(onCombatRound(false)) }}
          style={{
            width: '100%', fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.92rem',
            letterSpacing: '0.04em', padding: '14px',
            background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none',
            borderRadius: '3px', cursor: 'pointer', marginBottom: '10px',
          }}
        >
          Continue the story →
        </button>
        <span role="status" style={{ fontFamily: 'var(--font-title)', fontSize: '1.1rem', color }}>{label}</span>
      </div>
    )
  }

  const hero = combat.participants[0]
  const enemy = combat.participants[1]
  const log = buildLog(combat)

  // Hero health bar uses CharacterSheet if available (has initial)
  const heroStamMax = character?.stamina.initial ?? Math.max(hero?.stamina ?? 1, 1)
  const heroStamCur = character?.stamina.current ?? hero?.stamina ?? 0
  const heroSkill   = character?.skill.current ?? hero?.skill ?? 0
  const heroPct     = Math.max(0, Math.min(100, (heroStamCur / heroStamMax) * 100))

  const enemyStam = enemy?.stamina ?? 0
  const enemySkill = enemy?.skill ?? 0

  return (
    <section aria-label="Combat" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>

      {/* Combat header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <span style={{ fontFamily: 'var(--font-title)', fontSize: '1.05rem', letterSpacing: '0.1em', color: 'var(--danger)', textTransform: 'uppercase', fontWeight: 700 }}>
          ⚔ Combat
        </span>
        <span style={{ flex: 1, height: '1px', background: 'var(--line)' }} />
        {combat.flee_allowed && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', color: 'var(--faint)' }}>
            flee allowed
          </span>
        )}
      </div>

      {/* Hero vs Enemy cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: '18px', alignItems: 'center' }}>

        {/* Hero card */}
        <div style={{ background: 'var(--panel-bg)', border: '1px solid var(--panel-border)', borderRadius: '4px', padding: '18px' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.64rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: '6px' }}>Hero</div>
          <div style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1.15rem', color: 'var(--panel-ink)', marginBottom: '12px' }}>
            {character?.name ?? hero?.name ?? 'Hero'}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--panel-muted)', marginBottom: '6px' }}>
            <span>Skill</span><span style={{ color: 'var(--skill)' }}>{heroSkill}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--panel-muted)', marginBottom: '6px' }}>
            <span>Stamina</span>
            <span style={{ color: 'var(--stamina)' }}>{heroStamCur}/{heroStamMax}</span>
          </div>
          <div style={{ height: '6px', background: 'var(--bg2)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${heroPct}%`, background: heroPct > 40 ? 'var(--stamina)' : 'var(--danger)', borderRadius: '3px', transition: 'width .4s ease' }} />
          </div>
        </div>

        {/* VS */}
        <div style={{ fontFamily: 'var(--font-title)', fontSize: '1.3rem', color: 'var(--danger)' }}>VS</div>

        {/* Enemy card */}
        <div style={{ background: 'var(--panel-bg)', border: '1px solid var(--danger)', borderRadius: '4px', padding: '18px' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.64rem', letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: '6px' }}>Foe</div>
          <div style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '1.15rem', color: 'var(--panel-ink)', marginBottom: '12px' }}>
            {enemy?.name ?? 'Enemy'}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--panel-muted)', marginBottom: '6px' }}>
            <span>Skill</span><span style={{ color: 'var(--skill)' }}>{enemySkill}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: '0.76rem', color: 'var(--panel-muted)', marginBottom: '6px' }}>
            <span>Stamina</span><span style={{ color: 'var(--stamina)' }}>{enemyStam}</span>
          </div>
          {/* Enemy bar — no initial, show full-ish as placeholder */}
          <div style={{ height: '6px', background: 'var(--bg2)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: '70%', background: 'var(--danger)', borderRadius: '3px' }} />
          </div>
        </div>
      </div>

      {/* Combat log */}
      <div
        ref={logRef}
        style={{
          background: 'var(--bg2)', border: '1px solid var(--line)', borderRadius: '4px',
          padding: '16px 18px', height: '188px', overflowY: 'auto',
        }}
      >
        {log.length === 0 ? (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--faint)' }}>
            Combat has begun — resolve your first round.
          </div>
        ) : (
          log.map((line, i) => (
            <div key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', lineHeight: 1.5, marginBottom: '7px', color: line.color }}>
              {line.text}
            </div>
          ))
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        {/* Luck toggle */}
        <button
          onClick={() => setTestLuck((v) => !v)}
          disabled={actionPending}
          style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.78rem', letterSpacing: '0.06em',
            padding: '13px 14px',
            background: testLuck ? 'var(--luck)' : 'transparent',
            color: testLuck ? 'var(--bg)' : 'var(--luck)',
            border: `1px solid ${testLuck ? 'var(--luck)' : 'var(--panel-border)'}`,
            borderRadius: '3px', cursor: actionPending ? 'not-allowed' : 'pointer',
            opacity: actionPending ? 0.5 : 1, transition: 'all .15s',
          }}
          aria-pressed={testLuck}
          title="Toggle luck test for this round"
        >
          ⚅ Test luck this round
        </button>

        {/* Resolve */}
        <button
          onClick={() => { void Promise.resolve(onCombatRound(testLuck)) }}
          disabled={actionPending}
          style={{
            flex: 1, minWidth: '140px',
            fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.9rem', letterSpacing: '0.04em',
            padding: '13px', background: 'var(--danger)', color: '#fff',
            border: 'none', borderRadius: '3px', cursor: actionPending ? 'wait' : 'pointer',
            opacity: actionPending ? 0.6 : 1,
          }}
          aria-label="Resolve combat round"
        >
          {actionPending ? 'Resolving…' : 'Resolve round'}
        </button>

        {/* Flee */}
        {combat.flee_allowed && (
          <button
            onClick={() => { void Promise.resolve(onFlee()) }}
            disabled={actionPending}
            style={{
              fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.1em',
              textTransform: 'uppercase', padding: '13px 16px',
              background: 'transparent', border: '1px solid var(--panel-border)',
              borderRadius: '3px', color: 'var(--muted)',
              cursor: actionPending ? 'not-allowed' : 'pointer', opacity: actionPending ? 0.5 : 1,
            }}
            aria-label="Flee combat (costs 2 stamina)"
          >
            Flee −2
          </button>
        )}
      </div>
    </section>
  )
}
