"""Fail-closed OIDC auth tests (T036, SC-009, ADR-022).

Covers the cycle-1 remediation guarantees for slice 004's auth seam:

  * The app REFUSES TO START when neither OIDC nor dev mode is configured
    (T030) — no silent public API reachable with the well-known dev token.
  * A JWT with no ``exp`` is rejected ``401`` (T033).
  * A JWT with no ``kid`` is rejected ``401`` — no fallback to an arbitrary
    JWKS key (T034).
  * A JWT with the wrong ``iss`` is rejected ``401``; ``iss`` is always verified
    and ``OIDC_ISSUER`` is mandatory (T032).
  * The validated-token cache key is derived from a token hash + ``exp`` (T035),
    never the raw token.

The token-rejection cases exercise ``oidc_auth.get_current_account`` directly
with a mocked JWKS so no live OIDC provider is required.
"""

from __future__ import annotations

import asyncio
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwk, jwt
from starlette.testclient import TestClient

from gamebook_web.auth import oidc_auth

ISSUER = "https://issuer.example"
AUDIENCE = "gamebook"
KID = "test-key-1"


# ---------------------------------------------------------------------------
# RSA keypair + JWKS helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="module")
def jwks(rsa_pem: str) -> dict:
    pub = jwk.construct(rsa_pem, "RS256").public_key().to_dict()
    pub["kid"] = KID
    return {"keys": [pub]}


def _mint(pem: str, claims: dict, *, kid: str | None = KID) -> str:
    headers = {"kid": kid} if kid is not None else None
    return jwt.encode(claims, pem, algorithm="RS256", headers=headers)


@pytest.fixture
def oidc_env(monkeypatch, jwks):
    """Configure real-OIDC mode and stub the JWKS fetch."""
    monkeypatch.delenv("GAMEBOOK_DEV_MODE", raising=False)
    monkeypatch.setenv("OIDC_JWKS_URI", "https://issuer.example/keys")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", AUDIENCE)

    async def _fake_fetch(uri: str, force_refresh: bool = False) -> dict:
        return jwks

    monkeypatch.setattr(oidc_auth, "_fetch_jwks", _fake_fetch)
    # Isolate the module-level validated-token cache per test.
    oidc_auth._VALIDATED_TOKEN_CACHE.clear()
    yield
    oidc_auth._VALIDATED_TOKEN_CACHE.clear()


def _call(token: str) -> None:
    """Invoke the auth dependency with a Bearer token; propagate HTTPException."""
    asyncio.run(oidc_auth.get_current_account(authorization=f"Bearer {token}"))


# ---------------------------------------------------------------------------
# T030 — boot refusal when no auth configured
# ---------------------------------------------------------------------------

def test_boot_without_oidc_or_dev_mode_refuses(monkeypatch):
    """Lifespan must raise rather than serve a public API with the dev stub."""
    monkeypatch.delenv("GAMEBOOK_DEV_MODE", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URI", raising=False)

    from gamebook_web.api.app import app

    app.dependency_overrides.clear()
    with pytest.raises(RuntimeError, match="no authentication configured"):
        with TestClient(app):
            pass


def test_boot_with_oidc_but_no_issuer_refuses(monkeypatch):
    """OIDC without OIDC_ISSUER is a misconfiguration — refuse to start (T032)."""
    monkeypatch.delenv("GAMEBOOK_DEV_MODE", raising=False)
    monkeypatch.setenv("OIDC_JWKS_URI", "https://issuer.example/keys")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)

    from gamebook_web.api.app import app

    app.dependency_overrides.clear()
    with pytest.raises(RuntimeError, match="OIDC_ISSUER"):
        with TestClient(app):
            pass


# ---------------------------------------------------------------------------
# T033 / T034 / T032 — token rejection paths
# ---------------------------------------------------------------------------

def test_token_without_exp_is_rejected(oidc_env, rsa_pem):
    token = _mint(rsa_pem, {"sub": "u1", "aud": AUDIENCE, "iss": ISSUER})  # no exp
    with pytest.raises(HTTPException) as exc:
        _call(token)
    assert exc.value.status_code == 401


def test_token_without_kid_is_rejected(oidc_env, rsa_pem):
    token = _mint(
        rsa_pem,
        {"sub": "u1", "exp": 9999999999, "aud": AUDIENCE, "iss": ISSUER},
        kid=None,
    )
    with pytest.raises(HTTPException) as exc:
        _call(token)
    assert exc.value.status_code == 401


def test_token_with_wrong_issuer_is_rejected(oidc_env, rsa_pem):
    token = _mint(
        rsa_pem,
        {"sub": "u1", "exp": 9999999999, "aud": AUDIENCE, "iss": "https://evil.example"},
    )
    with pytest.raises(HTTPException) as exc:
        _call(token)
    assert exc.value.status_code == 401


def test_valid_token_missing_kid_does_not_fall_back_to_first_key(oidc_env, rsa_pem, jwks):
    """Even with exactly one JWKS key present, a kid-less token is refused (T034)."""
    assert len(jwks["keys"]) == 1
    token = _mint(
        rsa_pem,
        {"sub": "u1", "exp": 9999999999, "aud": AUDIENCE, "iss": ISSUER},
        kid=None,
    )
    with pytest.raises(HTTPException) as exc:
        _call(token)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# T035 — validated-token cache key format
# ---------------------------------------------------------------------------

def test_cache_key_is_token_hash_plus_exp_not_raw_token():
    token = "some.jwt.token"
    exp = 1_800_000_000
    key = oidc_auth._token_cache_key(token, exp)

    assert isinstance(key, tuple) and len(key) == 2
    key_hash, key_exp = key
    # Keyed on a SHA-256 digest of the token (not the raw token) plus exp, so the
    # raw bearer string is never used as a dict key.  The impl keeps the full
    # digest (stronger than ADR-022's suggested sha256[:16]); still token-derived.
    assert key_exp == exp
    assert key_hash != token
    assert key_hash == hashlib.sha256(token.encode()).hexdigest()
