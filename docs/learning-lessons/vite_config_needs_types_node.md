# Vite config (`vite.config.ts`) requires `@types/node` as an explicit devDependency

**Context:** Scaffolding the `frontend/` SPA with Vite 5 + TypeScript 5. The `vite.config.ts`
used `import { resolve } from 'path'`, `__dirname`, and `process.env[...]`.
**Date:** 2026-06-27
**Future intent:** Any Vite + TypeScript project that uses `path`, `__dirname`, or `process`
in `vite.config.ts` must declare `@types/node`.

---

## The issue

Running `npm run build` (which runs `tsc -b && vite build`) failed with:

```
vite.config.ts(3,25): error TS2307: Cannot find module 'path' or its corresponding type declarations.
vite.config.ts(11,20): error TS2304: Cannot find name '__dirname'.
vite.config.ts(33,7): error TS2580: Cannot find name 'process'. Do you need to install type
declarations for node? Try `npm i --save-dev @types/node`.
```

This happened despite `tsconfig.node.json` using `"moduleResolution": "bundler"` and including
`vite.config.ts`. TypeScript cannot resolve Node.js built-in module types or globals (`process`,
`__dirname`) unless `@types/node` is explicitly installed.

## Root cause

`@types/node` is **not** a transitive dependency of `vite` or `@vitejs/plugin-react` in npm's
dependency model — they include their own ambient declarations for just enough to run Vite's
internals. When the project's own `vite.config.ts` directly imports `path` or uses
`__dirname`/`process`, it needs the `@types/node` package to supply those type declarations.

## Fix

Add `@types/node` to `devDependencies`:

```json
"@types/node": "^26.0.1"
```

`npm install --save-dev @types/node` adds it and resolves all three errors. `typecheck`,
`lint`, and `build` all pass after.

## Prevention

Always add `@types/node` to `devDependencies` when `vite.config.ts` uses:
- `import { ... } from 'path'` (or `'fs'`, `'url'`, etc.)
- `__dirname`, `__filename`
- `process.env[...]` or `process.cwd()`

The Vite scaffold template from `npm create vite` typically includes `@types/node` only if you
select the `ts-node` or similar template variants; the base React + TypeScript template does not.
