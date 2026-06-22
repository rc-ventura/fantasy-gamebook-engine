"""Runtime module-isolation audit (the strongest plugability proof).

Imports each engine module in a *fresh* interpreter and inspects its
``sys.modules`` footprint. Where ``test_dependencies.py`` proves what the source
*says*, this proves what actually gets *loaded* -- catching any concrete impl
dragged in transitively at run time.

Key subtlety from ``docs/CONTRACTS.md`` Section 1 (binding audit rule):
``combat`` references ``storage.interfaces.StorageBackend`` only under
``if TYPE_CHECKING:``, so at run time it has **no** storage dependency at all.
Consequently we must NOT require ``storage.interfaces`` to be present in
``combat``'s footprint; we assert only the *absence* of the storage concretes
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


# --------------------------------------------------------------------------- domain
def test_domain_loads_no_other_gamebook_layer() -> None:
    footprint = _audit.runtime_gamebook_modules("gamebook.domain.models")
    foreign = {
        m
        for m in footprint
        if m != "gamebook" and not _audit.imports_target(m, "gamebook.domain")
    }
    assert not foreign, f"domain dragged in foreign gamebook modules: {sorted(foreign)}"


# --------------------------------------------------------------------------- rules
def test_rules_loads_only_domain_below_it() -> None:
    footprint = _audit.runtime_gamebook_modules("gamebook.rules.implementation")
    assert not _has(footprint, "gamebook.storage"), footprint
    assert not _has(footprint, "gamebook.combat"), footprint
    assert not _has(footprint, "gamebook.mcp"), footprint


# --------------------------------------------------------------------------- storage
def test_storage_concretes_load_nothing_above_domain() -> None:
    for concrete in STORAGE_CONCRETES:
        footprint = _audit.runtime_gamebook_modules(concrete)
        assert not _has(footprint, "gamebook.rules"), (concrete, footprint)
        assert not _has(footprint, "gamebook.combat"), (concrete, footprint)
        assert not _has(footprint, "gamebook.mcp"), (concrete, footprint)


# --------------------------------------------------------------------------- combat
def test_combat_runtime_has_no_storage_concrete_or_mcp() -> None:
    """The binding isolation check for swap boundary #1.

    Per the audit rule, assert only the ABSENCE of the storage concretes and of
    ``mcp``; do NOT require ``storage.interfaces`` to be present (TYPE_CHECKING).
    """
    footprint = _audit.runtime_gamebook_modules("gamebook.combat.implementation")

    for concrete in STORAGE_CONCRETES:
        assert concrete not in footprint, (
            f"combat leaked the concrete backend {concrete!r} at runtime "
            f"(swap boundary #1 violated): {sorted(footprint)}"
        )
    assert not _has(footprint, "gamebook.mcp"), (
        f"combat must not load the mcp facade: {sorted(footprint)}"
    )

    # Stronger corollary of the TYPE_CHECKING guard: combat pulls in NO storage
    # module at all at run time (not even the interface). This is informative,
    # not the binding assertion above.
    assert not _has(footprint, "gamebook.storage"), (
        "combat is expected to reference StorageBackend only under TYPE_CHECKING, "
        f"so no storage module should load at runtime, got: {sorted(footprint)}"
    )

    # Sanity: it really did load the layers it is allowed to use.
    assert _has(footprint, "gamebook.rules"), footprint
    assert _has(footprint, "gamebook.domain"), footprint
