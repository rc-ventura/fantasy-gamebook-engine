# ADR-032: Atomic validate-and-renew to close TOCTOU in lease enforcement

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-02 |
| **Related** | ADR-023 (session lease semantics), ADR-031 (route-level require_lease) |

## Context

The SDD final review (cycle 2) identified a TOCTOU (time-of-check-to-time-of-use) race in the lease enforcement path:

1. `require_lease` called `validate()` and `renew()` in **separate transactions**.
2. `validate()` used a non-locking `SELECT` (no `FOR UPDATE`), so its transaction committed and released any implicit lock before the protected route mutation executed.
3. Between `validate()` passing and `renew()` running, a concurrent `takeover()` could rotate the lease holder.
4. `renew()` would then fail with `409 not_session_holder` — but `require_lease` caught **all** exceptions from `renew()` with `except Exception: pass`, swallowing the 409.
5. The route mutation proceeded under a lease the caller no longer held.

This was rated MEDIUM by the Security Engineer (narrow concurrency window, requires precise timing) and confirmed by the QA Engineer and the Devin CLI second opinion.

Additionally, the `account_id` comparison in `validate()` and `release()` used Python's `str.__eq__` (`!=`), which is not constant-time and short-circuits the `or` before the token comparison (`_tokens_match`), creating a timing oracle on whether the supplied account is the current holder.

## Decision

### 1. Atomic `validate_and_renew()`

Add a new `LeaseService.validate_and_renew(campaign_id, account_id, lease_token)` method that performs both validation and TTL renewal in a **single transaction** with `SELECT ... FOR UPDATE`:

```sql
SELECT lease_token, holder_account_id, expires_at
FROM session_lease WHERE campaign_id = :cid FOR UPDATE
-- validate account_id + token + expiry
UPDATE session_lease SET expires_at = :new_expires WHERE campaign_id = :cid
```

The `FOR UPDATE` row lock is held for the duration of the transaction, preventing a concurrent `takeover()` from rotating the holder between validation and renewal.

`require_lease` now calls `validate_and_renew()` instead of `validate()` + `renew()` separately.

### 2. Stop swallowing `HTTPException` from renewal

The `except Exception: pass` that swallowed all `renew()` failures is replaced with:

```python
except HTTPException:
    # not_session_holder / lease_expired — MUST propagate
    audit_event("lease.denied", ...)
    raise
except Exception:
    # DB connectivity, etc. — non-fatal, log and continue
    logger.warning(...)
```

`HTTPException` (409) propagates so a taken-over lease rejects the mutation. Non-HTTP exceptions (infrastructure failures) are still non-fatal — the request proceeds without lease renewal rather than failing hard on a transient blip.

### 3. Constant-time `account_id` comparison

Add `_accounts_match()` using `hmac.compare_digest`, and restructure the boolean to evaluate both `holder_ok` and `token_ok` **before** the `if` statement, eliminating the short-circuit:

```python
holder_ok = _accounts_match(db_holder, account_id)  # constant-time
token_ok = _tokens_match(db_token, lease_token)      # constant-time
if not holder_ok or not token_ok:
    raise HTTPException(409, ...)
```

Both comparisons always run regardless of the first result.

### 4. `validate()` also uses `FOR UPDATE`

The standalone `validate()` method (still called by tests and potentially by other consumers) is updated to use `async with session.begin()` + `FOR UPDATE` for consistency, even though `require_lease` now uses `validate_and_renew()`.

## Consequences

**Positive**:
- The TOCTOU window between validate and renew is eliminated — both happen under a single row lock.
- A taken-over lease correctly rejects the mutation (409 propagates instead of being swallowed).
- No timing oracle on `account_id` — both account and token comparisons are constant-time and always evaluated.
- The `validate()` method is consistent with `acquire`/`renew`/`release`/`takeover` (all use `FOR UPDATE`).

**Negative**:
- The `FOR UPDATE` lock in `validate()` is held slightly longer (until the transaction commits) compared to the previous non-locking read. This is negligible — the transaction is a single SELECT + conditional UPDATE.
- `require_lease` no longer renews the lease on infrastructure failures (DB down). This is acceptable: the lease has a 30-minute TTL, and a transient DB blip should not block the request. The next successful request will renew.
