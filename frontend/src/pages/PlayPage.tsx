/**
 * PlayPage — placeholder.
 *
 * Full implementation in T006 (app shell + routing) and T008–T013 (play loop panels).
 * Mirrors the Play screen from the Fantasy Gamebook prototype:
 *   - Narrator panel (prose in EB Garamond)
 *   - Numbered choices + free-text input
 *   - Character sheet sidebar
 *   - Combat panel (when in combat)
 */
export default function PlayPage() {
  return (
    <main
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        padding: '2rem',
      }}
    >
      <p
        style={{
          fontFamily: 'var(--font-body)',
          color: 'var(--muted)',
          fontSize: '1rem',
        }}
      >
        {/* T008–T013: replace with NarratorPanel + ChoicesPanel + CharacterSheet + CombatPanel */}
        Play loop coming in T008–T013 …
      </p>
    </main>
  )
}
