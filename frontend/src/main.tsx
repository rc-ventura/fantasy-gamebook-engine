import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from 'react-oidc-context'
import './index.css'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { userManager } from './auth/oidcConfig'
import './auth/tokenBridge'

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element #root not found in index.html')
}

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <AuthProvider
        userManager={userManager}
        onSigninCallback={() => {
          window.history.replaceState({}, document.title, window.location.pathname)
        }}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  </StrictMode>,
)
