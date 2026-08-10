# LeaseService.acquire() lets the same account silently reclaim a lease — the dedicated /takeover endpoint can't be used by a dispossessed tab

**Date**: 2026-08-09
**Spec**: [004-accounts-hardening-obs](../../specs/004-accounts-hardening-obs/) (ADR-023/031/032)
**Code**: `src/gamebook_web/sessions/lease.py::LeaseService.acquire/takeover`

## What happened

Wiring session-lease enforcement into the SPA (issue #15) required understanding exactly
how two browser tabs on the *same account* are supposed to negotiate exclusive write
access. Reading `LeaseService.acquire()`, the "someone else holds it" check is:

```python
is_same_holder = db_holder == account_id
if not is_expired and not is_same_holder:
    raise 409  # someone else holds it, unexpired
# otherwise: rotate the token unconditionally
```

Empirically probed against real Postgres (`LeaseService` instantiated directly, not through
the API): **a second call to `acquire()` from the same account_id always succeeds**, even
while a first, unexpired lease is still held — it silently rotates the token and the first
tab's next mutating request 409s. There is no 409 at *acquire* time for the same-account
case, only later, when the dispossessed tab tries to act.

The natural next step — call the dedicated `POST /me/game/session/takeover` endpoint from
the dispossessed tab to reclaim it — does not work. `takeover()`'s `current_token` check
compares only against `db_token` (the *live*, currently-held token), never against
`db_holder`/account identity:

```python
if not current_token or not _tokens_match(current_token, db_token):
    raise 409  # requires knowing the CURRENT holder's live token
```

A tab that just got dispossessed only ever knew its own *now-stale* token — it structurally
cannot know the other tab's live one. Verified directly: presenting your own stale token to
`takeover()` always 409s. The dedicated takeover endpoint is unusable for the exact scenario
its UI button ("Take Over Session") is meant to solve, in a single-tenant-per-campaign app.

## The resolution

`acquireSession()` (not `takeoverSession()`'s dedicated route) is the actual reclaim path
for this app: since `is_same_holder` only checks `account_id`, a plain re-acquire from the
same authenticated account always succeeds regardless of who currently holds it, with no
token needed. `client.ts`'s `takeoverSession()` now delegates to `acquireSession()`
internally — the UI button and its name stay the same, only the HTTP route underneath
changes. See `frontend/src/api/client.ts`'s `takeoverSession()` docstring for the same
reasoning.

## Rule

Before wiring a UI action to a specific backend endpoint by name, check what the endpoint's
authorization check actually requires against what the caller can actually possess at that
point in the flow. `takeover(current_token)`'s check is sound for a genuinely different
future scenario (a second *account* that somehow learned the live token — e.g. a
multi-player/spectator "join and take control" feature) but is a dead end for "the same
person, second tab, dispossessed by their own first tab" — the actual scenario this app's
UI presents it for. `acquire()`'s account-identity-only check is what actually implements
same-account reclaim; don't assume the endpoint named for a UI action is the one whose
authorization model matches that action's real caller.
