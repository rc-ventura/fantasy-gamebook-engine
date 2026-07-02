"""Security audit logging (T052, FR-033).

A single ``audit_event`` helper writes structured security events to the
``gamebook.audit`` logger.  Only opaque identifiers are logged — account_id and
campaign_id are UUIDs, never a name, email, OIDC ``sub`` value, token, or player
input.  Events are logged at INFO (normal lifecycle) or WARNING (failures).

Covered events (names are stable — deployments alert on them):
  auth.signin / auth.signout       — session lease acquired / released
  auth.failed                      — token rejected / missing
  auth.jwks_unavailable            — OIDC provider unreachable
  session.takeover                 — lease taken over
  lease.denied                     — lease validation failed (guard)
  account.deleted                  — account erased (GDPR)
"""

from __future__ import annotations

import logging

audit_logger = logging.getLogger("gamebook.audit")

# Fields that must never be logged even if a caller passes them (defence in depth).
_FORBIDDEN_FIELDS = frozenset({"sub", "token", "name", "email", "authorization", "narrative"})


def audit_event(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Emit a security audit event with opaque fields only.

    ``event`` is a stable dotted name (e.g. ``auth.failed``); ``fields`` are
    opaque identifiers.  Any forbidden (PII-bearing) field is dropped rather
    than logged.
    """
    safe = {k: v for k, v in fields.items() if k not in _FORBIDDEN_FIELDS and v is not None}
    detail = " ".join(f"{k}={v}" for k, v in safe.items())
    audit_logger.log(level, "audit event=%s %s", event, detail)
