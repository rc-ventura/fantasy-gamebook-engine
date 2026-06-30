import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCampaign } from '../hooks/useCampaign'
import { getCampaign } from '../api'
import type { CampaignState } from '../types'

interface FallenHero {
  id: string
  endedAt: string
  character: CampaignState['character']
  world: CampaignState['world']
}

export default function GraveyardPage() {
  const navigate = useNavigate()
  const { campaigns, error: listError } = useCampaign()
  const [fallen, setFallen] = useState<FallenHero[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const ended = campaigns.filter((c) => c.status === 'ended')
    if (ended.length === 0) { setLoading(false); return }

    Promise.all(
      ended.map((c) =>
        getCampaign(c.id)
          .then((state): FallenHero => ({ id: c.id, endedAt: c.updated_at, character: state.character, world: state.world }))
          .catch((): FallenHero => ({ id: c.id, endedAt: c.updated_at, character: undefined, world: undefined }))
      )
    ).then((results) => {
      setFallen(results)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [campaigns])

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })

  const fmtLoc = (loc: string) =>
    loc.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>

      {/* Header */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 30,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 32px', height: '62px',
        background: 'var(--bg2)', borderBottom: '1px solid var(--line)',
      }}>
        <button
          onClick={() => { void navigate('/dashboard') }}
          style={{ background: 'transparent', color: 'var(--muted)', border: 'none', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer', padding: 0 }}
        >
          ← Hall of Heroes
        </button>
        <span style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.92rem', letterSpacing: '0.12em', color: 'var(--ink)' }}>
          THE GRAVEYARD
        </span>
        <span style={{ width: '120px' }} />
      </header>

      {/* Page title */}
      <section style={{ textAlign: 'center', padding: '64px 24px 48px' }}>
        <div style={{ fontFamily: 'var(--font-title)', fontSize: '2.4rem', color: 'var(--faint)', marginBottom: '8px' }}>
          ✝
        </div>
        <h1 style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: 'clamp(2rem, 5vw, 3.2rem)', color: 'var(--ink)', margin: '0 0 12px', letterSpacing: '0.04em' }}>
          The Graveyard
        </h1>
        <p style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '1.15rem', color: 'var(--muted)', margin: 0 }}>
          Heroes who fell to the Grey Mountain are remembered here.
        </p>
      </section>

      {/* Content */}
      <main style={{ flex: 1, maxWidth: '1060px', width: '100%', margin: '0 auto', padding: '0 24px 80px' }}>

        {loading && (
          <div style={{ textAlign: 'center', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--faint)', letterSpacing: '0.1em', padding: '40px 0' }}>
            Consulting the death ledger…
          </div>
        )}

        {!loading && listError && (
          <div style={{ textAlign: 'center', color: '#c0392b', fontFamily: 'var(--font-body)', padding: '40px 0' }}>{listError}</div>
        )}

        {!loading && fallen.length === 0 && (
          <div style={{ textAlign: 'center', padding: '64px 0' }}>
            <div style={{ fontFamily: 'var(--font-title)', fontSize: '1.2rem', color: 'var(--ink)', marginBottom: '10px' }}>
              No fallen heroes yet
            </div>
            <p style={{ fontFamily: 'var(--font-body)', fontSize: '1.05rem', color: 'var(--muted)', marginBottom: '28px' }}>
              All your campaigns are still in progress — or you haven't forged a hero yet.
            </p>
            <button
              onClick={() => { void navigate('/dashboard') }}
              style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.9rem', letterSpacing: '0.06em', padding: '13px 28px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: '3px', cursor: 'pointer' }}
            >
              Return to the Hall →
            </button>
          </div>
        )}

        {!loading && fallen.length > 0 && (
          <>
            {/* Epitaph count */}
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: '36px', textAlign: 'center' }}>
              {fallen.length} soul{fallen.length !== 1 ? 's' : ''} lost to the mountain
            </div>

            {/* Hero cards grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '22px' }}>
              {fallen.map((hero) => (
                <article
                  key={hero.id}
                  style={{
                    background: 'var(--panel-bg)',
                    border: '1px solid var(--panel-border)',
                    borderRadius: '5px',
                    padding: '26px 22px',
                    display: 'flex', flexDirection: 'column', gap: '16px',
                    position: 'relative', overflow: 'hidden',
                    opacity: 0.9,
                  }}
                >
                  {/* Gravestone header */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <div>
                      <div style={{ fontFamily: 'var(--font-title)', fontWeight: 700, fontSize: '1.25rem', color: 'var(--panel-ink)', marginBottom: '3px' }}>
                        {hero.character?.name ?? 'Unnamed Hero'}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.66rem', letterSpacing: '0.08em', color: 'var(--faint)' }}>
                        R · I · P · {formatDate(hero.endedAt)}
                      </div>
                    </div>
                    <span style={{ fontFamily: 'var(--font-title)', fontSize: '1.6rem', color: 'var(--faint)', opacity: 0.6 }}>✝</span>
                  </div>

                  {/* Where they fell */}
                  {hero.world && (
                    <div style={{ fontFamily: 'var(--font-body)', fontStyle: 'italic', fontSize: '0.95rem', color: 'var(--panel-muted)', borderLeft: '2px solid var(--panel-border)', paddingLeft: '12px' }}>
                      Fell at <strong style={{ color: 'var(--panel-ink)' }}>{fmtLoc(hero.world.location)}</strong>
                      {hero.world.visited.length > 0 && `, after visiting ${hero.world.visited.length} zone${hero.world.visited.length !== 1 ? 's' : ''}.`}
                    </div>
                  )}

                  {/* Final stats */}
                  {hero.character && (
                    <div style={{ display: 'flex', gap: '10px' }}>
                      {[
                        { label: 'Skill', val: `${hero.character.skill.current}/${hero.character.skill.initial}`, color: 'var(--skill)' },
                        { label: 'Stamina', val: `${hero.character.stamina.current}/${hero.character.stamina.initial}`, color: 'var(--stamina)' },
                        { label: 'Luck', val: `${hero.character.luck.current}/${hero.character.luck.initial}`, color: 'var(--luck)' },
                      ].map(({ label, val, color }) => (
                        <div key={label} style={{ flex: 1, textAlign: 'center', background: 'var(--bg2)', border: '1px solid var(--line)', borderRadius: '3px', padding: '8px 4px' }}>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', letterSpacing: '0.08em', color: 'var(--faint)', textTransform: 'uppercase', marginBottom: '3px' }}>{label}</div>
                          <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.9rem', fontWeight: 600, color }}>{val}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Campaign ID footnote */}
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--faint)', letterSpacing: '0.06em', borderTop: '1px solid var(--line)', paddingTop: '10px' }}>
                    Campaign {hero.id.slice(0, 8)}…
                  </div>

                  {/* Vignette overlay for atmosphere */}
                  <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, rgba(0,0,0,.07) 0, transparent 60%)', pointerEvents: 'none' }} />
                </article>
              ))}
            </div>

            {/* CTA */}
            <div style={{ textAlign: 'center', marginTop: '54px' }}>
              <button
                onClick={() => { void navigate('/dashboard') }}
                style={{ fontFamily: 'var(--font-title)', fontWeight: 600, fontSize: '0.9rem', letterSpacing: '0.06em', padding: '13px 28px', background: 'var(--accent)', color: 'var(--accent-ink)', border: 'none', borderRadius: '3px', cursor: 'pointer' }}
                onMouseOver={(e) => { e.currentTarget.style.filter = 'brightness(1.08)' }}
                onMouseOut={(e) => { e.currentTarget.style.filter = '' }}
              >
                ⚔ Forge a new hero
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
