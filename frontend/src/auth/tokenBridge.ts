/**
 * Bridges the real OIDC session (userManager, auth/oidcConfig.ts) into
 * frontend/src/api/client.ts's synchronous token-provider seam.
 *
 * The bearer credential sent to the backend is the `id_token`, not the
 * `access_token` — the backend validates `aud`/`iss` exactly as the OIDC spec
 * guarantees for an id_token (always a JWT, `aud` == client_id); `access_token`
 * format/claims are not spec-guaranteed across providers. See research.md.
 *
 * `client.ts`'s `_tokenProvider` is synchronous, so the current id_token is
 * cached here and kept in sync via UserManager's load/unload events, rather than
 * making every API call await `userManager.getUser()`.
 *
 * Falls back to the dev token-paste stub's sessionStorage entry (DEV builds
 * only, FR-009) when there's no real OIDC session — keeps that fallback usable
 * for API calls, not just the `authenticated` flag in useAuth.ts.
 */
import { setTokenProvider } from '../api'
import { userManager } from './oidcConfig'

let cachedIdToken: string | null = null

userManager.events.addUserLoaded((user) => {
  cachedIdToken = user.id_token ?? null
})
userManager.events.addUserUnloaded(() => {
  cachedIdToken = null
})

// Seed from any session already persisted in sessionStorage (e.g. after a reload).
void userManager.getUser().then((user) => {
  cachedIdToken = user?.id_token ?? null
})

setTokenProvider(() => {
  if (cachedIdToken) return cachedIdToken
  return import.meta.env.DEV ? sessionStorage.getItem('auth_token') : null
})
