"""Tests for production safety guards (FR-008, FR-009, FR-010).

Verifies:
  - Server raises at boot when ENV=production + GAMEBOOK_DEV_MODE=1
  - /docs, /redoc, /openapi.json return 404 when ENV=production
  - Auth failures are logged with path and reason
  - Dev mode is skipped when ENV=production (fail-closed)
"""

from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gamebook_web.api.app import _check_production_dev_mode_clash


# ---------------------------------------------------------------------------
# T016: startup guard — refuse ENV=production + GAMEBOOK_DEV_MODE=1
# ---------------------------------------------------------------------------

class TestProductionDevModeGuard:
    def test_raises_when_production_and_dev_mode_enabled(self) -> None:
        with (
            patch.dict(os.environ, {"ENV": "production", "GAMEBOOK_DEV_MODE": "1"}),
            pytest.raises(RuntimeError, match="Refusing to start"),
        ):
            _check_production_dev_mode_clash()

    def test_raises_when_dev_mode_true_string(self) -> None:
        with (
            patch.dict(os.environ, {"ENV": "production", "GAMEBOOK_DEV_MODE": "true"}),
            pytest.raises(RuntimeError, match="Refusing to start"),
        ):
            _check_production_dev_mode_clash()

    def test_passes_when_not_production(self) -> None:
        with patch.dict(os.environ, {"ENV": "development", "GAMEBOOK_DEV_MODE": "1"}):
            _check_production_dev_mode_clash()  # must not raise

    def test_passes_when_production_and_dev_mode_off(self) -> None:
        with patch.dict(os.environ, {"ENV": "production", "GAMEBOOK_DEV_MODE": "0"}):
            _check_production_dev_mode_clash()  # must not raise

    def test_passes_when_no_env_vars(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("ENV", "GAMEBOOK_DEV_MODE")}
        with patch.dict(os.environ, env, clear=True):
            _check_production_dev_mode_clash()  # must not raise


# ---------------------------------------------------------------------------
# T017: /docs, /redoc, /openapi.json disabled when ENV=production
# ---------------------------------------------------------------------------

class TestDocumentationDisabledInProduction:
    """Requires a fresh FastAPI app instance built with ENV=production."""

    def _make_production_app(self):
        """Build a fresh app module with ENV=production set at import time."""
        import importlib
        import gamebook_web.api.app as app_module

        with patch.dict(os.environ, {"ENV": "production"}):
            importlib.reload(app_module)
            return app_module.app

    def test_docs_hidden_in_production(self) -> None:
        prod_app = self._make_production_app()
        client = TestClient(prod_app, raise_server_exceptions=False)
        resp = client.get("/docs")
        assert resp.status_code == 404

    def test_redoc_hidden_in_production(self) -> None:
        prod_app = self._make_production_app()
        client = TestClient(prod_app, raise_server_exceptions=False)
        resp = client.get("/redoc")
        assert resp.status_code == 404

    def test_openapi_hidden_in_production(self) -> None:
        prod_app = self._make_production_app()
        client = TestClient(prod_app, raise_server_exceptions=False)
        resp = client.get("/openapi.json")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T018: auth failures are logged with path and reason
# ---------------------------------------------------------------------------

class TestAuthFailureLogging:
    def test_missing_token_is_logged(self, caplog) -> None:
        """Missing Authorization header triggers a warning log."""
        from gamebook_web.api.app import app
        from starlette.testclient import TestClient

        with caplog.at_level(logging.WARNING, logger="gamebook_web.auth.dev_auth"):
            # No dev mode, no token → should log warning
            env = {k: v for k, v in os.environ.items() if k != "GAMEBOOK_DEV_MODE"}
            env["GAMEBOOK_DEV_MODE"] = "0"
            with patch.dict(os.environ, env, clear=True):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/me/game")

        assert resp.status_code == 401
        assert any("auth failed" in r.message for r in caplog.records), (
            f"Expected 'auth failed' log, got: {[r.message for r in caplog.records]}"
        )

    def test_invalid_token_is_logged(self, caplog) -> None:
        """Invalid Bearer token triggers a warning log."""
        from gamebook_web.api.app import app

        with caplog.at_level(logging.WARNING, logger="gamebook_web.auth.dev_auth"):
            env = {**os.environ, "GAMEBOOK_DEV_MODE": "0"}
            with patch.dict(os.environ, env):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.get("/me/game", headers={"Authorization": "Bearer wrong-token"})

        assert resp.status_code == 401
        assert any("auth failed" in r.message for r in caplog.records)

    def test_log_includes_path(self, caplog) -> None:
        """Auth failure log must include the request path."""
        from gamebook_web.api.app import app

        with caplog.at_level(logging.WARNING, logger="gamebook_web.auth.dev_auth"):
            env = {**os.environ, "GAMEBOOK_DEV_MODE": "0"}
            with patch.dict(os.environ, env):
                client = TestClient(app, raise_server_exceptions=False)
                client.get("/me/game/character", headers={"Authorization": "Bearer bad"})

        path_logged = any("/me/game/character" in r.message for r in caplog.records)
        assert path_logged, f"Path not in logs: {[r.message for r in caplog.records]}"
