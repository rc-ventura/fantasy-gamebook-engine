# Tasks: Real OIDC Login Flow (Frontend)

**Input**: Design documents from `specs/008-oidc-frontend-login/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/oidc-client-contract.md](./contracts/oidc-client-contract.md),
[quickstart.md](./quickstart.md), [ADR-034](../../docs/adrs/ADR-034-oidc-frontend-spa-pkce-public-client.md)

**Tests**: Included — spec 008's own acceptance criteria (SC-005) require the flow to be
provable via browser automation with zero mocks/backdoors, so Playwright e2e coverage
against the real Dex+backend stack is part of "done," not optional polish.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) so each
is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3, per spec.md's three user stories
- All paths are repo-root-relative

---

## Phase 1: Setup

**Purpose**: Bring in the new dependency and its config surface before any code depends on it.

- [X] T001 Add `react-oidc-context` and `oidc-client-ts` to `frontend/package.json` dependencies; `npm install` to update `frontend/package-lock.json`
- [X] T002 [P] Add `VITE_OIDC_AUTHORITY` and `VITE_OIDC_CLIENT_ID` to the `ImportMetaEnv` interface in `frontend/src/vite-env.d.ts`, with doc comments noting the defaults (local Dex) and that production sets real values

**Checkpoint**: Dependency installed, env vars typed — no runtime behavior yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Nothing in any user story can run until Dex accepts a public-client PKCE
exchange and the app has a shared `UserManager` instance mounted.

**⚠️ CRITICAL**: Complete this phase before any User Story phase.

- [X] T003 In `docker/dex/config.yaml`, convert the `gamebook` static client to a public
  client: replace `secret: gamebook-secret-dev` with `public: true`, and replace
  `redirectURIs` (`localhost:3000/callback`, `localhost:8000/callback` — neither matches
  a real running service) with `http://localhost:5173/callback` (Vite dev server) and
  `http://localhost:8080/callback` (docker-compose `gameobs` frontend). See
  [contracts/oidc-client-contract.md](./contracts/oidc-client-contract.md) for the exact
  target block.
