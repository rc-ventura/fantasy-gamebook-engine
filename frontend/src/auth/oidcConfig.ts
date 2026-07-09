/**
 * OIDC client configuration (slice 008, ADR-034).
 *
 * A single `UserManager` instance, shared by <AuthProvider> (main.tsx) and the
 * token bridge (auth/tokenBridge.ts) so both observe the same session.
 *
 * Local-Dex quirk: Dex's configured `issuer` is a container-network hostname
 * (`http://dex:5556/dex`, matching the backend's OIDC_ISSUER) baked into every
 * token's `iss` claim — the browser cannot resolve it. Standard `.well-known`
 * discovery from the browser-reachable URL would therefore return endpoint URLs
 * (authorization_endpoint, token_endpoint, ...) the browser can never reach. When
 * no real VITE_OIDC_AUTHORITY has been configured (i.e. we're pointed at local
 * Dex), the OIDC endpoints are hand-seeded at the browser-reachable host URL
 * instead of discovered, while `metadata.issuer` still matches what's actually in
 * the tokens. Any real OIDC provider (VITE_OIDC_AUTHORITY set) uses normal
 * `.well-known` discovery — this is not a provider-specific code path, only the
 * *default values* happen to describe today's local Dex setup.
 */
import { UserManager, WebStorageStateStore } from 'oidc-client-ts'

// `||`, not `??`: a Docker `ARG` with no default becomes an empty string when
// passed through to `ENV` (not "unset"), so Vite bakes `import.meta.env.VITE_*`
// as `""` rather than `undefined` for an unconfigured build. `??` would accept
// that empty string as "configured" and silently turn every seeded endpoint
// below into a same-origin relative path — treat any falsy value as absent.
const rawAuthority = import.meta.env.VITE_OIDC_AUTHORITY || undefined
const authority = rawAuthority || 'http://localhost:5556/dex'
const issuer = import.meta.env.VITE_OIDC_ISSUER || (rawAuthority ? authority : 'http://dex:5556/dex')
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID || 'gamebook'

export const userManager = new UserManager({
  authority: issuer,
  client_id: clientId,
  redirect_uri: `${window.location.origin}/callback`,
  scope: 'openid profile email',
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  automaticSilentRenew: true,
  ...(issuer !== authority
    ? {
        metadata: {
          issuer,
          authorization_endpoint: `${authority}/auth`,
          token_endpoint: `${authority}/token`,
          jwks_uri: `${authority}/keys`,
        },
      }
    : {}),
})
