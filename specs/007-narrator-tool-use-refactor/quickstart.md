# Quickstart Validation: Narrator Tool-Use Refactor

**Feature**: 007-narrator-tool-use-refactor
**Date**: 2026-06-30

Validation scenarios that prove the narrator tool-use refactor works end-to-end.
Run these after each migration phase to confirm no regression.

---

## Prerequisites

- Spec 006 (`006-cycle1-remediation`) merged to `dev`
- Postgres running: `docker compose up -d`
- Migration applied: `DATABASE_URL=... uv run alembic upgrade head`
- Tests pass on `dev` before branching: `uv run pytest -q`

---

## Phase 1 Validation — System prompt change only

**Goal**: Confirm narrator calls MCP tools during generation after system prompt update.

```bash
# Run API play loop tests (canonical test file — test_narrator.py does not exist)
uv run pytest tests/server/test_api_play_loop.py -v

# Confirm toolset is exercised during generation (check test logs for tool calls)
# Expected: narrator agent run() shows MCP tool calls in trace/debug output
```

**Expected**: Tests pass. Narrator output references real engine values.

---

## Phase 2 Validation — effects[] removed from Scene

**Goal**: Confirm `Scene` has no `effects` field and `TurnResponse` has no `effects_applied`.

```bash
# Full backend test suite
uv run pytest -q

# Confirm no effects_applied in TurnResponse shape
python -c "
from gamebook_web.api.play import TurnResponse
import pydantic
m = TurnResponse.model_fields
assert 'effects_applied' not in m, f'effects_applied still in TurnResponse: {m}'
print('OK: effects_applied removed from TurnResponse')
"

# Confirm no effects in Scene shape
python -c "
from gamebook_web.harness.scene import Scene
m = Scene.model_fields
assert 'effects' not in m, f'effects still in Scene: {m}'
print('OK: effects removed from Scene')
"
```

**Expected**: All assertions pass. No test references `effects_applied`.

---

## Phase 3 + 4 Validation — scaffolding removed + combat endpoints removed (parallel)

**Goal**: Tasks.md Phases 3 (US3 — combat endpoints) and 4 (US4 — scaffolding) are parallel.
Validate both together after they complete.

### Scaffolding (US4 — Phase 4)

```bash
# Confirm EFFECT_TO_MCP_TOOL is gone
grep -r "EFFECT_TO_MCP_TOOL" src/ && echo "FAIL: still present" || echo "OK: removed"

# Confirm _scene_contains_fabricated_numbers is gone
grep -r "_scene_contains_fabricated_numbers" src/ && echo "FAIL: still present" || echo "OK: removed"

# Full test suite still green
uv run pytest -q

# Plugability audit still green (critical)
uv run pytest tests/qa/test_dependencies.py tests/qa/test_isolation.py -q
```

**Expected**: All greps return "OK: removed". Tests green.

### Combat endpoints (US3 — Phase 3)

**Goal**: Confirm `POST /combat/round` and `POST /combat/flee` return 404.

```bash
# Start the server
DATABASE_URL=... uv run uvicorn gamebook_web.api.app:app --port 8000 &
sleep 2

# Create a campaign and character
CAMPAIGN_ID=$(curl -s -X POST http://localhost:8000/campaigns \
  -H "Content-Type: application/json" \
  -H "X-Dev-Account: test-user" | python -c "import sys,json; print(json.load(sys.stdin)['campaign_id'])")

curl -s -X POST http://localhost:8000/campaigns/$CAMPAIGN_ID/character \
  -H "Content-Type: application/json" \
  -H "X-Dev-Account: test-user" \
  -d '{"name": "Validation Hero"}'

# Confirm combat endpoints are 404
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8000/campaigns/$CAMPAIGN_ID/combat/round \
  -H "X-Dev-Account: test-user")
echo "POST /combat/round status: $STATUS"  # Expected: 404

STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8000/campaigns/$CAMPAIGN_ID/combat/flee \
  -H "X-Dev-Account: test-user")
echo "POST /combat/flee status: $STATUS"  # Expected: 404

kill %1  # stop server
```

**Expected**: Both endpoints return 404.

---

## Phase 5 Validation — contract and frontend types updated

**Goal**: Confirm no `effects_applied` or `effects: list[Effect]` references anywhere.

```bash
# Backend: no effects_applied references in contracts or tests
grep -r "effects_applied" docs/CONTRACTS.md tests/ && echo "FAIL: refs remain" || echo "OK: clean"

# Backend: no Effect type references in tests
grep -r "from gamebook_web.harness.scene import.*Effect" tests/ && echo "FAIL" || echo "OK"

# Frontend: no effects_applied in types
grep -r "effects_applied" frontend/src/ && echo "FAIL: refs remain" || echo "OK: clean"

# Full suite green
uv run pytest -q
cd frontend && npm run test -- --run && cd ..
```

**Expected**: All greps return "OK: clean". All tests pass.

---

## End-to-End: narrator uses real numbers (P1 acceptance)

**Goal**: Verify the narrator incorporates real engine values into narrative (not fabricated).

This test requires a live LLM call. Run manually or as part of a smoke test suite:

```bash
# Start server with ANTHROPIC_API_KEY set
ANTHROPIC_API_KEY=... DATABASE_URL=... \
  uv run uvicorn gamebook_web.api.app:app --port 8000 &

# Create campaign + character
CAMPAIGN_ID=$(curl -s -X POST http://localhost:8000/campaigns \
  -H "Content-Type: application/json" | python -c "import sys,json; print(json.load(sys.stdin)['campaign_id'])")

curl -s -X POST http://localhost:8000/campaigns/$CAMPAIGN_ID/character \
  -H "Content-Type: application/json" -d '{"name": "Test Hero"}'

# Take a turn and capture response
RESPONSE=$(curl -s -X POST http://localhost:8000/campaigns/$CAMPAIGN_ID/turn \
  -H "Content-Type: application/json" -d '{"choice": null}')

echo "$RESPONSE" | python -c "
import sys, json
r = json.load(sys.stdin)
# Verify no effects_applied in response
assert 'effects_applied' not in r, 'effects_applied still present!'
# Verify scene has no effects
assert 'effects' not in r['scene'], 'effects still in scene!'
print('Structural check: PASS')
print('Narrative:', r['scene']['narrative'][:200])
"

kill %1
```

**Expected**: No `effects_applied` or `effects` in response. Narrative is coherent and
references engine state (the narrator read the character sheet and world during generation).
