# Phase 0 — Research & Technology Decisions

Feature: Web Platform Migration · Date: 2026-06-26

Each decision resolves an unknown from Technical Context or a deferred item from the spec. Format:
**Decision · Rationale · Alternatives considered**.

---

## 1. Storage backend — `PostgresStorage` behind `StorageBackend`

**Decision**: PostgreSQL accessed via SQLAlchemy 2.x Core + `asyncpg`, with Alembic migrations.
Implement a new `PostgresStorage(StorageBackend)` in `src/gamebook/storage/postgres.py`. Each
domain aggregate (CharacterSheet, World, Events, Combat, ArchiveRecord) maps to a table; writes
run inside a single transaction per state change (atomic, all-or-nothing).

**Rationale**: The domain schema was "designed to map ~1:1 to Postgres tables later"
(`docs/CONTRACTS.md` §2, `docs/03-storage.md`). Postgres transactions give the Principle V
atomicity guarantee for free (the relational analogue of JSON's temp-file+rename). SQLAlchemy Core
keeps the mapping explicit and avoids ORM identity-map surprises; `asyncpg` fits the async FastAPI
stack and the ≥1,000-concurrent-campaign target. The existing `StorageBackend` interface and
in-memory test backend are reused unchanged — this is exactly swap boundary #1.

**Alternatives considered**: ORM-heavy SQLModel/Django ORM (more magic, weaker control over the
atomic write boundary); document store (Mongo) — rejected, the schema is already relational and
invariants/round-trip are cleaner in SQL; keeping JSONStorage in prod — rejected, no concurrency
or query story at scale.

---

## 2. New harness — PydanticAI narrator with Pydantic `Scene` (see ADR-011)

**Decision**: A narrator built on **PydanticAI core (`Agent`)**, behind a thin `NarratorBackend`
port (so a deterministic `FakeNarrator` can be injected for tests — Principle IV). It consumes the
**same MCP tool contract** via `MCPToolset` over the existing FastMCP server, returns a **`Scene`**
object — `{ narrative, choices[], effects[] }` — as its `output_type` (validated by Pydantic v2
before it can reach storage or the UI), and delegates fights to a **combat subagent** via agent
delegation. The model/provider is **agnostic** (PydanticAI model string), default
`anthropic:claude-opus-4-8` (Sonnet 4.6 for volume, Haiku 4.5 for cheap subtasks). This is the
swap-boundary-#3 decision — see
[ADR-011](../../docs/adrs/ADR-011-phase2-harness-pydanticai-narrator-backend.md).

**Rationale**: `docs/07-harness.md` already specifies Phase 2 as a structured-output narrator that
emits a `Scene` the frontend renders, reusing the same MCP + adventure module — this decision just
makes that concrete. Pydantic validation satisfies FR-014 (invalid narrator output is rejected
pre-persistence) and matches the existing domain's Pydantic v2 base. `claude-opus-4-8` is the
current most-capable Opus model and the default for new AI applications; adaptive thinking + effort
control replace any fixed thinking budget. The combat subagent maps 1:1 to the existing
`combat-sub-agent` SKILL, preserving the delegation pattern (ADR-001).

**Alternatives considered** (full record in ADR-011): hand-rolled loop on the raw Anthropic SDK —
rejected (more code; provider-agnosticism would be manual, whereas PydanticAI gives structured
output + MCP client + agnosticism natively while staying Pydantic-native). LangChain `deepagents` —
rejected as overkill for a bounded, structured turn (planner/virtual-FS not needed; memory already
lives in the engine). `pydantic-ai-harness` / CodeMode — **deferred**, not v1 (small per-turn tool
fan-out, interactive combat, and it routes tool calls inside code, bypassing the `Scene.effects[]` +
`output_validator` gate). Managed Agents (server-hosted) — rejected for v1 (we host our own compute,
engine MCP in-process). Keeping Claude Code as prod harness — rejected by clarification (terminal
harness is dev/test only).

**Enforcement note**: the narrator is structurally prevented from inventing numbers — `effects[]`
reference engine operations (roll/luck/combat/state mutations) rather than literal stat values, and
all numeric outcomes come back from MCP tool results. A PydanticAI `output_validator` raises
`ModelRetry` if a `Scene` carries a literal number. This is the Principle I gate at the harness
boundary.

---

## 3. Authentication — dedicated OIDC service, separate from the engine

**Decision**: Identity is provided by a **dedicated, separately-deployable OIDC/OAuth2 provider**.
Default to a self-hostable, standards-compliant IdP (Keycloak or Ory/Zitadel-class) issuing JWT
access tokens; the backend validates tokens (signature, audience, expiry) and maps `sub` → account.
The engine/API never stores passwords. A managed IdP (Auth0/Clerk/Cognito) is a drop-in alternative
since the integration is standard OIDC.

**Rationale**: The spec mandates "authentication as a separate service" (FR-007) decoupled from
gameplay. OIDC/JWT is the industry-standard web-app auth and keeps the engine stateless about
credentials. Per-account isolation (FR-009) is enforced in the API/data layer by scoping every
query to the authenticated `sub`. Graceful degradation when the IdP is unavailable (FR-024): cached
JWKS + short-lived token validation lets already-signed-in players continue read-only until tokens
expire, while new sign-ins fail with a clear message.

**Alternatives considered**: rolling our own user/password store — rejected, violates the
"separate service" directive and adds security surface; session-cookie monolith — rejected, doesn't
give the clean service boundary or the API-first story (FR-017).

---

## 4. Web API surface — FastAPI, one contract for UI and external clients

**Decision**: A FastAPI app exposes the engine as a documented, authenticated HTTP/JSON API
(OpenAPI auto-generated). The UI consumes the exact same API as external clients — no privileged
hidden path (FR-017). Endpoints cover the full play loop (read state, take a turn, resolve combat,
save/resume, manage characters). Drafted in `contracts/http-api.md`.

**Rationale**: FastAPI gives OpenAPI docs for free (FR-016), first-class Pydantic models (shared
with the domain/`Scene`), and an async stack matching `asyncpg`. Exposing the engine as an API is
an explicit goal (FR-015); making the UI just another client keeps one consistent contract.

**Alternatives considered**: GraphQL — rejected, the operation set is small and turn-oriented, REST
+ OpenAPI is simpler to document and consume; gRPC — rejected, browser/clients want plain JSON.

---

## 5. Frontend — separate professional SPA

**Decision**: A separate single-page app (React + Vite + TypeScript) in `frontend/`, consuming the
HTTP API via a typed client generated from the OpenAPI schema. Renders narration, numbered choices,
character sheet, inventory, map, and combat state — all from real engine state (FR-021).

**Rationale**: The spec requires a "distinct, professional front-end separate from the engine"
(FR-020). A typed client off the OpenAPI schema keeps the UI honest to the contract and prevents the
UI from fabricating values. React + Vite is a mainstream, well-supported choice for a polished SPA.

**Alternatives considered**: server-rendered templates inside FastAPI — rejected, doesn't deliver a
"separate professional UI" and couples UI to the engine process; a different framework (Svelte/Vue)
— acceptable, React chosen for ecosystem familiarity; specific tech is a frontend-team call.

---

## 6. Single active session per campaign (FR-025)

**Decision**: Enforce one active play session per campaign with a short-lived **session lease**
held in the datastore (a row with `campaign_id`, `session_token`, `expires_at`). A second opener
gets read-only until it explicitly "takes over", which atomically reassigns the lease and demotes
the prior holder. Writes require holding the current lease; stale-lease writes are rejected.

**Rationale**: This is the clarified concurrency policy — the strongest integrity guarantee for a
solo game and the simplest to reason about. It composes with the atomic-write requirement
(Principle V): a write is gated on both a valid lease and a transactional commit, so concurrent
campaign edits cannot corrupt or silently overwrite state.

**Alternatives considered**: optimistic locking (version column, reject stale writes) and
last-write-wins — both surfaced in clarification and rejected by the user in favor of single active
session.

---

## 7. Observability — OpenTelemetry, vendor-neutral

**Decision**: Instrument the backend with OpenTelemetry (traces, metrics, logs) exported via OTLP
to a backend the operator chooses (e.g. Grafana/Tempo/Prometheus or a managed APM). Emit at minimum
health, error rate, latency, and basic play metrics (FR-022), with per-request traces that can
locate a failing turn without exposing internal failure as corrupted game state (FR-023).

**Rationale**: OTel is the vendor-neutral standard; exporting via OTLP avoids lock-in and lets the
operator pick a backend. The required signals map directly to SC-009 (operators can detect and
locate an induced failure from telemetry alone).

**Alternatives considered**: bespoke logging only — rejected, no traces/metrics story for SC-009;
a single proprietary APM SDK — rejected for lock-in (OTel can still export to it).

---

## 8. Privacy / compliance posture (deferred from spec — resolved here)

**Decision**: Adopt a **GDPR-aligned baseline**: treat account data as personal data, minimize
stored PII (the engine stores game state keyed by an opaque account id; the IdP owns
credentials/profile), and support **account data export and deletion/erasure**. Deletion cascades to
the player's campaigns, characters, events, and archives; export returns the player's game data in a
portable format.

**Rationale**: The spec deliberately deferred the posture to planning; with EU-facing public signup
the responsible default is GDPR-style export+delete. Keeping credentials/profile in the separate IdP
shrinks the engine's PII footprint, so most erasure work is "delete this account's game rows" plus an
IdP delete. This adds concrete data-model and API obligations (see data-model.md and
`contracts/http-api.md`: `DELETE /me`, `GET /me/export`).

**Alternatives considered**: basic protection only (no formal export/erasure) — rejected as the
weaker compliance story for a public EU product; defer again — rejected, the plan phase is where it
should land, and it materially shapes the data model.

---

## 9. Resolved unknowns summary

| Unknown (Technical Context / spec) | Resolution |
|---|---|
| Storage technology | PostgreSQL + SQLAlchemy Core + asyncpg behind `StorageBackend` (§1) |
| New harness framework + model | PydanticAI core behind a `NarratorBackend` port; model-agnostic, default `anthropic:claude-opus-4-8`; `Scene` output, combat delegation (§2, ADR-011) |
| Auth method/provider | Dedicated OIDC/OAuth2 service, JWT validation (§3) |
| API style | FastAPI REST + OpenAPI, shared by UI and external clients (§4) |
| Frontend stack | Separate React + Vite + TypeScript SPA (§5) |
| Concurrency policy | Single active session per campaign via session lease (§6) |
| Observability stack | OpenTelemetry → OTLP, operator-chosen backend (§7) |
| Privacy/compliance posture | GDPR-aligned export + erasure baseline (§8) |
| Availability target | Best-effort, no SLA at launch (from clarification); integrity guarantees unconditional |
