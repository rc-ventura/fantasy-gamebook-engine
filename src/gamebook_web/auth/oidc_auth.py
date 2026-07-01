"""Real OIDC authentication — JWT/JWKS validation (slice 004).

Replaces ``dev_auth.py`` at the auth seam.  Routes continue to depend on
``get_current_account``; only the implementation changes.

Environment variables
---------------------
OIDC_JWKS_URI   — JWKS endpoint (e.g. http://dex:5556/dex/keys)
OIDC_AUDIENCE   — expected ``aud`` claim (e.g. "gamebook")
OIDC_ISSUER     — expected ``iss`` claim (e.g. "http://dex:5556/dex")
GAMEBOOK_DEV_MODE — if "1", fall back to dev stub (testing convenience)

Graceful degradation (T017)
---------------------------
If the JWKS endpoint is unreachable, new sign-ins receive ``503 auth_unavailable``.
Tokens already validated within the last ``VALIDATED_TOKEN_TTL`` seconds continue
to be accepted from an in-memory cache keyed on (signature-hash, exp).

JWKS key cache TTL: 5 minutes (refreshed on 404 key-id to handle key rotation).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Header, HTTPException, status
from jose import JWTError, jwk, jwt
from jose.exceptions import ExpiredSignatureError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Account type — same interface as dev_auth.Account
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Account:
    """Authenticated player account resolved from the OIDC token subject."""
    account_id: str


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_JWKS_CACHE: dict[str, Any] | None = None
_JWKS_CACHE_FETCHED_AT: float = 0.0
_JWKS_CACHE_TTL = 300  # 5 minutes

# Serialises access to the module-level caches.  Async request handlers can
# interleave at ``await`` points, so the caches are guarded by an asyncio.Lock
# to prevent torn reads/writes and concurrent mutation during GC.
#
# Created lazily on first use rather than at import time: an ``asyncio.Lock``
# binds to the running event loop on first acquire, so constructing it at import
# (before any loop exists) risks a ``RuntimeError`` if the module is first used
# from a different loop than the one that first acquired it (CWE-362).
_CACHE_LOCK: asyncio.Lock | None = None


def _get_cache_lock() -> asyncio.Lock:
    """Return the module cache lock, creating it lazily on first use."""
    global _CACHE_LOCK
    if _CACHE_LOCK is None:
        _CACHE_LOCK = asyncio.Lock()
    return _CACHE_LOCK

# Short-term validated-token cache for graceful degradation.
# Key: (token-signature-hash, exp), Value: account_id.  An OrderedDict gives
# us O(1) LRU eviction so the cache cannot grow without bound (CWE-400).
_VALIDATED_TOKEN_CACHE: OrderedDict[tuple[str, int], str] = OrderedDict()
VALIDATED_TOKEN_TTL = 300  # seconds; allows tokens to ride through a short OIDC outage
# Hard cap on cached tokens — bounds memory under a token-flood / re-auth storm.
_VALIDATED_TOKEN_CACHE_MAX = 10_000


def _token_cache_key(token: str, exp: int) -> tuple[str, int]:
    # Full SHA-256 digest (not truncated) for strong collision resistance.
    sig = hashlib.sha256(token.encode()).hexdigest()
    return (sig, exp)


def _cache_validated_token(token: str, exp: int, account_id: str) -> None:
    """Store a validated token. Caller must hold ``_CACHE_LOCK``."""
    key = _token_cache_key(token, exp)
    _VALIDATED_TOKEN_CACHE[key] = account_id
    _VALIDATED_TOKEN_CACHE.move_to_end(key)
    # Purge expired entries (simple GC)
    now = time.time()
    expired = [k for k in _VALIDATED_TOKEN_CACHE if k[1] < now]
    for k in expired:
        _VALIDATED_TOKEN_CACHE.pop(k, None)
    # Enforce the size cap by evicting the least-recently-used entries.
    while len(_VALIDATED_TOKEN_CACHE) > _VALIDATED_TOKEN_CACHE_MAX:
        _VALIDATED_TOKEN_CACHE.popitem(last=False)


def _lookup_validated_token(token: str, exp: int) -> str | None:
    """Return the cached account_id, or None. Caller must hold ``_CACHE_LOCK``."""
    key = _token_cache_key(token, exp)
    if exp < time.time():
        _VALIDATED_TOKEN_CACHE.pop(key, None)
        return None
    account_id = _VALIDATED_TOKEN_CACHE.get(key)
    if account_id is not None:
        _VALIDATED_TOKEN_CACHE.move_to_end(key)
    return account_id


async def _fetch_jwks(jwks_uri: str, force_refresh: bool = False) -> dict[str, Any]:
    """Fetch and cache the JWKS from the OIDC provider.

    Raises ``httpx.RequestError`` if the provider is unreachable.  Access to
    the module-level JWKS cache is serialised via ``_CACHE_LOCK``.
    """
    global _JWKS_CACHE, _JWKS_CACHE_FETCHED_AT

    lock = _get_cache_lock()

    # 1. Fast path: serve a fresh cache entry under the lock, then release it.
    async with lock:
        now = time.time()
        if not force_refresh and _JWKS_CACHE is not None and (now - _JWKS_CACHE_FETCHED_AT) < _JWKS_CACHE_TTL:
            return _JWKS_CACHE

    # 2. Cache miss: perform the network fetch WITHOUT holding the lock so that
    #    a slow/unresponsive OIDC provider cannot serialise all concurrent
    #    token validations behind the lock for up to the full timeout (CWE-400).
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(jwks_uri)
        response.raise_for_status()
        fetched = response.json()

    # 3. Re-acquire the lock only to publish the result.  Double-check that a
    #    concurrent fetch has not already populated a fresher entry.
    async with lock:
        now = time.time()
        if not force_refresh and _JWKS_CACHE is not None and (now - _JWKS_CACHE_FETCHED_AT) < _JWKS_CACHE_TTL:
            return _JWKS_CACHE
        _JWKS_CACHE = fetched
        _JWKS_CACHE_FETCHED_AT = time.time()
        return _JWKS_CACHE


async def _get_signing_key(jwks_uri: str, kid: str | None) -> Any:
    """Return the signing key matching ``kid`` (or the first key if no kid)."""
    jwks = await _fetch_jwks(jwks_uri)
    keys = jwks.get("keys", [])
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "auth_unavailable", "message": "OIDC key set is empty"}},
        )

    if kid is not None:
        matched = [k for k in keys if k.get("kid") == kid]
        if not matched:
            # Key might have been rotated — force refresh once
            jwks = await _fetch_jwks(jwks_uri, force_refresh=True)
            keys = jwks.get("keys", [])
            matched = [k for k in keys if k.get("kid") == kid]
        if matched:
            return jwk.construct(matched[0])

    # Fall back to first key
    return jwk.construct(keys[0])


# ---------------------------------------------------------------------------
# Account resolution (upsert on first access — deferred to AccountRepository
# which is imported at call time to avoid circular imports)
# ---------------------------------------------------------------------------

async def _resolve_account(sub: str) -> Account:
    """Upsert account row and return the Account with its DB id."""
    from gamebook_web.accounts import get_account_repository
    repo = get_account_repository()
    db_account = await repo.get_or_create(sub)
    return Account(account_id=db_account["account_id"])


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_current_account(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Account:
    """OIDC auth dependency: validate bearer JWT and resolve account.

    On JWKS fetch failure:
      - Token in validated-token cache → serve from cache (graceful degradation).
      - No cached token → 503 auth_unavailable.
    On invalid/expired token → 401 unauthenticated.
    """
    # Dev-mode fallback (testing convenience — never enabled in prod)
    dev_mode = os.getenv("GAMEBOOK_DEV_MODE", "0") in ("1", "true", "True")
    if dev_mode:
        from gamebook_web.auth.dev_auth import get_current_account as _dev_auth
        return await _dev_auth(authorization)

    jwks_uri = os.getenv("OIDC_JWKS_URI", "")
    audience = os.getenv("OIDC_AUDIENCE", "gamebook")
    issuer = os.getenv("OIDC_ISSUER", "")

    if not jwks_uri:
        _unauthenticated("OIDC_JWKS_URI not configured — set GAMEBOOK_DEV_MODE=1 for local dev")

    if authorization is None:
        _unauthenticated("Missing Authorization header")

    if not authorization.startswith("Bearer "):
        _unauthenticated("Authorization header must be 'Bearer <token>'")

    token = authorization[len("Bearer "):]

    # Decode header to find kid (without verification — just to select key)
    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        # Also get exp from unverified claims for cache lookup
        unverified_claims = jwt.get_unverified_claims(token)
        exp = int(unverified_claims.get("exp", 0))
    except (JWTError, ValueError, TypeError) as exc:
        _unauthenticated(f"Malformed token: {exc}")

    # Check validated-token cache (graceful degradation)
    async with _get_cache_lock():
        cached_account_id = _lookup_validated_token(token, exp)
    if cached_account_id:
        return Account(account_id=cached_account_id)

    # Fetch signing key (may raise on network error)
    try:
        signing_key = await _get_signing_key(jwks_uri, kid)
    except httpx.RequestError as exc:
        logger.warning("OIDC JWKS fetch failed — provider unreachable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "auth_unavailable", "message": "Authentication service temporarily unavailable"}},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("JWKS key fetch error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "auth_unavailable", "message": "Authentication service temporarily unavailable"}},
        )

    # Validate JWT
    try:
        options = {"verify_aud": bool(audience), "verify_iss": bool(issuer)}
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            audience=audience if audience else None,
            issuer=issuer if issuer else None,
            options=options,
        )
    except ExpiredSignatureError:
        _unauthenticated("Token has expired")
    except JWTError as exc:
        _unauthenticated(f"Token validation failed: {exc}")

    sub: str = claims.get("sub", "")
    if not sub:
        _unauthenticated("Token missing 'sub' claim")

    # Resolve or create the account
    try:
        account = await _resolve_account(sub)
    except Exception as exc:
        logger.exception("Account resolution failed for sub=%s: %s", sub, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "internal_error", "message": "Account resolution failed"}},
        )

    # Cache for graceful degradation
    async with _get_cache_lock():
        _cache_validated_token(token, exp, account.account_id)

    return account


def _unauthenticated(message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthenticated", "message": message}},
        headers={"WWW-Authenticate": "Bearer"},
    )
