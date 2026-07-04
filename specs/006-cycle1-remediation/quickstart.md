# Quickstart — Cycle-1 Remediation Validation (spec 006)

**Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

End-to-end validation guide. Proves the remediation is complete by exercising each
track's critical path. Run after all tasks in [tasks.md](./tasks.md) are complete.

---

## Prerequisites

```bash
# 1. Postgres running (matches DATABASE_URL below)
docker run -d --name gamebook-pg \
  -e POSTGRES_USER=gamebook -e POSTGRES_PASSWORD=gamebook \
  -e POSTGRES_DB=gamebook -p 5432:5432 postgres:16-alpine

export DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost/gamebook

# 2. Apply migrations
uv run alembic upgrade head

# 3. Install frontend deps
cd frontend && npm install && cd ..
```

---

## Track 1: Multi-tenant engine isolation (ADR-018, SC-002)

```bash
# Run multi-campaign isolation test
DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost/gamebook \
  uv run pytest tests/server/test_multi_campaign_isolation.py -v

# Run plugability audit (must stay green)
uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q
```

**Expected**: campaign A's character is not visible to campaign B; plugability audit
passes with no new violations from the `storage_factory` seam.

---

## Track 2: Backend-scoped routes + frontend contract alignment (D1, SC-001, SC-007)

```bash
# Backend: verify new routes exist
DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost/gamebook \
  uv run uvicorn gamebook_web.api.app:app --reload &

curl -s -X POST http://localhost:8000/me/game \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Hero"}' | python3 -m json.tool

curl -s http://localhost:8000/me/graveyard \
  -H "Authorization: Bearer dev-token" | python3 -m json.tool

# Frontend: TypeScript compile check (no errors from type changes)
cd frontend && node_modules/.bin/tsc -p tsconfig.app.json --noEmit

# Frontend: unit tests
npm test -- --run

# Playwright: live backend integration test
VITE_USE_MOCK=false npx playwright test tests/e2e/live-play-loop.spec.ts
```

**Expected**: `POST /me/game` returns `{ status, campaign_id }`. `GET /me/graveyard`
returns `[]` (empty at start). TypeScript compiles clean. All unit + Playwright tests
pass.

---

## Track 3: Production guards (SC-003, SC-004)

```bash
# Start server in production mode with dev auth — must refuse
ENV=production GAMEBOOK_DEV_MODE=1 \
  uv run python -c "
import asyncio
from gamebook_web.api.app import app
import uvicorn
asyncio.run(uvicorn.Server(uvicorn.Config(app)).startup())
" 2>&1 | grep "RuntimeError\|must not"

# Docs must return 404 in production
ENV=production uv run uvicorn gamebook_web.api.app:app &
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs
# Expected: 404

kill %1
```

**Expected**: server refuses to start with `RuntimeError`; `/docs` returns 404.

---

## Track 4: Postgres persistence hardening (ADR-026/027, SC-018/019/020)

```bash
DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost/gamebook \
  uv run pytest tests/server/test_postgres_storage.py \
    tests/server/test_atomic_writes.py \
    tests/qa/test_storage_swap.py -v
```

**Expected**: TLS enforcement test passes (or is skipped with note if local Postgres
doesn't support TLS); concurrent `append_event` produces unique `seq` values; `close()`
teardown is clean; atomic write mid-failure leaves no partial data.

---

## Track 5: Fail-closed OIDC auth (ADR-022, SC-009)

```bash
uv run pytest tests/server/test_oidc_fail_closed.py -v
```

**Expected**: boot without `OIDC_JWKS_URI` refused; JWT without `exp` → 401; JWT
without `kid` → 401; JWT with wrong `iss` → 401.

---

## Track 6: DB-backed campaign ownership + lease (ADR-023/025, SC-010/011/013/014)

```bash
DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost/gamebook \
  uv run pytest \
    tests/server/test_postgres_campaign_ownership.py \
    tests/server/test_postgres_leases.py \
    tests/server/test_account_endpoints.py \
    tests/server/test_postgres_gdpr.py -v
```

**Expected**: duplicate campaign → 409; `account_id` not NULL; `takeover` validates
`current_token`; lease expiry uses `<=`; `DELETE /me` requires confirmation; export
includes `save_slot`.

---

## Track 7: Observability (ADR-024, SC-012/015)

```bash
uv run pytest tests/server/test_otel_instrumentation.py \
              tests/server/test_security_audit_logging.py \
              tests/server/test_production_guards.py -v
```

**Expected**: `turn_span`/`narrator_span` exist with correct attributes; no PII in
spans; `http_requests_total` incremented; security events logged for auth/lease
operations; CORS `*` rejected when `allow_credentials=True`.

---

## Track 8: Combat victory + narrator (SC-025b, SC-026)

```bash
uv run pytest tests/server/test_combat_victory.py \
              tests/server/test_narrator_integration.py \
              tests/server/test_rate_limiter.py -v
```

**Expected**: combat victory via `POST /me/game/turn` → campaign ended + archived;
subsequent turn → 409 `run_ended`; narrator produces `Scene` with no `effects` field;
rate limiter keys on `account_id` when authenticated.

---

## Track 9: SPA production hardening (SC-031/032/033/035/036)

```bash
cd frontend

# Source maps absent in production build
npm run build
ls dist/assets/*.map 2>/dev/null && echo "FAIL: source maps present" || echo "PASS: no source maps"

# ErrorBoundary test
npm test -- --run src/components/__tests__/test_error_boundary.test.tsx

# Auth redirect test
npm test -- --run src/hooks/__tests__/test_auth_redirect.test.tsx

# Choices validation test
npm test -- --run src/components/__tests__/test_choices_validation.test.tsx
```

**Expected**: no `.map` files in production build; all three test files pass.

---

## Full suite (SC-006/007, final gate)

```bash
# Backend full suite
uv run pytest -q

# Frontend unit suite
cd frontend && npm test -- --run

# Plugability audit
uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q

# Postgres integration (requires DATABASE_URL)
DATABASE_URL=postgresql+asyncpg://gamebook:gamebook@localhost/gamebook \
  uv run pytest tests/server/test_postgres_*.py tests/qa/test_storage_swap.py -v
```

**All green = remediation complete and ready for SDD cycle-2 review.**

---

## References

- [spec.md](./spec.md) — requirements
- [plan.md](./plan.md) — architecture
- [tasks.md](./tasks.md) — ordered task list
- [contracts/http-api.md](./contracts/http-api.md) — API contract
- [data-model.md](./data-model.md) — data model changes
- [research.md](./research.md) — decision rationale
