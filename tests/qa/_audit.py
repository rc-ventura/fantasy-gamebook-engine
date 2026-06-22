"""Static + runtime import-audit helpers shared by the QA plugability tests.

This is a *helper* module (leading underscore -> never collected as tests). It is
made importable from the sibling test modules by ``conftest.py``, which inserts
this directory onto ``sys.path`` before the test modules are imported.

Two layers, used by two different QA tests:

* **Static (ast)** -- parse each ``gamebook`` source file and report exactly which
  dotted modules it imports, *without executing it*. This deliberately sees
  imports guarded by ``if TYPE_CHECKING:`` (which never run at import time) and
  resolves relative imports to absolute names. Used by ``test_dependencies.py``
  to enforce the golden rule at the source level.
* **Runtime (subprocess)** -- import a single module in a *fresh* interpreter and
  report which ``gamebook.*`` submodules ended up in ``sys.modules``. This is the
  strongest proof that a module does not *drag in* a forbidden concrete impl
  transitively at run time. Used by ``test_isolation.py``.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import gamebook

# Resolve the real on-disk package location (robust to the editable install and
# to the trailing space in the repo directory name).
GAMEBOOK_ROOT = Path(gamebook.__file__).resolve().parent  # .../src/gamebook
SRC_ROOT = GAMEBOOK_ROOT.parent  # .../src  (module name == path relative to here)

# The five engine packages, bottom-to-top of the dependency pyramid.
ENGINE_PACKAGES = ("domain", "rules", "storage", "combat", "mcp")


# --------------------------------------------------------------------------- static (ast)
def package_files(pkg: str) -> list[Path]:
    """Every ``*.py`` source file under ``gamebook/<pkg>`` (recursively)."""
    root = GAMEBOOK_ROOT / pkg
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def module_name_for(path: Path) -> str:
    """Dotted module name (``gamebook.combat.implementation``) for a source file."""
    rel = path.resolve().relative_to(SRC_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve_relative(this_module: str, is_pkg_init: bool, level: int, module: str) -> str:
    """Resolve a relative import target to an absolute dotted module name."""
    pkg = this_module if is_pkg_init else this_module.rsplit(".", 1)[0]
    base_parts = pkg.split(".") if pkg else []
    drop = level - 1
    base = "" if drop > len(base_parts) else ".".join(base_parts[: len(base_parts) - drop])
    if module and base:
        return f"{base}.{module}"
    return module or base


def imported_modules(path: Path) -> set[str]:
    """All absolute dotted names imported by ``path`` (modules *and* ``module.name``).

    Relative imports are resolved to absolute names. ``if TYPE_CHECKING:`` imports
    are included on purpose -- that is exactly the kind of cross-layer coupling we
    audit at the source level.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    this_module = module_name_for(path)
    is_pkg_init = path.name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                mod = node.module or ""
                if mod:
                    found.add(mod)
                for alias in node.names:
                    found.add(f"{mod}.{alias.name}" if mod else alias.name)
            else:
                base = _resolve_relative(
                    this_module, is_pkg_init, node.level, node.module or ""
                )
                if base:
                    found.add(base)
                for alias in node.names:
                    found.add(f"{base}.{alias.name}" if base else alias.name)
    return found


def gamebook_imports(path: Path) -> set[str]:
    """Subset of :func:`imported_modules` that targets the ``gamebook`` package."""
    return {
        m for m in imported_modules(path) if m == "gamebook" or m.startswith("gamebook.")
    }


def imports_target(imp: str, target: str) -> bool:
    """True if ``imp`` is ``target`` or a dotted child of it (``target.something``)."""
    return imp == target or imp.startswith(target + ".")


def matches_any(imp: str, targets: tuple[str, ...]) -> str | None:
    """Return the first ``target`` that ``imp`` matches (via :func:`imports_target`)."""
    for target in targets:
        if imports_target(imp, target):
            return target
    return None


# ------------------------------------------------------------------------ runtime (subproc)
def runtime_gamebook_modules(target: str) -> set[str]:
    """Import ``target`` in a fresh interpreter; return loaded ``gamebook.*`` modules.

    Runs with the same interpreter/venv as the test session (so ``gamebook`` is
    importable), but in a clean process so the result reflects *only* what
    ``target`` pulls in -- not whatever the test session already imported.
    """
    code = (
        "import json, sys, importlib\n"
        f"importlib.import_module({target!r})\n"
        "print(json.dumps(sorted(m for m in sys.modules "
        "if m == 'gamebook' or m.startswith('gamebook.'))))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"importing {target!r} in a subprocess failed:\n{proc.stderr}"
        )
    return set(json.loads(proc.stdout.strip().splitlines()[-1]))
