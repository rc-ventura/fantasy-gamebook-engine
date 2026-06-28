# python-jose JWKS caching and graceful degradation pattern

**Date**: 2026-06-28 | **Feature**: 004-accounts-hardening-obs

## The pattern

When validating OIDC JWTs, the JWKS endpoint is fetched on every new token validation. Caching the key set avoids hitting the OIDC provider on every request. `python-jose` does NOT cache JWKS responses internally — the application must implement its own cache.

### Key rotation

JWTs include a `kid` (key ID) header. On a cache miss for a given `kid` (after key rotation by the OIDC provider), force-refresh the cache once. This prevents a stale cache from permanently rejecting tokens signed with a new key:

```python
matched = [k for k in keys if k.get("kid") == kid]
if not matched:
    jwks = await _fetch_jwks(jwks_uri, force_refresh=True)
    keys = jwks.get("keys", [])
    matched = [k for k in keys if k.get("kid") == kid]
```

### Graceful degradation cache

To survive a short OIDC outage without dropping signed-in players, maintain a short-term cache of recently validated tokens keyed on `sha256(raw_token)[:16] + exp`. If the JWKS fetch raises `httpx.RequestError`, look up this cache first. This allows already-authenticated sessions to continue read-only until their tokens expire naturally.

### Never store the raw token in logs/spans

The token cache key uses a hash prefix (`sha256[:16]`) rather than the raw JWT. This prevents accidentally logging a bearer token that could be replayed.

## FastAPI dependency override for auth seam swap

Routes in existing code `Depends(dev_auth.get_current_account)`. To swap to OIDC without modifying those routes:

```python
app.dependency_overrides[dev_auth.get_current_account] = oidc_auth.get_current_account
```

This is installed in the FastAPI lifespan, not at module import time, so tests can override it before the lifespan runs.

## SQLAlchemy AsyncSession and double-begin

When building a snapshot that is then written in the same session (for atomic `save_slot`), do not open a new `session.begin()` context inside an already-begun transaction. Extract the read logic into a helper that takes the session as a parameter, then call it inside the transaction context from the caller.
