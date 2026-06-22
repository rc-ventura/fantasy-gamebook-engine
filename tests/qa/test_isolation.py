"""Runtime module-isolation audit (the strongest plugability proof).

Imports each engine module in a *fresh* interpreter and inspects its
``sys.modules`` footprint. Where ``test_dependencies.py`` proves what the source
*says*, this proves what actually gets *loaded* -- catching any concrete impl
dragged in transitively at run time.

Key subtlety from ``docs/CONTRACTS.md`` Section 1 (binding audit rule):
``combate`` references ``storage.interfaces.StorageBackend`` only under
``if TYPE_CHECKING:``, so at run time it has **no** storage dependency at all.
Consequently we must NOT require ``storage.interfaces`` to be present in
``combate``'s footprint; we assert only the *absence* of the storage concretes
and of ``mcp``. (We additionally observe that no ``storage`` module whatsoever
is loaded -- an even stronger result the TYPE_CHECKING guard buys us.)
"""

from __future__ import annotations

import _audit

STORAGE_CONCRETES = (
    "gamebook.storage.json_storage",
    "gamebook.storage.in_memory",
)


def _has(footprint: set[str], target: str) -> bool:
    return any(_audit.imports_target(mod, target) for mod in footprint)


# --------------------------------------------------------------------------- dominio
def test_dominio_loads_no_other_gamebook_layer() -> None:
    footprint = _audit.runtime_gamebook_modules("gamebook.dominio.models")
    foreign = {
        m
        for m in footprint
        if m != "gamebook" and not _audit.imports_target(m, "gamebook.dominio")
    }
    assert not foreign, f"dominio dragged in foreign gamebook modules: {sorted(foreign)}"


# --------------------------------------------------------------------------- regras
def test_regras_loads_only_dominio_below_it() -> None:
    footprint = _audit.runtime_gamebook_modules("gamebook.regras.implementation")
    assert not _has(footprint, "gamebook.storage"), footprint
    assert not _has(footprint, "gamebook.combate"), footprint
    assert not _has(footprint, "gamebook.mcp"), footprint


# --------------------------------------------------------------------------- storage
def test_storage_concretes_load_nothing_above_dominio() -> None:
    for concrete in STORAGE_CONCRETES:
        footprint = _audit.runtime_gamebook_modules(concrete)
        assert not _has(footprint, "gamebook.regras"), (concrete, footprint)
        assert not _has(footprint, "gamebook.combate"), (concrete, footprint)
        assert not _has(footprint, "gamebook.mcp"), (concrete, footprint)


# --------------------------------------------------------------------------- combate
def test_combate_runtime_has_no_storage_concrete_or_mcp() -> None:
    """The binding isolation check for swap boundary #1.

    Per the audit rule, assert only the ABSENCE of the storage concretes and of
    ``mcp``; do NOT require ``storage.interfaces`` to be present (TYPE_CHECKING).
    """
    footprint = _audit.runtime_gamebook_modules("gamebook.combate.implementation")

    for concrete in STORAGE_CONCRETES:
        assert concrete not in footprint, (
            f"combate leaked the concrete backend {concrete!r} at runtime "
            f"(swap boundary #1 violated): {sorted(footprint)}"
        )
    assert not _has(footprint, "gamebook.mcp"), (
        f"combate must not load the mcp facade: {sorted(footprint)}"
    )

    # Stronger corollary of the TYPE_CHECKING guard: combate pulls in NO storage
    # module at all at run time (not even the interface). This is informative,
    # not the binding assertion above.
    assert not _has(footprint, "gamebook.storage"), (
        "combate is expected to reference StorageBackend only under TYPE_CHECKING, "
        f"so no storage module should load at runtime, got: {sorted(footprint)}"
    )

    # Sanity: it really did load the layers it is allowed to use.
    assert _has(footprint, "gamebook.regras"), footprint
    assert _has(footprint, "gamebook.dominio"), footprint