- [X] T004 Create `frontend/src/auth/oidcConfig.ts`: build and export a single
  `oidc-client-ts` `UserManager` instance — `authority` from
  `import.meta.env.VITE_OIDC_AUTHORITY` (default `http://localhost:5556/dex`),
  `client_id` from `import.meta.env.VITE_OIDC_CLIENT_ID` (default `gamebook`),
  `redirect_uri: ${window.location.origin}/callback` (computed, not env-driven — always
  correct regardless of dev/compose/prod origin), `scope: 'openid profile email'`,
  `userStore: new WebStorageStateStore({ store: window.sessionStorage })` (matches the
  dev stub's existing storage — see research.md), `automaticSilentRenew: true`. This is
  the one `UserManager` instance both `<AuthProvider>` (T005) and the token bridge (T009)
  must share.
  **Implementation finding (not anticipated in planning)**: Dex's configured
  `issuer` (`http://dex:5556/dex`, baked into every token's `iss`) is a
  container-network hostname the browser cannot resolve — standard `.well-known`
  discovery from the browser-reachable URL would return endpoint URLs the browser
  could never reach. Added a `VITE_OIDC_ISSUER` env var (`vite-env.d.ts`) and, only
  when it differs from `VITE_OIDC_AUTHORITY`, hand-seed `metadata` (auth/token/jwks
  endpoints at the browser-reachable host URL, `issuer` matching the real token
  claim) instead of relying on discovery — verified as a supported
  `oidc-client-ts` pattern via its docs. Defaults reproduce today's local Dex setup
  with zero config; a real provider (VITE_OIDC_AUTHORITY set, VITE_OIDC_ISSUER
  unset) gets normal `.well-known` discovery, no Dex-specific behavior leaks into
  that path.
- [X] T005 In `frontend/src/main.tsx`, wrap `<App>` in `<AuthProvider userManager={userManager}>`
  (the instance from T004), between `<ErrorBoundary>` and `<BrowserRouter>`. Pass
  `onSigninCallback` clearing OIDC query params after a processed callback:
  `() => window.history.replaceState({}, document.title, window.location.pathname)`.
  Also added the T010 token-bridge side-effect import here (pulled forward from
  Phase 3 since `main.tsx` only needed one edit for both).
- [X] T006 [P] Add `ARG VITE_OIDC_AUTHORITY` / `ARG VITE_OIDC_CLIENT_ID` (with `ENV` set
  from the `ARG`, same pattern as needed for any other `VITE_*` build-time var) to
  `frontend/Dockerfile` before `RUN npm run build`, so a real deployment can target a
  different OIDC provider via `docker build --build-arg` without editing source
  (spec 008 Assumption: "must not hardcode Dex-specific behavior"). Also added
  `VITE_OIDC_ISSUER` for symmetry with T004's finding.

**Checkpoint**: Dex accepts PKCE from a public client; the SPA has one shared OIDC
session object mounted app-wide. No user-facing behavior has changed yet.

---

## Phase 3: User Story 1 - Sign in with real credentials through the browser (Priority: P1) 🎯 MVP

**Goal**: Clicking **Login** takes the player to Dex's real sign-in page; on success
they land back in the app already authenticated, with zero token entry, and the first
authenticated API call succeeds.

**Independent Test**: [quickstart.md](./quickstart.md) — "Story 1" and its invalid-credentials
edge case, using only a browser against the `gameobs` compose stack (or Dex + native
backend + `npm run dev`).

### Implementation for User Story 1

- [X] T007 [US1] Create `frontend/src/pages/CallbackPage.tsx`: consumes the library's
  `useAuth()` (from `react-oidc-context`); while `isLoading`, render a minimal
  loading state; on `isAuthenticated` becoming `true`, `navigate('/dashboard', { replace: true })`;
  on `auth.error`, `navigate('/auth', { replace: true, state: { error: auth.error.message } })`
  (FR-006 — clean error, not a dead end).
- [X] T008 [US1] Add a public `/callback` route rendering `CallbackPage` in
  `frontend/src/App.tsx`, outside `ProtectedRoute` (it runs before the app knows the
  player is signed in).
- [X] T009 [US1] Rewrite `frontend/src/hooks/useAuth.ts` to back `authenticated`/`signIn`/`signOut`
  with `react-oidc-context`'s `useAuth()`: `authenticated` ← `auth.isAuthenticated`,
  `signIn` ← `() => auth.signinRedirect()`, `signOut` ← `() => auth.removeUser()`. Keep
  the exported hook shape (`{ authenticated, signIn, signOut }`) so no non-auth
  component needs to change (the seam `client.ts` was already built for, per
  `setTokenProvider()`'s existing doc comment).
  **Implementation refinement**: kept `signIn`'s `devToken?: string` parameter as
  *optional* rather than dropping it — FR-009 requires the dev-paste fallback to keep
  working *alongside* real OIDC, not be replaced by it (spec 008 Assumption: retained
  "behind the same kind of production guard already established," not deleted). Calling
  `signIn()` with no argument starts the real redirect; calling it with a token uses the
  existing sessionStorage-paste path, gated to `import.meta.env.DEV` at the mock-toggle
  level (`hasDevToken()`) and mirrored in `tokenBridge.ts`'s fallback so API calls (not
  just the `authenticated` flag) honor it too.
- [X] T010 [US1] Create `frontend/src/auth/tokenBridge.ts`: subscribe to the shared
  `UserManager` from T004 (`userManager.events.addUserLoaded` / `addUserUnloaded`) to
  cache the current session's `id_token` in a module-level variable (not
  `access_token` — see research.md for why), and call
  `setTokenProvider(() => cachedIdToken)` (from `frontend/src/api/client.ts`) once at
  module load. Import this module once from `main.tsx` (side-effect import) so it's
  wired before any API call can happen. This keeps `client.ts`'s synchronous
  `_tokenProvider` signature unchanged while sourcing it from the real OIDC session
  instead of `sessionStorage.getItem('auth_token')`.
- [X] T011 [US1] In `frontend/src/pages/AuthPage.tsx`: replace the sign-in submit
  handler with a **Login** button calling `signIn()` (from the rewritten `useAuth()`,
  T009) — this becomes the primary path (FR-001). Gate the existing dev token-paste
  field (and its submit-with-pasted-token behavior) behind `import.meta.env.DEV`
  (matches the existing guard pattern in `ErrorBoundary.tsx` / `useGame.ts`) so it is
  absent from a production build (FR-009). Surface any `error` passed via router
  `location.state` from `CallbackPage` (T007).
  **Implementation refinement**: removed the Sign In/Register tab toggle — the
  "Register" tab was already non-functional scaffolding (its email field was never
  read by the submit handler, and Dex's local static-password config has no
  self-registration flow), and with a real redirect-based Login there is exactly one
  action; keeping a second, identical-behavior tab would be confusing UI, not a
  requirement preserved. Nothing else in the app links to a register-specific state
  (`LandingPage.tsx` only ever routes to plain `/auth`).
- [X] T012 [US1] [P] Create `frontend/playwright.oidc.config.ts`: same shape as
  `frontend/playwright.config.ts` but with **no** `webServer` block (assumes the
  `gameobs` compose stack is already running externally with real Dex + real backend —
  this must NOT run against `VITE_USE_MOCK=true`) and `testDir: './tests/e2e-oidc'`,
  `baseURL` from `PLAYWRIGHT_BASE_URL` defaulting to `http://localhost:8080`. Add an
  `test:e2e:oidc` script to `frontend/package.json` running
  `playwright test --config=playwright.oidc.config.ts`. Added to
  `tsconfig.node.json`'s `include` for parity with `playwright.config.ts`.
- [X] T013 [US1] [P] Write `frontend/tests/e2e-oidc/oidc-login.spec.ts`: drives Login →
  Dex's real form (`player1@example.com` / `gamebook-test-1`, from
  `docker/dex/config.yaml`) → lands on `/dashboard` authenticated → a subsequent API
  call (e.g. the account summary the dashboard loads) succeeds (Acceptance Scenarios
  1–4). Include the invalid-credentials edge case (Dex's own error page, retry without
  reload) and the replayed-`/callback`-URL edge case (revisit a spent callback URL,
  confirm it's routed to `/auth` with an error, not silently signed in again — FR-008).
  Selectors (`getByRole('button', { name: 'Login' })`, Dex's `email address`/`Password`
  textboxes) confirmed against the real Dex login form during live verification below,
  not guessed.
- [X] T014 [US1] [P] Add `frontend/tests/unit/hooks/useAuth.test.tsx`: mock
  `react-oidc-context`'s `useAuth()` and assert the wrapped hook's
  signed-out → pending → signed-in → loading(reload) transitions map correctly onto
  `{ authenticated, isLoading, signIn, signOut }` (the `isLoading` field was added
  during live verification — see below).

**Live verification (real Dex + real backend, `docker compose --profile gameobs up`,
driven via an actual browser — not simulated)**: the full Login → Dex sign-in →
`/dashboard` authenticated flow, the replay edge case, and sign-out were all exercised
for real and confirmed working. This surfaced four real bugs invisible to
typecheck/lint/unit tests, all now fixed:

1. **CSP blocked the token-endpoint fetch.** `index.html`'s existing
   `connect-src 'self'` (T098/FR-052 hardening) doesn't allow the OIDC provider's
   origin. Fixed in `frontend/vite.config.ts` via a `transformIndexHtml` plugin that
   injects the resolved OIDC origin into the CSP meta tag at build time — one source of
   truth (`VITE_OIDC_AUTHORITY`), no hardcoded Dex origin in the shipped policy.
2. **Dex rejected the token-endpoint fetch via CORS.** Dex disables CORS on
   discovery/token/keys endpoints unless `web.allowedOrigins` is set. Added to
   `docker/dex/config.yaml` for both frontend origins (5173, 8080).
3. **A Docker `ARG` with no default becomes an empty string, not "unset."** My
   `frontend/Dockerfile` ARG→ENV passthrough (T006) meant `import.meta.env.VITE_OIDC_AUTHORITY`
   was `""` rather than `undefined` in the compose build, and `??` doesn't treat `""`
   as nullish — silently turned every seeded OIDC endpoint into a same-origin relative
   path (`/auth` instead of `http://localhost:5556/dex/auth`), so clicking Login just
   navigated back to the current page with no visible error. Fixed by switching
   `oidcConfig.ts`'s fallbacks from `??` to `||`.
4. **Real FR-004 bug: reload bounced a valid session to `/auth`.** `ProtectedRoute`
   read `authenticated` synchronously on first render, before
   `react-oidc-context` finished asynchronously rehydrating the session from
   `sessionStorage` — every reload of a protected route redirected to `/auth`
   regardless of a valid persisted session. Fixed by adding `isLoading` to `useAuth()`
   (true only while the real OIDC path is still determining state) and having
   `ProtectedRoute` (`App.tsx`) render nothing until it resolves, matching how T015/T016
   (User Story 2) were always going to need this same signal — pulled forward here
   since it blocked proving User Story 1's own "first authenticated call succeeds"
   claim on anything but a first load.

None of these four would have been caught by `tsc`, `eslint`, or the mocked unit
suite — all require a real Dex + real backend + a real browser, exactly what
spec 008's own SC-005 says "done" requires. After all four fixes,
`npm run test:e2e:oidc` (T012/T013) was run for real against the `gameobs` stack:
**8/8 passed** — Login → real Dex form → authenticated dashboard, invalid credentials,
replay rejection, sign-out, no-secret-in-token-exchange, reload persistence, and
cleared-session redirect all green with zero mocks.

**Checkpoint**: User Story 1 is fully functional and independently testable — a player
can sign in for real, with no other story's work required. Verified live, not just by
inspection.

---

## Phase 4: User Story 2 - Session persists without repeating the manual flow (Priority: P2)

**Goal**: A signed-in player stays signed in across a reload; an expired session sends
them cleanly back through Story 1's real login, never to a broken state.

**Independent Test**: [quickstart.md](./quickstart.md) — "Story 2."

### Implementation for User Story 2

- [X] T015 [US2] Confirm (add a regression test if not already covered by T014) that a
  page reload rehydrates `authenticated: true` from the `sessionStorage`-backed
  `userStore` (T004) without re-invoking `signinRedirect()` — this is largely inherited
  from T004/T009's design; this task is the explicit verification + test for FR-004.
  **This is what surfaced finding #4 under T012–T014 above** (`ProtectedRoute` redirected
  before rehydration finished) — fixed there via `useAuth()`'s new `isLoading` field.
  Covered by `useAuth.test.tsx`'s "reports isLoading while rehydrating" case and, live,
  by `oidc-login.spec.ts`'s "a signed-in session survives a page reload" (passed against
  the real stack, see T012–T014's live-verification note).
