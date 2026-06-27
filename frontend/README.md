# Fantasy Gamebook SPA — `frontend/`

Professional single-page web application for the Fantasy Gamebook Engine.
Consumes the documented HTTP API from slice 003 (`src/gamebook_web/`).

**Stack**: React 18 + Vite + TypeScript (strict) · Vitest (unit) · Playwright (E2E)

---

## Quick Start

### Prerequisites

- Node.js v22+ (`nvm use 22` or via `.nvmrc`)
- A running backend (slice 003) OR mock mode (no backend needed)

```bash
cd frontend
npm ci
```

### Mock mode (no backend required)

All API calls return deterministic fixture data. The full play loop is exercisable.

```bash
echo "VITE_USE_MOCK=true" > .env.local
npm run dev
# → http://localhost:5173
```

### Live backend mode (slice 003 required)

```bash
# Terminal 1 — start the backend
cd ..
docker compose up -d
DATABASE_URL=postgresql+asyncpg://... uv run uvicorn gamebook_web.api.app:app --reload

# Terminal 2 — start the SPA (proxies /api/* → localhost:8000)
cd frontend
VITE_DEV_TOKEN=your-dev-token npm run dev
```

The Vite dev server proxies `/api/*` to `http://localhost:8000` (configured in `vite.config.ts`).
Set `VITE_DEV_TOKEN` to the dev auth token expected by slice 003's dev auth stub.

---

## Running Tests

### Unit / component tests (vitest)

```bash
npm run test            # run once
npm run test:watch      # watch mode
```

All unit tests run against the mock layer — **no backend or LLM required**.

### E2E tests (Playwright)

```bash
npm run test:e2e        # spins up the dev server (mock mode) and runs Playwright
```

E2E tests are in `tests/e2e/`. They exercise the full play loop in the browser:
- Landing page → Dashboard → New campaign → Character creation → Choices → Combat → End state

To run against the live backend instead of mock mode:
```bash
PLAYWRIGHT_BASE_URL=http://localhost:5173 npm run test:e2e
# (make sure the dev server is running without VITE_USE_MOCK)
```

---

## Green Gate (CI)

All four must pass before merging:

```bash
npm run typecheck    # tsc -b --noEmit  (strict, no `any`)
npm run lint         # eslint src --max-warnings 0
npm run build        # tsc -b && vite build
npm run test         # vitest run (59 tests)
```

---

## Project Structure

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts      # Typed HTTP client (wraps all endpoints from http-api.md)
│   │   ├── mock.ts        # Deterministic mock handlers (VITE_USE_MOCK=true)
│   │   └── index.ts       # Re-exports
│   ├── components/
│   │   ├── NarratorPanel.tsx    # Scene narration (EB Garamond prose)
│   │   ├── ChoicesPanel.tsx     # Numbered choices + free-text input
│   │   ├── CharacterSheet.tsx   # Hero stats (engine state only)
│   │   ├── Inventory.tsx        # Backpack (engine state only)
│   │   ├── MapPanel.tsx         # World / visited locations
│   │   ├── CombatPanel.tsx      # Combat rounds, luck tests, outcomes
│   │   ├── SessionConflict.tsx  # 409 not_session_holder → "Take over" prompt
│   │   ├── LoadingState.tsx     # Spinner for every async operation
│   │   ├── ErrorState.tsx       # Safe error display
│   │   └── EmptyState.tsx       # Empty state (no character, empty inventory, etc.)
│   ├── hooks/
│   │   ├── useAuth.ts           # Auth token seam (dev stub → real OIDC in 004)
│   │   ├── useGame.ts           # Full play loop state (loads campaign, takes turns)
│   │   └── useCampaign.ts       # Campaign list management
│   ├── pages/
│   │   ├── LandingPage.tsx      # Marketing / hero screen
│   │   ├── AuthPage.tsx         # Sign-in / register (dev stub; real OIDC in 004)
│   │   ├── DashboardPage.tsx    # Campaign list
│   │   └── PlayPage.tsx         # Full play loop (narrator + choices + sidebar + combat)
│   ├── types/
│   │   └── index.ts             # TypeScript types mirroring Scene schema + domain entities
│   ├── vite-env.d.ts            # VITE_* env var types (ImportMetaEnv)
│   ├── test-setup.ts            # Vitest setup (@testing-library/jest-dom)
│   └── index.css                # Design tokens (--bg, --accent, --ink, fonts)
├── tests/
│   ├── unit/
│   │   ├── api/                 # client.test.ts — API contract shape tests
│   │   ├── components/          # Per-component tests (NarratorPanel, ChoicesPanel, etc.)
│   │   └── audit/               # no-fabricated-values.test.ts (SC-003 audit)
│   └── e2e/
│       └── play-loop.spec.ts    # Playwright: full play loop in mock mode
├── package.json
├── vite.config.ts               # Vite dev server + proxy config
├── vitest.config.ts             # Vitest test runner config
├── playwright.config.ts         # Playwright E2E config
├── tsconfig.json                # Composite tsconfig root
├── tsconfig.app.json            # App source (strict, no any)
├── tsconfig.node.json           # Config files (vite, vitest, playwright)
└── eslint.config.js             # ESLint flat config (type-checked, no-any enforced)
```

---

## Architecture Constraints

**The one rule that shapes the entire SPA**: every number shown to the player comes from the API.
The frontend never rolls dice, computes combat math, or fabricates stats.

- No durable state in the SPA — all game state flows through the API
- Auth seam in `useAuth.ts` — dev stub now, real OIDC (slice 004) swaps in without touching play loop
- 409 `not_session_holder` → `SessionConflict` modal with "Take Over Session" button
- TypeScript strict mode + `no-any` enforced by ESLint

---

## Live Backend Integration (after slice 003 ships)

Slice 003 delivers the real FastAPI backend. To switch from mock to real:
1. Remove `VITE_USE_MOCK=true` from `.env.local`
2. Set `VITE_DEV_TOKEN=<your-dev-token>` in `.env.local`
3. Ensure the backend is running (`docker compose up -d` + `uvicorn ...`)
4. `npm run dev` — the Vite proxy forwards `/api/*` to `localhost:8000`

**What still needs live-backend integration** (flagged in PR body):
- Turn taking (the mock advances scenes but doesn't call the real narrator LLM)
- Real character attribute rolling (mock uses pre-defined values)
- Combat math (mock uses hardcoded attack strengths)
- Actual session lease expiry and renewal
- Account management (`GET /me`, `DELETE /me`)
- GDPR export (`GET /me/export`)

---

## Environment Variables (`.env.local`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_USE_MOCK` | `false` | Set to `true` to use mock API handlers |
| `VITE_DEV_TOKEN` | `''` | Dev auth token (sent as `Authorization: Bearer <token>`) |
| `VITE_API_BASE_URL` | `/api` | API base URL (Vite proxies this to localhost:8000) |

Copy `.env.local.example` to `.env.local` and fill in values.
