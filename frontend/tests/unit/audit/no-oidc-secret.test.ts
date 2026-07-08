/**
 * Audit test: no-oidc-secret (SC-003, slice 008)
 *
 * Verifies no long-lived OIDC client secret is hardcoded anywhere in the
 * frontend source tree — the SPA uses Authorization Code + PKCE against a
 * public Dex client (ADR-034), so no secret should ever need to appear in
 * app code. Scanning source (not a built bundle) catches a leak before it
 * could even reach a build, and needs no `npm run build` step to run.
 *
 * Live confirmation that the actual network traffic carries no secret (the
 * complementary runtime check) lives in
 * tests/e2e-oidc/oidc-login.spec.ts's "no client secret appears in the token
 * exchange request" — this test is the static-source half of the guarantee.
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'fs'
import { join } from 'path'

const SRC_DIR = join(__dirname, '../../../src')

// The dev secret that used to live in docker/dex/config.yaml before ADR-034
// converted the client to public — this string must never appear in shipped
// app code. Kept as a literal (not imported) so a future re-introduction
// can't accidentally sidestep this check via a shared constant.
const KNOWN_SECRET_VALUE = 'gamebook-secret-dev'

function collectSourceFiles(dir: string): string[] {
  const files: string[] = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const stat = statSync(full)
    if (stat.isDirectory()) {
      files.push(...collectSourceFiles(full))
    } else if (/\.(ts|tsx)$/.test(entry)) {
      files.push(full)
    }
  }
  return files
}

describe('no-oidc-secret audit (SC-003, ADR-034)', () => {
  const sourceFiles = collectSourceFiles(SRC_DIR)

  it('scans a non-trivial number of source files', () => {
    // Sanity check that the scan itself isn't silently matching nothing.
    expect(sourceFiles.length).toBeGreaterThan(10)
  })

  it('never contains the known dev client secret value', () => {
    const offenders = sourceFiles.filter((f) => readFileSync(f, 'utf-8').includes(KNOWN_SECRET_VALUE))
    expect(offenders).toEqual([])
  })

  it('never sets client_secret to a literal string in the OIDC config', () => {
    const oidcConfig = readFileSync(join(SRC_DIR, 'auth/oidcConfig.ts'), 'utf-8')
    expect(oidcConfig).not.toMatch(/client_secret\s*:\s*['"]/)
  })
})
