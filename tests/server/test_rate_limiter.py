"""Rate-limiter key function (T095, SC-028, FR-046).

Authenticated requests must be keyed on the account (stable across IPs);
unauthenticated requests fall back to the client IP. ``X-Forwarded-For`` is
honoured only behind an explicitly trusted proxy — otherwise it is spoofable.
"""

from __future__ import annotations

from starlette.requests import Request

from gamebook_web.api.limiter import rate_limit_key
from gamebook_web.auth.dev_auth import DEV_ACCOUNT_ID, DEV_TOKEN

CLIENT_IP = "203.0.113.7"


def _make_request(headers: dict[str, str] | None = None, client_ip: str = CLIENT_IP) -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/me/game/turn",
        "headers": raw_headers,
        "client": (client_ip, 54321),
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    return Request(scope)


class TestRateLimitKey:
    def test_authenticated_request_keys_on_account(self):
        request = _make_request({"Authorization": f"Bearer {DEV_TOKEN}"})
        assert rate_limit_key(request) == f"account:{DEV_ACCOUNT_ID}"

    def test_account_key_is_stable_across_ips(self):
        """The same account gets the same bucket from different addresses."""
        key_a = rate_limit_key(
            _make_request({"Authorization": f"Bearer {DEV_TOKEN}"}, client_ip="198.51.100.1")
        )
        key_b = rate_limit_key(
            _make_request({"Authorization": f"Bearer {DEV_TOKEN}"}, client_ip="198.51.100.2")
        )
        assert key_a == key_b == f"account:{DEV_ACCOUNT_ID}"

    def test_unauthenticated_request_falls_back_to_ip(self):
        request = _make_request()
        assert rate_limit_key(request) == CLIENT_IP

    def test_invalid_token_does_not_mint_a_fresh_bucket(self):
        """Random invalid bearer tokens must NOT bypass the IP bucket."""
        request = _make_request({"Authorization": "Bearer forged-token-123"})
        assert rate_limit_key(request) == CLIENT_IP

    def test_forwarded_for_ignored_without_trusted_proxy(self, monkeypatch):
        monkeypatch.delenv("GAMEBOOK_TRUSTED_PROXY", raising=False)
        request = _make_request({"X-Forwarded-For": "10.0.0.99"})
        assert rate_limit_key(request) == CLIENT_IP

    def test_forwarded_for_honoured_behind_trusted_proxy(self, monkeypatch):
        monkeypatch.setenv("GAMEBOOK_TRUSTED_PROXY", "1")
        request = _make_request({"X-Forwarded-For": "10.0.0.99, 172.16.0.1"})
        assert rate_limit_key(request) == "10.0.0.99"

    def test_account_key_wins_over_forwarded_for(self, monkeypatch):
        monkeypatch.setenv("GAMEBOOK_TRUSTED_PROXY", "1")
        request = _make_request(
            {
                "Authorization": f"Bearer {DEV_TOKEN}",
                "X-Forwarded-For": "10.0.0.99",
            }
        )
        assert rate_limit_key(request) == f"account:{DEV_ACCOUNT_ID}"
