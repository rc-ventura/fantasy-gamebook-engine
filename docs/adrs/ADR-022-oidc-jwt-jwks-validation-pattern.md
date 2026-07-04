# ADR-022: OIDC JWT/JWKS validation + graceful degradation strategy

**Status**: Accepted (amended 2026-07-02 — see "Amendment: PyJWT migration" below) | **Date**: 2026-06-28 | **Branch**: `feat/004-auth-obs`

> Renumbered from slice 004's ADR-017 by spec 006 (ADR-020 numbering policy) — the original numbers collided with ADRs 017-019 on `dev`.

## Context

Slice 004 replaces the development auth stub (`dev_auth.py`) with real OIDC authentication. The requirements are:

1. Validate JWT bearer tokens (signature, `exp`, `aud`, `iss`) against a JWKS endpoint.
2. Resolve the authenticated account from the token `sub` (upsert on first access).
3. Degrade gracefully when the OIDC provider is temporarily unreachable.
4. Keep the auth seam transparent — routes that currently `Depends(dev_auth.get_current_account)` must continue to work unchanged.

Options evaluated:

| Option | Notes |
|---|---|
| **python-jose + httpx** (chosen) | Lightweight JWT library; JWKS parsing built-in; httpx already in project |
| PyJWT | Similar; no built-in JWKS key set fetching |
| authlib | Heavier; designed for full OAuth2 server-side flows |
| python-keycloak | Vendor-specific |

For the auth seam, two options:
- **Modify routes**: change imports in `play.py` / `combat.py` — violates "do not touch 003 routes"
- **FastAPI dependency override** (chosen): `app.dependency_overrides[dev_auth.get_current_account] = oidc_auth.get_current_account` installed in the lifespan

## Decision

### JWT validation (`oidc_auth.py`)

1. Decode the header (without verification) to extract `kid`.
2. Fetch JWKS from `OIDC_JWKS_URI` (cached for 5 minutes; refreshed on unknown `kid`).
3. Construct the signing key and validate: RS256/ES256 signature, `exp`, `aud` == `OIDC_AUDIENCE`, `iss` == `OIDC_ISSUER`.
4. Resolve `sub` → `account` row (upsert via `AccountRepository.get_or_create`).

### Graceful degradation

Two-tier cache:
- **JWKS cache** (TTL 5 min): avoids hitting the OIDC provider on every request.
- **Validated-token cache** (keyed on `sha256(token)[:16]` + `exp`, TTL = token `exp`): tokens validated recently survive a short OIDC outage without re-validation.

On JWKS fetch failure (`httpx.RequestError`):
- Token in validated-token cache → served (already authed → read-only session continues).
- No cached token → `503 auth_unavailable` (new sign-in fails cleanly; no data loss).

### Auth seam

The lifespan in `app.py` installs:
```python
app.dependency_overrides[dev_auth.get_current_account] = oidc_auth.get_current_account
```
when `GAMEBOOK_DEV_MODE` is unset and `OIDC_JWKS_URI` is configured. Tests continue using the dev stub by setting `GAMEBOOK_DEV_MODE=1` (default in the test environment).

## Consequences

**Positive**:
- Routes in play.py / combat.py are completely unchanged (swap boundary #3 honoured).
- No PII stored: only `sub` (opaque OIDC subject) + `created_at` in the `account` table.
- Graceful degradation allows already-signed-in players to continue during short outages.
- JWKS key rotation is handled: on `kid` miss, the cache is force-refreshed once.

**Negative**:
- Validated-token cache is in-process memory; tokens remain valid across a restart only if the OIDC provider is reachable again (acceptable tradeoff).
- `python-jose` is in maintenance mode upstream; if rotated, the swap is isolated to `oidc_auth.py`.

## Related

- T003 (OIDC auth implementation), T017 (graceful degradation tests)
- ADR-011 (auth seam established in slice 003)

---

## Amendment: PyJWT migration (2026-07-02)

**Status**: Accepted | **Date**: 2026-07-02 | **Branch**: `feat/006-remediation`

### Context

The original decision chose `python-jose` for JWT validation. By 2026, `python-jose` is in maintenance mode — no active development, and CVE-2024-33664 (algorithm confusion) and CVE-2024-33663 (PJWS/JWS input confusion) were disclosed. The SDD final review (cycle 1) flagged this as a dependency risk.

### Decision

Migrate from `python-jose` to `PyJWT` (`>=2.8.0,<3.0`):

- `import jwt` replaces `from jose import jwt`
- `jwt.PyJWK` replaces `jose.backends.cryptography_backend.CryptographyRSAKey` for JWKS key construction
- `jwt.exceptions` replaces `jose.exceptions` for error handling
- Algorithms explicitly restricted to `["RS256", "ES256"]` — no `none`, no HS256 (prevents algorithm confusion)
- PyJWT 2.4.0+ includes the fix for CVE-2022-29217 (algorithm confusion)

### Consequences

**Positive**:
- Actively maintained library with timely CVE patches
- Simpler API — no separate key construction step (`jwt.PyJWK` handles JWKS directly)
- Algorithm-confusion hardening via explicit `algorithms=` parameter (required by PyJWT)

**Negative**:
- `joserfc` (the maintained successor to `python-jose`) is still pulled in transitively via `authlib` ← `fastmcp_slim[client]`, but is not used by application auth code — the app uses PyJWT directly. This expands the dependency tree but does not create a vulnerability.

### What changed in the code

- `pyproject.toml`: `python-jose[cryptography]` → `pyjwt>=2.8.0,<3.0`
- `src/gamebook_web/auth/oidc_auth.py`: `import jwt` / `from jwt import PyJWK` / `jwt.exceptions.*`
- Tests: `tests/server/test_oidc_fail_closed.py`, `tests/server/test_auth_degradation.py` updated to use `pyjwt` directly
- `VALIDATED_TOKEN_TTL` reduced from 300s to 60s (H-03 — revocation gap)
