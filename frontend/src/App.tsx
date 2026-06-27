import { Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import PlayPage from './pages/PlayPage'

/**
 * App — root routing shell.
 *
 * Routes are fleshed out in T006 (app shell + routing).
 * For now they are placeholder components so the scaffold builds and typechecks.
 *
 * Screens (per Fantasy Gamebook prototype):
 *   /           → Landing / Marketing
 *   /auth       → Sign-in / Register  (T007/T016)
 *   /dashboard  → Campaign list / Dashboard  (T006/T017)
 *   /play/:id   → Play loop  (T008–T013)
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/play/:id" element={<PlayPage />} />
      {/* Redirect unknown paths to landing */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
