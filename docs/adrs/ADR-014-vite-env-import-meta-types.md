# ADR-014: `import.meta.env` types via `src/vite-env.d.ts` (not `tsconfig` types array)

**Status**: Accepted | **Date**: 2026-06-27 | **Branch**: `feat/005-spa`

## Context

Vite exposes environment variables through `import.meta.env.VITE_*`. TypeScript's DOM lib does not include the `ImportMeta.env` property from Vite's client types (`vite/client`). Without proper typing:
- `import.meta.env` has type `never` or produces `TS2339: Property 'env' does not exist`
- Every `VITE_*` access requires unsafe casts
- The strict no-`any` rule can't be satisfied

Two approaches exist:
1. Add `"types": ["vite/client"]` to `tsconfig.app.json`
2. Add `/// <reference types="vite/client" />` via a `src/vite-env.d.ts` file with a typed `ImportMetaEnv` interface

## Decision

Use a `src/vite-env.d.ts` file that:
- Declares `/// <reference types="vite/client" />` to pull in Vite's base types
- Augments `ImportMetaEnv` with typed declarations for every `VITE_*` variable used in the project
- Is included automatically by `tsconfig.app.json` via `"include": ["src"]`

This approach is preferred over the `types` array because:
- **Self-documenting**: all expected env vars are listed in one place, with comments explaining their purpose and which slice delivers them
- **Precision**: only the vars actually used are declared; typos in `import.meta.env.VITE_TYPO` become compile errors
- **Auth seam alignment**: `VITE_DEV_TOKEN` is documented at the type level as "replaced by real OIDC in slice 004" — a compile-time contract for the seam

## Consequences

- Accessing an undeclared `VITE_*` var is a TypeScript error (good: prevents typos)
- Adding a new env var requires updating `src/vite-env.d.ts` (small overhead, justified by the doc value)
- The file is a standard Vite template convention — maintainers are familiar with it

## Learning Lesson

`import.meta.env` is typed by `vite/client`, not by the standard TypeScript DOM lib. Projects that use Vite with `strict: true` and `"lib": ["DOM"]` must explicitly pull in the Vite client types. The `src/vite-env.d.ts` pattern is the idiomatic way to do this while also documenting the project's specific env var surface.

**Cross-reference**: documented in `docs/learning-lessons/vite-env-import-meta-types.md`
