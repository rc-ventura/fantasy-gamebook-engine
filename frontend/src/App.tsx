import { Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import AuthPage from './pages/AuthPage'
import DashboardPage from './pages/DashboardPage'
import PlayPage from './pages/PlayPage'
import GraveyardPage from './pages/GraveyardPage'
import CreateHeroPage from './pages/CreateHeroPage'
import { useAuth } from './hooks/useAuth'

/**
 * App — root routing shell.
 *
 * Screens (per Fantasy Gamebook prototype):
 *   /           → Landing / Marketing
 *   /auth       → Sign-in / Register
 *   /dashboard  → Campaign list / Dashboard
 *   /play/:id   → Play loop (narrator + choices + character sheet + combat)
 */

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { authenticated } = useAuth()
  if (!authenticated) {
    return <Navigate to="/auth" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/auth" element={<AuthPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/play/:id"
        element={
          <ProtectedRoute>
            <PlayPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/create"
        element={
          <ProtectedRoute>
            <CreateHeroPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/graveyard"
        element={
          <ProtectedRoute>
            <GraveyardPage />
          </ProtectedRoute>
        }
      />
      {/* Redirect unknown paths to landing */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