- [X] T016 [US2] Confirm `frontend/src/hooks/useGame.ts`'s existing 401/403 →
  `redirectToAuth()` behavior (already tested in
  `frontend/tests/unit/hooks/useGameAuthRedirect.test.tsx`) still fires correctly once
  the bearer token comes from `tokenBridge.ts` (T010) instead of the old
  `sessionStorage` dev-token read — i.e. an expired/cleared OIDC session produces a
  `null` token, the API call 401s, and the existing redirect logic (unchanged) sends the
  player to `/auth` (FR-005). Verified: the existing 6-test suite still passes unchanged
  (the interceptor mocks `../api` directly, insulated from the token source), and live,
  clearing `sessionStorage` on a protected route correctly redirects to `/auth`
  (`oidc-login.spec.ts`'s "a cleared session routes back to /auth" — passed).
- [X] T017 [US2] [P] Extend `frontend/tests/e2e-oidc/oidc-login.spec.ts` (or add a
  sibling spec in `frontend/tests/e2e-oidc/`): sign in, reload the tab, confirm still
  authenticated (no redirect to `/auth`); then clear the `sessionStorage` OIDC user key
  via `page.evaluate`, trigger a protected action, and confirm the app routes to
  `/auth` rather than showing a broken/blank screen. Both scenarios are in the
  "Session persistence (User Story 2)" describe block — ran for real against the
  `gameobs` stack, both passed (see T012–T014's live-verification note: 8/8 total).

**Checkpoint**: User Stories 1 and 2 both work independently and together — proven live
against the real stack, not just by inspection.

---

## Phase 5: User Story 3 - No long-lived secret ever reaches the browser (Priority: P3)

**Goal**: Prove — not just assert — that no shared secret exists in the shipped bundle
or in the login flow's network traffic.

**Independent Test**: [quickstart.md](./quickstart.md) — "Story 3."

### Implementation for User Story 3

- [X] T018 [US3] [P] Add `frontend/tests/unit/audit/no-oidc-secret.test.ts` — regression
  guard for SC-003. **Implementation refinement**: scans the tracked `frontend/src/`
  source tree (not a built `dist/`) for the literal `gamebook-secret-dev` value and any
  hardcoded `client_secret: '...'` in `oidcConfig.ts`, rather than grepping a build
  artifact — catches a leak before it could even reach a build, and needs no `npm run
  build` step to run in CI. (Checking the built bundle for the generic string
  `client_secret` was tried live and rejected: `oidc-client-ts`'s own library code
  contains that field *name* unconditionally — e.g. `client_secret_post`, the
  never-populated `client_secret:s` property — so it would always false-positive; only
  the literal secret *value* is a meaningful signal.) 3/3 pass.
- [X] T019 [US3] Run the quickstart.md Story 3 pass — **done live**, not just by
  construction: captured the real `token` POST request body during the live-verification
  session above. Body was exactly
  `grant_type=authorization_code&redirect_uri=...&code=...&code_verifier=...&client_id=gamebook`
  — no `client_secret` field. Also confirmed via `docker exec` grep on the built,
  nginx-served bundle: zero occurrences of `gamebook-secret-dev`; the only
  `client_secret` occurrences are the library's own field name/constant
  (`client_secret_post`), never a value.

**Checkpoint**: All three user stories independently functional; SC-003 has both an
automated guard (T018) and a manual confirmation (T019).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Clean up now-stale references to the old dev-stub-only world.

- [X] T020 [P] Update the stale "Real OIDC lands in slice 004" / "Slice 004 will
  replace" comments in `frontend/src/api/client.ts` (`setTokenProvider()` doc comment)
  and (if any remain after T009/T011) `frontend/src/hooks/useAuth.ts` /
  `frontend/src/pages/AuthPage.tsx` to reflect that 008 is what implements real OIDC.
  `useAuth.ts`/`AuthPage.tsx` had none left (written fresh in T009/T011); fixed the two
  in `client.ts`. Left the *separate*, pre-existing "stub — real impl in slice 004"
  comments on `acquireSession`/`takeoverSession`/`releaseSession` alone — those are
  about session-lease wiring, a real but unrelated gap already noted as out-of-scope in
  research.md, not something this slice touches.
- [X] T021 [P] Ran the full [quickstart.md](./quickstart.md) validation pass end-to-end
  against the real `gameobs` stack (not just the compose smoke test):
  - **Story 1** (all 4 acceptance scenarios + invalid-credentials edge case): live via
    browser automation, then automated in `oidc-login.spec.ts` — pass.
  - **Story 2** (reload persistence, expired/cleared-session redirect): live, then
    automated — pass. (Surfaced and fixed the real `isLoading`/reload bug — see
    T012–T014.)
  - **Story 3** (no secret in traffic or source): live network inspection of the actual
    `token` POST body + automated source-scan (`no-oidc-secret.test.ts`) — pass.
  - **Replay edge case**: live + automated — Dex/oidc-client-ts's own
    "No matching state found in storage" error, routed to `/auth` — pass.
  - **Sign-out**: live + automated — clears `sessionStorage`, protected routes require
    signing in again — pass.
  - **Dev-stub backward compatibility (FR-009)**: live — dev build (`npm run dev`)
    shows the token-paste fallback and it authenticates correctly; the production
    compose build (nginx-served, `import.meta.env.DEV === false`) shows no trace of it
    — pass.
  - Full existing regression suites re-run clean throughout: 69/69 unit tests (vitest),
    13/13 mock-mode e2e tests (Playwright), `tsc -b --noEmit` clean, `eslint src` clean
    (one pre-existing unrelated warning in `CreateHeroPage.tsx`, not touched by this
    slice).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks all user stories** — T003
  (Dex public client) and T004/T005 (shared `UserManager` + mounted `AuthProvider`) must
  exist before any story's code can run against a real session.
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational **and** User Story 1 (T009's
  `useAuth()` rewrite, T010's token bridge) — session persistence is a property of the
  same session object US1 creates, not a separate mechanism.
- **User Story 3 (Phase 5)**: Depends on Foundational **and** User Story 1 (T003's
  public-client conversion, which is what makes SC-003 true). Can run in parallel with
  User Story 2 — they touch disjoint files.
- **Polish (Phase 6)**: Depends on whichever stories are in scope for the change being
  shipped.

### Parallel Opportunities

- T002 (env var typing) can run alongside T001 (dep install).
- T006 (Dockerfile ARG/ENV) can run alongside T003–T005 (different file).
- Within User Story 1: T012 (Playwright config) and T014 (unit test) can start once
  T009/T010 exist, in parallel with each other and with T013 once T012 lands.
- User Story 2 (Phase 4) and User Story 3 (Phase 5) touch disjoint files and can proceed
  in parallel once User Story 1 is done.
- T020 and T021 (Polish) can run in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (User Story 1).
2. **STOP and VALIDATE**: run `quickstart.md` Story 1 against a real `gameobs` compose
   stack — real Login button, real Dex form, real signed-in dashboard, zero pasted
   tokens.
3. This alone already satisfies FR-001–FR-003, FR-006–FR-009 and SC-001/SC-002/SC-005.

### Incremental Delivery

1. Setup + Foundational → Dex accepts PKCE, `AuthProvider` mounted.
2. User Story 1 → real login works end-to-end (MVP, demoable).
3. User Story 2 → reload/expiry handled cleanly (FR-004/FR-005).
4. User Story 3 → automated + manual proof that FR-002/SC-003 hold (mostly verification,
   since T003 already makes it true).
5. Polish → stale comments cleaned up, full quickstart re-run recorded.
