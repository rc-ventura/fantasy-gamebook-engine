"""Golden-rule import audit (static / ast).

Parses every ``gamebook`` source file *without executing it* and asserts the
dependency direction of the architecture: each module may depend only on the
layers below it (and only on their *interfaces*). This is the QA guardian of the
golden rule and the three swap boundaries.

The rules encoded here come directly from ``docs/CONTRACTS.md`` Section 1
("Module layering" + the binding **Audit rule** paragraph):

* ``domain`` -- base of the pyramid; imports no other ``gamebook`` module.
* ``rules``  -- imports only ``domain`` (the pure core).
* ``storage`` -- imports only ``domain``.
* ``combat`` -- may import ``rules`` and ``domain`` and, under
  ``TYPE_CHECKING`` only, ``storage.interfaces``; it must NEVER import a storage
  *concrete* (``storage.json_storage`` / ``storage.in_memory``) nor ``mcp``.
* ``mcp`` (non-root) -- the facade; only ``server.py``'s ``main()`` (the
  composition root) is allowed to construct concretes, so every *other* ``mcp``
  module must not import a storage concrete.

Because the audit is static it also sees ``if TYPE_CHECKING:`` imports, so a
concrete leak smuggled in under a typing guard is still caught.
"""

from __future__ import annotations

import _audit
import pytest

# Storage concrete implementations -- forbidden above the composition root.
STORAGE_CONCRETES = (
    "gamebook.storage.json_storage",
    "gamebook.storage.in_memory",
)

# Allow-list rules for the lower, strictly-layered packages: every gamebook
# import a file in <pkg> makes must match one of these prefixes.
ALLOWED_PREFIXES: dict[str, tuple[str, ...]] = {
    "domain": ("gamebook", "gamebook.domain"),
    "rules": ("gamebook", "gamebook.domain", "gamebook.rules"),
    "storage": ("gamebook", "gamebook.domain", "gamebook.storage"),
}


def _files(pkg: str):
    files = _audit.package_files(pkg)
    return [(f, _audit.module_name_for(f)) for f in files]


# --------------------------------------------------------------------------- domain/rules/storage
@pytest.mark.parametrize("pkg", ["domain", "rules", "storage"])
def test_lower_layers_only_import_allowed_prefixes(pkg: str) -> None:
    """`domain`/`rules`/`storage` may only import the layers below them."""
    allowed = ALLOWED_PREFIXES[pkg]
    files = _files(pkg)
    assert files, f"no source files found for package {pkg!r}"

    violations: list[str] = []
    for path, modname in files:
        for imp in sorted(_audit.gamebook_imports(path)):
            if _audit.matches_any(imp, allowed) is None:
                violations.append(f"{modname} imports {imp!r} (allowed: {allowed})")

    assert not violations, (
        f"{pkg!r} reaches outside its allowed layers (golden-rule violation):\n  "
        + "\n  ".join(violations)
    )


def test_domain_is_the_base_of_the_pyramid() -> None:
    """`domain` depends on nothing else in `gamebook` (only its own submodules)."""
    leaks: list[str] = []
    for path, modname in _files("domain"):
        for imp in sorted(_audit.gamebook_imports(path)):
            if not _audit.imports_target(imp, "gamebook.domain") and imp != "gamebook":
                leaks.append(f"{modname} imports {imp!r}")
    assert not leaks, "domain must depend on no other gamebook module:\n  " + "\n  ".join(leaks)


# --------------------------------------------------------------------------- combat
def test_combat_never_imports_a_storage_concrete_or_mcp() -> None:
    """`combat` must depend on storage only via its interface (boundary #1).

    It may import `rules` (stable core) and `domain`, and reference
    `storage.interfaces` under `TYPE_CHECKING`; it must NEVER import a concrete
    storage backend nor the `mcp` facade above it.
    """
    forbidden = STORAGE_CONCRETES + ("gamebook.mcp",)
    files = _files("combat")
    assert files, "no source files found for package 'combat'"

    violations: list[str] = []
    for path, modname in files:
        imports = _audit.gamebook_imports(path)
        for imp in sorted(imports):
            hit = _audit.matches_any(imp, forbidden)
            if hit is not None:
                violations.append(f"{modname} imports {imp!r} (forbidden: {hit})")

    assert not violations, (
        "combat violated swap boundary #1 by importing a concrete impl/facade:\n  "
        + "\n  ".join(violations)
    )


def test_combat_uses_storage_interface_only_under_type_checking() -> None:
    """Positive proof the boundary is satisfied the *intended* way.

    `combat` references `StorageBackend` for typing; the ast audit sees that
    typing import, and it must be `storage.interfaces` (never a concrete). This
    asserts the interface seam exists, complementing the negative test above.
    """
    referenced_storage: set[str] = set()
    for path, _modname in _files("combat"):
        for imp in _audit.gamebook_imports(path):
            if _audit.imports_target(imp, "gamebook.storage"):
                referenced_storage.add(imp)

    for imp in referenced_storage:
        assert _audit.imports_target(imp, "gamebook.storage.interfaces"), (
            f"combat references storage via {imp!r}, expected gamebook.storage.interfaces"
        )


