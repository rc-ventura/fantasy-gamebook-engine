# ADR-020: Resolve duplicate ADR numbering (ADR-014 / ADR-015)

**Status**: Accepted | **Date**: 2026-06-28 | **Branch**: `feat/006-cycle1-remediation`

## Context

The SDD final review (cycle-1) flagged a **GOVERNANCE** issue: ADR numbers are
duplicated, violating the constitution's decision-record convention
(`.specify/memory/constitution.md` §Additional Constraints: "technical decisions are
recorded as ADRs (`docs/adrs/`)"). The `docs/adrs/` directory contains:

| File | Status | Content |
|---|---|---|
| `ADR-014-postgres-storage-sync-async-bridge.md` | real | PostgresStorage sync/async bridge (2026-06-27) |
| `ADR-014-pydantic-ai-v2-mcp-toolset-direct-call.md` | real | pydantic-ai 2.0 MCPToolset pattern (2026-06-27) |
| `ADR-014-vite-env-import-meta-types.md` | stub | "moved to ADR-015" pointer |
| `ADR-015-vite-env-import-meta-types.md` | real | `import.meta.env` types (2026-06-27) |
| `ADR-015-mock-mode-client-side-fixture-layer.md` | stub | "moved to ADR-016" pointer |
| `ADR-016-mock-mode-client-side-fixture-layer.md` | real | Mock mode fixture layer (2026-06-27) |

Two real ADRs share the number **014** (postgres-storage AND pydantic-ai). A partial
cleanup was attempted — the vite-env ADR was moved 014 → 015 and the mock ADR was
moved 015 → 016, leaving "moved" stubs behind — but the pydantic-ai ADR was **not**
renumbered, so it still collides with postgres-storage at 014.

The `CLAUDE.md` ADR table lists both as "ADR-014", perpetuating the ambiguity.

## Decision

1. **`ADR-014-postgres-storage-sync-async-bridge.md` keeps the number 014.** It is
   the first-created of the colliding pair and is referenced by
   `specs/002-persistence-foundation/tasks.md` T004.
2. **`ADR-014-pydantic-ai-v2-mcp-toolset-direct-call.md` is renumbered to
   `ADR-021`.** It is the next free number after the new ADRs 017–020 created in this
   remediation cycle. Chronological order is already broken by the original
   duplication; renumbering to 021 is honest and avoids further collisions. The file
   is renamed and its header updated; the `CLAUDE.md` table is updated to reference
   ADR-021.
3. **The two "moved" stub files are deleted**:
   - `ADR-014-vite-env-import-meta-types.md` (stub → real is at ADR-015)
   - `ADR-015-mock-mode-client-side-fixture-layer.md` (stub → real is at ADR-016)
   
   They are 7-line pointer files that add no value once the `CLAUDE.md` table is the
   authoritative index. The real ADRs (015, 016) remain.
4. **The `CLAUDE.md` ADR table is corrected** to list each ADR exactly once with its
   final number, and to add ADRs 017–021.

### Final ADR numbering after remediation

| ADR | Title |
|---|---|
| 014 | PostgresStorage sync/async bridge |
| 015 | `import.meta.env` types via `src/vite-env.d.ts` |
| 016 | Mock mode via client-side fixture layer |
| 017 | API/frontend contract canonical shape (backend wins) |
| 018 | Multi-tenant engine via per-call campaign_id |
| 019 | Allowlist for fabricated-number detection |
| 020 | Resolve duplicate ADR numbering (this ADR) |
| 021 | pydantic-ai 2.0 MCPToolset — `direct_call_tool` for routes, `toolsets=[]` for agents |

## Consequences

**Positive**:
- Every ADR has a unique number — constitution governance restored.
- The `CLAUDE.md` table is unambiguous; no more "ADR-014 (which one?)".
- Stub files removed — less clutter, one authoritative index.

**Negative**:
- ADR-021 (pydantic-ai) is out of chronological order (dated 2026-06-27 but numbered
  after 017–020 dated 2026-06-28). This is an unavoidable artifact of the
  renumbering; the date field in the ADR header preserves the true chronology.
- Any external reference to "ADR-014 pydantic-ai" breaks. A grep of the repo found
  references only in `CLAUDE.md` (updated in the same change) and the ADR's own
  learning-lesson cross-link (`docs/learning-lessons/pydantic_ai_v2_mcp_toolset_direct_call_pattern.md`),
  which is updated in the remediation tasks.

## When to retire

Not retired — this is a one-time governance fix. Future ADRs continue from 022.

## Related

- Remediation spec: `specs/006-cycle1-remediation/spec.md` (tasks include the rename
  and stub deletion)
- SDD review: `reports/sdd-final-review/001-web-platform-migration/cycle-1-20260628-0752.md`
  (GOVERNANCE action items)
- Constitution: `.specify/memory/constitution.md` §Additional Constraints
- `CLAUDE.md` ADR table (updated in the remediation spec)
