# ADR-012: React + Vite + TypeScript toolchain for `frontend/`

**Status**: Accepted
**Date**: 2026-06-27
**Related spec**: [005-professional-spa](../../specs/005-professional-spa/spec.md), [001-web-platform-migration research §5](../../specs/001-web-platform-migration/research.md)

---

## Context

Slice `005-professional-spa` adds a professional browser-facing SPA that is **just another
consumer of `003`'s documented HTTP API** — no privileged path, no engine changes (research.md
§5, FR-017). The frontend technology stack is a frontend-team call per research.md §5, which
mandates "a separate React + Vite + TypeScript SPA under `frontend/`, consuming the HTTP API
via a typed client generated from the OpenAPI schema; tests via vitest (unit) + Playwright
(E2E)."

Four decisions needed to be made concrete before scaffolding:

1. **Exact framework and version** — React 18 vs earlier; Vite 5 vs 4.
2. **TypeScript strictness** — the spec mandates "no `any`"; that requires compile-time
   enforcement, not just convention.
3. **Linting setup** — ESLint major version 8 vs 9 (flat config); which TypeScript-ESLint
   preset.
4. **Router** — whether routing lives in the SPA or on the server; and which library.

---

## Decision

Build `frontend/` with:

| Layer | Choice | Version |
|-------|--------|---------|
| UI framework | **React** | 18.3.x |
| Build tool | **Vite** | 5.4.x |
| Language | **TypeScript** (strict) | 5.5.x |
| Lint | **ESLint** (flat config) + `typescript-eslint` recommended-type-checked | 9.x |
| Lint plugins | `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh` | latest |
| Routing | **react-router-dom** | 6.26.x |
| Unit / component tests | **vitest** + `@testing-library/react` | 2.x / 16.x |
| E2E tests | **@playwright/test** | 1.46.x |

**TypeScript strictness flags** (`tsconfig.json`):
```json
"strict": true,
"noUnusedLocals": true,
"noUnusedParameters": true,
"noFallthroughCasesInSwitch": true
```
`@typescript-eslint/no-explicit-any: "error"` enforces the "no `any`" rule at lint time in
addition to compile time.

**Vite dev-server proxy**: `/api/*` proxied to `http://localhost:8000` (the FastAPI backend)
with the `/api` prefix stripped, so the frontend calls `/api/campaigns/...` in development and
the backend sees `/campaigns/...`.

**Auth seam**: `VITE_DEV_TOKEN` environment variable (`.env.local`, gitignored) carries the
dev auth stub token (slice 003's hardcoded bearer). When slice 004 delivers real OIDC, only
`.env.local` changes — zero play-loop component changes (Principle II swap boundary for auth,
matching the `NarratorBackend` port pattern from ADR-011).

**Package manager**: `npm` (matches repo tooling conventions; no workspaces complexity needed
for a single SPA).

---

## Rationale

### React 18 + Vite 5

Research.md §5 names React + Vite. React 18 is the current stable major (Concurrent Mode,
`createRoot`, Suspense for data). Vite 5 is the current stable major: ES-module native,
sub-second HMR, first-class React plugin, and a built-in dev-server proxy that handles the
`/api → localhost:8000` rewrite without an extra reverse proxy in development.

### TypeScript strict mode + ESLint `no-explicit-any`

The spec mandates "TypeScript strict mode, no `any`" (tasks.md definition of done). Two
enforcement layers are better than one: `strict: true` catches inference gaps at compile time;
`@typescript-eslint/no-explicit-any: error` catches `any` annotations that slip past tsc.
`noUnusedLocals` / `noUnusedParameters` keep dead code from accumulating (a common source of
`any` escapes).

### ESLint 9 flat config

ESLint 9 is the current major; its flat config (`eslint.config.js`) replaces the legacy
`.eslintrc` format, is simpler to compose, and is what new React + Vite projects expect.
`typescript-eslint` 8.x provides `recommended-type-checked` which enables full type-aware
rules — necessary for the `no-explicit-any` enforcement and for catching unsafe member access.

### react-router-dom v6

Client-side routing for the Landing / Auth / Dashboard / Play screens. v6 has been the current
stable major since late 2021; nested routes (`<Outlet>`) map cleanly onto the four-screen
prototype. Server-side routing is unnecessary: the SPA is a static bundle served from CDN or
FastAPI's `StaticFiles`.

### vitest + Playwright (declared now, wired in T002)

Declared as devDependencies in T001 so the lockfile is consistent; the test config and first
tests land in T002 (per tasks.md T002 = "set up vitest + Playwright"). Keeping the dep
declaration with the scaffold avoids a separate `npm install` step later.

---

## Alternatives Considered

### Svelte / Vue

Acceptable alternatives (research.md §5: "specific tech is a frontend-team call"). Rejected in
favour of React for ecosystem maturity, hiring familiarity, and the large library surface
available for component testing (`@testing-library/react`) and animation.

### Server-rendered templates inside FastAPI (Jinja2)

Rejected. Does not deliver the "distinct, professional front-end separate from the engine"
(spec FR-020 / research.md §5). Couples UI lifecycle to the backend process and precludes a
CDN-deployed SPA.

### Plain CDN React (no build step)

Rejected. Without TypeScript and a typed API client, the "no fabricated values" guarantee is
enforcement-by-convention only. The typed client off the OpenAPI contract is the mechanical
check (Principle I, FR-002/008).

### ESLint 8 (`eslintrc`)

The legacy config format; ESLint 9 flat config is the direction for all new projects. No
compelling reason to start with a deprecated config format.

### Bun / pnpm as package manager

Both are valid. `npm` chosen because (a) no workspace complexity is needed for a single SPA,
(b) it avoids adding another runtime to the project's toolchain surface, and (c) it is the
universal fallback that every contributor already has.

---

## Consequences

- `frontend/` is entirely self-contained — its `package.json` and `node_modules` are isolated
  from the Python project (`pyproject.toml`, `uv.lock`). The Python test suite (`uv run pytest`)
  is unaffected.
- The Vite dev-server proxy means the SPA is developed with `npm run dev` (port 5173) pointing
  at `uvicorn` on port 8000 — no CORS config needed for local dev.
- TypeScript `moduleResolution: "bundler"` (Vite 5 / TS 5 recommended) ensures path aliases
  (`@/*`) work without additional plugins.
- Adding a component library or animation library in a future task is a standard `npm install`
  — no ADR required unless it changes a cross-module contract (Principle III).