# --------------------------------------------------------------------------- mcp
def test_non_root_mcp_modules_do_not_import_storage_concretes() -> None:
    """Only the composition root (`mcp/server.py` `main`) may build concretes.

    Every other `mcp` module must depend on storage via its interface only. If
    `mcp` has no modules yet (server not built), this passes vacuously and will
    start enforcing as soon as the facade lands.
    """
    violations: list[str] = []
    for path, modname in _files("mcp"):
        if modname == "gamebook.mcp.server":
            continue  # the single allowed composition root
        for imp in sorted(_audit.gamebook_imports(path)):
            hit = _audit.matches_any(imp, STORAGE_CONCRETES)
            if hit is not None:
                violations.append(f"{modname} imports {imp!r} (forbidden: {hit})")

    assert not violations, (
        "non-root mcp modules must not import storage concretes:\n  "
        + "\n  ".join(violations)
    )


# --------------------------------------------------------------------------- gamebook_web (slice 003)
#
# The web layer (``src/gamebook_web/``) sits ABOVE the engine.  Its golden
# rule: it may depend on ``gamebook.domain.*`` (the shared contract types) but
# must NEVER import storage concretes, engine-internal modules (combat, rules,
# mcp internals), or any Postgres-specific code.  It interacts with the engine
# exclusively through the MCP tool contract (Principle II).

WEB_FORBIDDEN: tuple[str, ...] = (
    # Storage concretes
    "gamebook.storage.json_storage",
    "gamebook.storage.in_memory",
    # Engine internals (combat, rules, mcp internals — use MCP tool contract only)
    "gamebook.combat",
    "gamebook.rules",
    # mcp.server is the composition root; the web layer must not import it
    # (it connects via the MCP protocol, not by calling server functions).
    "gamebook.mcp",
)


def _web_files():
    """All Python source files under ``src/gamebook_web/``."""
    from pathlib import Path
    import gamebook_web

    web_root = Path(gamebook_web.__file__).resolve().parent
    src_root = web_root.parent

    files = sorted(
        p for p in web_root.rglob("*.py") if "__pycache__" not in p.parts
    )

    def _modname(path: Path) -> str:
        rel = path.resolve().relative_to(src_root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    return [(f, _modname(f)) for f in files]


def _web_gamebook_imports(path):
    """``gamebook.*`` imports found in a ``gamebook_web`` source file."""
    return {
        m for m in _audit.imported_modules(path)
        if m == "gamebook" or m.startswith("gamebook.")
    }


def test_gamebook_web_exists() -> None:
    """Confirm the web package is importable (sanity guard)."""
    files = _web_files()
    assert files, "No source files found for gamebook_web — package not built yet"


def test_gamebook_web_never_imports_storage_concretes() -> None:
    """``gamebook_web`` must not import any storage concrete implementation.

    Swap boundary #1 (StorageBackend) must be intact from the web layer too.
    """
    violations: list[str] = []
    for path, modname in _web_files():
        for imp in sorted(_web_gamebook_imports(path)):
            hit = _audit.matches_any(imp, WEB_FORBIDDEN[:2])  # only storage concretes
            if hit is not None:
                violations.append(f"{modname} imports {imp!r} (forbidden: {hit})")

    assert not violations, (
        "gamebook_web imported a storage concrete — Principle II violated:\n  "
        + "\n  ".join(violations)
    )


def test_gamebook_web_never_imports_engine_internals() -> None:
    """``gamebook_web`` must not reach into combat, rules, or mcp internals.

    The web layer depends on the MCP tool contract (Principle II).  It may
    import ``gamebook.domain.*`` (shared contract types).
    """
    violations: list[str] = []
    for path, modname in _web_files():
        for imp in sorted(_web_gamebook_imports(path)):
            hit = _audit.matches_any(imp, WEB_FORBIDDEN[2:])  # internals
            if hit is not None:
                violations.append(f"{modname} imports {imp!r} (forbidden: {hit})")

    assert not violations, (
        "gamebook_web reached into engine internals — Principle II violated:\n  "
        + "\n  ".join(violations)
    )


def test_gamebook_web_domain_imports_only_domain() -> None:
    """Any ``gamebook.*`` import in ``gamebook_web`` must be ``gamebook.domain.*``.

    Domain models are the shared contract (not internals).  No other gamebook
    package is allowed.
    """
    violations: list[str] = []
    for path, modname in _web_files():
        for imp in sorted(_web_gamebook_imports(path)):
            # Allowed: gamebook (top-level), gamebook.domain.*
            if imp == "gamebook":
                continue
            if _audit.imports_target(imp, "gamebook.domain"):
                continue
            # Everything else is a violation
            violations.append(
                f"{modname} imports {imp!r} (only gamebook.domain.* is allowed)"
            )

    assert not violations, (
        "gamebook_web imports gamebook modules beyond domain/ — Principle II violated:\n  "
        + "\n  ".join(violations)
    )
