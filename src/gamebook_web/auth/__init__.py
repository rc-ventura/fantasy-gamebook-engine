"""Auth package — re-exports Account and get_current_account.

The concrete implementation is selected at startup:
  - GAMEBOOK_DEV_MODE=1  → dev_auth stub (tests / local dev without OIDC)
  - otherwise            → oidc_auth (real JWT/JWKS validation)

Routes import ``Account`` and ``get_current_account`` from here or directly
from ``dev_auth`` (for backward compat with slice 003 routes that we must
not modify).  ``app.py`` installs a ``dependency_override`` to route the dev
stub to the real OIDC implementation when not in dev mode.
"""

from gamebook_web.auth.dev_auth import Account  # noqa: F401 — shared type

__all__ = ["Account"]
