"""Test: graceful OIDC degradation when JWKS endpoint is unreachable (T017 / SC-006).

Scenarios covered:
  1. JWKS fetch raises httpx.ConnectError → new sign-in → 503 auth_unavailable.
  2. Token already in the validated-token cache → accepted (graceful degradation).

These are unit tests that mock JWKS fetching — no real OIDC provider needed.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from jose import jwt as jose_jwt


# ---------------------------------------------------------------------------
# Helpers: generate a test JWT (RS256 with a throwaway key)
# ---------------------------------------------------------------------------

def _make_test_jwt(sub: str = "test-user", exp: int | None = None) -> tuple[str, str]:
    """Return (token, kid) for testing. Uses a pre-generated RSA key pair."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    from jose.utils import base64url_encode
    import struct

    pub_numbers = private_key.public_key().public_numbers()

    def _int_to_bytes(n: int) -> bytes:
        length = (n.bit_length() + 7) // 8
        return n.to_bytes(length, "big")

    if exp is None:
        exp = int(time.time()) + 3600

    payload = {
        "sub": sub,
        "aud": "gamebook",
        "iss": "http://localhost:5556/dex",
        "exp": exp,
        "iat": int(time.time()),
        "jti": "test-jti-" + str(sub),
    }

    # Sign with private key (RS256)
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PrivateFormat,
        NoEncryption,
    )
    pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())

    kid = "test-key-1"
    token = jose_jwt.encode(payload, pem, algorithm="RS256", headers={"kid": kid})
    return token, kid


@pytest.mark.asyncio
async def test_new_signin_503_when_jwks_unreachable():
    """When JWKS is unreachable, a new sign-in gets 503 auth_unavailable."""
    import os

    # Reset OIDC module-level cache
    import gamebook_web.auth.oidc_auth as oidc_mod
    oidc_mod._JWKS_CACHE = None
    oidc_mod._JWKS_CACHE_FETCHED_AT = 0.0
    oidc_mod._VALIDATED_TOKEN_CACHE.clear()

    token, kid = _make_test_jwt()

    with (
        patch.dict(
            os.environ,
            {
                "OIDC_JWKS_URI": "http://unreachable-oidc:5556/keys",
                "OIDC_AUDIENCE": "gamebook",
                "OIDC_ISSUER": "http://unreachable-oidc:5556",
                "GAMEBOOK_DEV_MODE": "0",
            },
        ),
        patch(
            "gamebook_web.auth.oidc_auth._fetch_jwks",
            side_effect=httpx.ConnectError("Connection refused"),
        ),
    ):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await oidc_mod.get_current_account(
                authorization=f"Bearer {token}"
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail["error"]["code"] == "auth_unavailable"


@pytest.mark.asyncio
async def test_cached_token_accepted_when_jwks_unreachable():
    """A token in the validated cache is accepted even when JWKS is unreachable."""
    import os

    import gamebook_web.auth.oidc_auth as oidc_mod
    oidc_mod._JWKS_CACHE = None
    oidc_mod._JWKS_CACHE_FETCHED_AT = 0.0
    oidc_mod._VALIDATED_TOKEN_CACHE.clear()

    exp = int(time.time()) + 3600
    token, _ = _make_test_jwt(sub="cached-user", exp=exp)

    # Pre-populate the cache with this token
    oidc_mod._cache_validated_token(token, exp, "account-id-from-cache")

    # Now JWKS is unreachable — but the token is in cache
    with (
        patch.dict(
            os.environ,
            {
                "OIDC_JWKS_URI": "http://unreachable-oidc:5556/keys",
                "OIDC_AUDIENCE": "gamebook",
                "GAMEBOOK_DEV_MODE": "0",
            },
        ),
        patch(
            "gamebook_web.auth.oidc_auth._fetch_jwks",
            side_effect=httpx.ConnectError("Connection refused"),
        ),
    ):
        account = await oidc_mod.get_current_account(authorization=f"Bearer {token}")
        assert account.account_id == "account-id-from-cache"


@pytest.mark.asyncio
async def test_expired_token_rejected_even_in_cache():
    """An expired token is rejected even if it was previously cached."""
    import os

    import gamebook_web.auth.oidc_auth as oidc_mod
    oidc_mod._JWKS_CACHE = None
    oidc_mod._JWKS_CACHE_FETCHED_AT = 0.0
    oidc_mod._VALIDATED_TOKEN_CACHE.clear()

    exp = int(time.time()) - 10  # already expired
    token, _ = _make_test_jwt(sub="expired-user", exp=exp)

    # Cache it with expired exp
    oidc_mod._cache_validated_token(token, exp, "stale-account")

    with (
        patch.dict(
            os.environ,
            {
                "OIDC_JWKS_URI": "http://localhost:5556/keys",
                "OIDC_AUDIENCE": "gamebook",
                "GAMEBOOK_DEV_MODE": "0",
            },
        ),
    ):
        from fastapi import HTTPException

        # Lookup should return None (expired)
        result = oidc_mod._lookup_validated_token(token, exp)
        assert result is None, "Expired token must not be served from cache"
