# Auth/redirect/token-lifecycle flows require live testing: mocks and static analysis miss CSP, CORS, and timing bugs

**Context:** Discovered during spec 008 (`feat/008-oidc-frontend-login`), implementing a
real OIDC Authorization Code + PKCE login flow against Dex. Live browser testing against
a real Dex + real backend (`docker compose --profile gameobs`) found and fixed 4 bugs
invisible to `tsc`, `eslint`, mocked `vitest`, and mock-mode Playwright. The subsequent
SDD final-review cycle (QA + Security sub-agents doing code inspection, not live
testing) found 2 more bugs of the exact same shape — proving the pattern repeats even
after the first round of live testing "should have" caught everything.

**Future intent:** Any future slice that touches auth, session lifecycle, redirects, or
CSP/CORS config must include a live-stack pass (real IdP, real backend, real browser) as
a required step before being called done — not an optional nice-to-have layered on top
of green CI.

---

## Mental Model: Three layers of auth-flow correctness, each blind to what the layer below actually executes

```
tsc / eslint          →  types, syntax, dead code
        ↓ (blind to runtime config)
mocked unit tests      →  hook/component logic, given a FAKE provider
        ↓ (blind to real network, CSP, CORS)
mock-mode e2e           →  UI/route wiring, given a FAKE backend
        ↓ (never touches auth at all — mock mode skips it)
live e2e (real IdP)     →  the only layer where CSP headers, CORS
                            preflight, Docker env-var resolution, and
                            async rehydration races actually execute
```

| Layer | Where it acts | What it covers | What it doesn't cover |
|-------|---------------|-----------------|------------------------|
| `tsc -b --noEmit` / `eslint` | Source, compile-time | Types, syntax, unreachable code | Runtime config resolution (CSP, CORS, env vars), timing, network |
| Mocked unit tests (`react-oidc-context` mocked) | Hook/component logic in isolation | State transitions given a fake provider | Real network calls, real CSP, real Docker build-time env resolution |
| Mock-mode e2e (`VITE_USE_MOCK=true`) | Full app render, fake API | UI/route wiring | Anything OIDC-shaped — mock mode never exercises auth at all |
| Live e2e (real Dex + real backend + real browser) | Full stack, real network | CSP, CORS, redirect timing, Docker `ARG`/`ENV` resolution, async rehydration races | Nothing left for this bug class — this is the floor |

The dangerous part isn't that live testing is *better* — it's that the first three
layers can all be **fully green** while the actual login flow is completely broken, and
nothing in CI would ever tell you.

---

## The six bugs, in two batches

**Batch 1 — found via live browser testing during implementation** (documented in
`specs/008-oidc-frontend-login/tasks.md`):

1. CSP `connect-src 'self'` blocked the token-endpoint `fetch()` to Dex.
2. Dex itself rejected that same fetch via CORS (`web.allowedOrigins` wasn't set).
3. A Docker `ARG` with no default becomes an **empty string**, not `undefined`, when
   passed through to `ENV` — `??` doesn't treat `""` as nullish, so every seeded OIDC
   endpoint silently became a same-origin relative path (`/auth` instead of
   `http://localhost:5556/dex/auth`). Clicking "Login" just reloaded the current page,
   with no visible error.
4. `ProtectedRoute` redirected to `/auth` before `react-oidc-context` finished
   asynchronously rehydrating a persisted session from `sessionStorage` — every reload
   of a protected route bounced a *valid* session (a real FR-004 bug).

**Batch 2 — found via code inspection during the SDD final-review cycle**, *after*
batch 1 was already fixed and 8/8 live e2e tests were green
(`reports/sdd-final-review/008-oidc-frontend-login/cycle-1-20260708-0752.md`):

5. `automaticSilentRenew: true` is set, but the CSP fix for bug #1 only extended
   `connect-src`, never `frame-src` — the cross-origin iframe silent renewal needs is
   blocked. Enabled-but-dead config; only surfaces once a token is close to expiring.
6. `DashboardPage.tsx`'s `getAccount().then(...).catch(() => null)` swallows a 401
   instead of redirecting like `useGame.ts`'s interceptor does — a naturally-expired
   (not manually-cleared) session dead-ends on the dashboard's own load path.

Common thread across all six: none require a *logic* bug in the traditional sense — each
is a real browser, a real redirect, a real CSP/CORS header, or real timing doing exactly
what it's supposed to do, in a configuration nobody had actually exercised end-to-end.

---

## Examples for Fantasy Gamebook Engine

### 1. The `??` vs `||` footgun (bug #3)

```ts
// frontend/src/auth/oidcConfig.ts — wrong (accepts "" as "configured")
const authority = import.meta.env.VITE_OIDC_AUTHORITY ?? 'http://localhost:5556/dex'

// fixed — treats any falsy value (including "") as "not configured"
const authority = import.meta.env.VITE_OIDC_AUTHORITY || 'http://localhost:5556/dex'
```

No amount of `tsc`/`eslint`/unit testing would catch this: `import.meta.env.VITE_OIDC_AUTHORITY`
is a valid `string` either way, so the types check out. It only fails when Docker
actually builds the image without `--build-arg`.

### 2. CSP fixed for one path, silently missing another (bugs #1 and #5)

```ts
// frontend/vite.config.ts — fixed connect-src (bug #1) for the token fetch...
return html.replace("connect-src 'self'", `connect-src 'self' ${oidcOrigin}`)
```

...but `automaticSilentRenew: true` in `frontend/src/auth/oidcConfig.ts` needs
`frame-src`, which nobody added, because the live-testing pass that caught bug #1 only
exercised the *login* path — a token never actually got close enough to `exp` during
that session to trigger a silent renew attempt.

### 3. Reload-race gate (bug #4)

```tsx
// frontend/src/App.tsx
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { authenticated, isLoading } = useAuth()
  if (isLoading) return null   // <- added after live reload testing found the bug
  if (!authenticated) return <Navigate to="/auth" replace />
  return <>{children}</>
}
```

The `isLoading` field didn't exist in the original design — it was added specifically
because a *reload* (not a fresh navigation) surfaced a race that no unit test triggers,
since unit tests render a hook once and inspect the result, they don't model "the
library is still asynchronously reading `sessionStorage` on mount."

---

## Relation to ADRs and next steps

- **ADR-034** (SPA-direct PKCE public client) — this lesson is a direct byproduct of
  implementing that decision; the ADR's own text now references the four batch-1 bugs
  as "invisible to tsc/eslint/mocked unit tests."
- **Next step**: the SDD final-review's Mandatory Action Items (CSP `frame-src`,
  dashboard 401 → `/auth`, IdP-unreachable error surfacing, fail-loud CSP replace,
  DEV-gate the fallback primitives, CI-runnable tests for `oidcConfig.ts`/`CallbackPage.tsx`)
  are tracked in `reports/sdd-final-review/008-oidc-frontend-login/cycle-1-20260708-0752.md`
  — treat them as the concrete completion of this lesson, not just a to-do list.
- **Process next step**: when planning a future auth/session/CSP-touching slice, budget
  time for a `docker compose --profile gameobs up --build` + real-browser pass as part
  of the definition of done, before considering the feature complete — not as an
  optional verification step to skip under time pressure.
