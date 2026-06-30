# RTK proxy rewrites `tsc` and masks TypeScript errors

**Date**: 2026-06-30

## Problem

The RTK (Rust Token Killer) hook rewrites `tsc`, `npx tsc`, and `npx tsc --noEmit` invocations transparently. Its output filtering can suppress or transform TypeScript compiler error output, making a build that has real errors appear clean.

## Evidence

During spec 007 SDD cycle-1 review, `npx tsc --noEmit` (via RTK) reported 0 TypeScript errors. Direct invocation with `node_modules/.bin/tsc -p tsconfig.app.json --noEmit` revealed 10 errors in `mock.ts` and `DashboardPage.tsx` — including a `TS2304: Cannot find name 'MOCK_COMBAT'` that would crash mock mode at runtime.

## Rule

For authoritative TypeScript error counts, always use:
```
node_modules/.bin/tsc -p tsconfig.app.json --noEmit
```

Never rely on `tsc`, `npx tsc`, or `rtk tsc` for definitive error counts in CI or review contexts.

## Applies to

- SDD review QA verification steps
- Any pre-merge frontend TypeScript gate
- Any CI script that checks TypeScript compilation
