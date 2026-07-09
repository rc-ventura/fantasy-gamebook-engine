# Contract: SPA ↔ OIDC Provider (Dex) — 008

**Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

This feature adds no new backend HTTP routes (see [data-model.md](../data-model.md)) —
its external interface is the OIDC provider itself. This document is the contract the
frontend and the Dex configuration must both honor. Full rationale:
[ADR-034](../../../docs/adrs/ADR-034-oidc-frontend-spa-pkce-public-client.md),
[research.md](../research.md).

---

## Dex client registration (`docker/dex/config.yaml`)

```yaml
staticClients:
  - id: gamebook
    public: true              # was: secret: gamebook-secret-dev (unused — dropped)
    name: "Gamebook Dev Client"
    redirectURIs:
      - http://localhost:5173/callback   # Vite dev server (frontend/vite.config.ts, port 5173)
      - http://localhost:8080/callback   # docker-compose `gameobs` profile frontend (8080:80)
```

The `password` connector / `staticPasswords` block and `issuer` are unchanged.

---

## Authorization request (browser → Dex)

`GET {issuer}/auth` (issuer as seen by the *browser*, i.e. `http://localhost:5556/dex`
in the dev/compose setup — distinct from `OIDC_ISSUER` as seen by the backend
container, `http://dex:5556/dex`; both point at the same Dex instance, see ADR-022's
issuer-mismatch note).

| Param | Value |
|---|---|
| `client_id` | `gamebook` |
| `redirect_uri` | the origin's `/callback` (see client registration above) |
| `response_type` | `code` |
| `scope` | `openid profile email` |
| `state` | library-generated, one-time use |
| `code_challenge` / `code_challenge_method` | PKCE, `S256`, library-generated |

## Token request (browser → Dex, from the `/callback` handler)

`POST {issuer}/token` — no `client_secret` (public client). Body includes
`grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier`, `client_id`.

**Response** (subset the app relies on):

```json
{
  "id_token": "<JWT>",
  "access_token": "<opaque or JWT — not used by this app>",
  "expires_in": 3600
}
```

## What the SPA forwards to this project's backend

`Authorization: Bearer <id_token>` — unchanged shape from the dev stub
(`frontend/src/api/client.ts`'s `request()` already attaches
`Authorization: Bearer <token>`; only where `<token>` comes from changes).

Expected `id_token` claims (validated by `src/gamebook_web/auth/oidc_auth.py`,
unchanged):

| Claim | Expected value | Backend env var |
|---|---|---|
| `iss` | `http://dex:5556/dex` (compose-network issuer) | `OIDC_ISSUER` |
| `aud` | `gamebook` | `OIDC_AUDIENCE` |
| `exp` | required, checked | — |
| `kid` (header) | must match a key in `{OIDC_JWKS_URI}` | `OIDC_JWKS_URI=http://dex:5556/dex/keys` |
| `sub` | resolved to `account_id` via `AccountRepository.get_or_create` | — |

No backend env vars change for this slice.

## Backward compatibility

`GAMEBOOK_DEV_MODE=1` (`dev_auth.py`) and the frontend's dev token-paste UI
(`import.meta.env.DEV`-gated, FR-009) continue to work unchanged for
local development without Dex running — this feature does not remove that path, only
adds the real one alongside it and hides the fallback from production builds.
