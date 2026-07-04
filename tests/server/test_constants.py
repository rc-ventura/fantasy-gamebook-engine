"""Test-only auth constants (T031, ADR-022).

The magic dev credential is deliberately NOT a production constant on
``gamebook_web.auth.dev_auth`` — it exists there only when
``GAMEBOOK_DEV_MODE`` is enabled.  Tests keep their own copy here so nothing in
``src/`` ships a hardcoded, well-known bearer string.

This module is named ``test_constants`` but defines no tests; pytest collects it
without error because it contains no ``test_`` callables.
"""

from __future__ import annotations

# Matches the value dev_auth accepts when GAMEBOOK_DEV_MODE is enabled.
DEV_TOKEN = "dev-token"
DEV_ACCOUNT_ID = "dev-account"
DEV_CAMPAIGN_ID = "dev-campaign"

# Standard Authorization header for authenticated test requests.
AUTH_HEADER = {"Authorization": f"Bearer {DEV_TOKEN}"}
