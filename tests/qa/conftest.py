"""QA test configuration.

Makes the sibling ``_audit`` helper module importable from the QA test modules.
Under pytest's ``importlib`` import mode (see ``pyproject.toml``) the test
directory is *not* placed on ``sys.path`` automatically, so a plain
``import _audit`` from a test module would fail. Inserting this directory here —
``conftest.py`` is imported before the test modules in the same directory —
fixes that without polluting the global path for the rest of the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

_QA_DIR = str(Path(__file__).resolve().parent)
if _QA_DIR not in sys.path:
    sys.path.insert(0, _QA_DIR)
