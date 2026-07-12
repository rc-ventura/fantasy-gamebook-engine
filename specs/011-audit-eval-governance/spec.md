# Feature Specification: Audit, Evaluation & Observability Governance Layer

**Feature Branch**: `011-audit-eval-governance`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Audit, evaluation, and observability governance layer for the gamebook engine's AI-driven turn dispatcher and narrator. The system routes every player turn through an LLM-based intent classifier and a pure-narrator LLM call, with a deterministic code layer in between that is the only part proven trustworthy by tests. There is no regression harness for the classifier (a real bug — a required structured-output field silently never populated — shipped past a manual 'accepted' validation and was only found by accident). There is no durable per-campaign audit trail of dispatcher decisions (the tool built for this, `register_event`, has been unreachable since the narrator lost tool access; its table has zero rows despite dozens of campaigns played). Telemetry is only ever printed to a container's own stdout, and currently leaks the full narrator system prompt and player content into trace spans with no redaction. Even when the deterministic dispatcher is provably correct, the narrator can still narrate an event contradicting the settled facts, uncaught by the existing structural-only output validator. Two prior architecture decisions (ADR-030: OpenTelemetry + pydantic-evals as the stack; ADR-035: the eval harness is offline/batch, CI-gated, and explicitly not live-traffic scoring) constrain scope. Six related GitHub issues (#22-#27) catalog the gaps; a persistence gap unrelated to AI-decision auditing (#25, CampaignRegistry losing account association on restart) is explicitly out of scope."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Catch a classifier regression before it ships (Priority: P1)

A maintainer changes the intent classifier's prompt, or swaps which model it runs on, to improve or reduce cost. Before that change is merged, they need to know whether previously-working player scenarios (e.g., "move to the next area," "attack the thing blocking my path") still resolve to the correct mechanical action — without personally playing through the adventure live against a real model.

**Why this priority**: This is the exact gap that already let a real bug ship — a classifier change (or, in this case, an original oversight) silently broke an entire game mechanic, and the only reason it was noticed was an unrelated live inspection session. Without this, every future prompt/model change carries the same blind risk.

**Independent Test**: Can be fully tested by running the verification suite against the current classifier configuration and confirming it reports pass/fail per scenario, without needing any other part of this feature (audit trail, telemetry redaction, etc.) to exist.

**Acceptance Scenarios**:

1. **Given** a curated set of known player scenarios with their correct expected mechanical resolution, **When** the maintainer runs the verification suite against the current classifier, **Then** it reports, per scenario, whether the classifier's decision (including any required supporting details) matched the expected outcome.
2. **Given** the classifier's prompt is changed in a way that removes an instruction it needs to behave correctly, **When** the verification suite is run, **Then** at least one scenario fails and clearly identifies which behavior broke.
3. **Given** the verification suite passes on the current classifier configuration, **When** a change is proposed to the shared codebase, **Then** the change can carry that passing result as evidence, without requiring a live human play-testing session.

---

### User Story 2 - Reconstruct what happened in a specific campaign after the fact (Priority: P1)

A developer or support person needs to answer "what did the game actually decide happened in this player's campaign, and why?" — for example, investigating a player report that something seemed wrong, without being able to watch the session live.

**Why this priority**: Today this is impossible — the tool built for exactly this purpose is unreachable, and the only trace of a decision lives in a container's console output, gone the moment that container restarts. This blocks basic support/debugging for any AI-driven decision in the game.

**Independent Test**: Can be fully tested by playing a campaign through several mechanically significant moments (a zone entry, a combat, a dice-backed check), then querying that campaign's record independently of the process that served it, and confirming each decision is present with enough detail to explain it.

**Acceptance Scenarios**:

1. **Given** a campaign in which the player entered a new area, **When** someone inspects that campaign's record afterward, **Then** they can see which encounter (if any) was determined for that area and what the determination was.
2. **Given** a campaign in which a mechanical action was dispatched, **When** someone inspects that campaign's record afterward, **Then** they can see what action was dispatched and whether a required supporting detail came from the AI itself or from a fallback safeguard.
3. **Given** the server process that served a campaign has since restarted, **When** someone inspects that campaign's record, **Then** the record is still present and complete.

---

### User Story 3 - Trust that player content isn't leaking into operational telemetry (Priority: P2)

An operator responsible for the game's data-handling practices needs assurance that the operational monitoring data collected from real play sessions doesn't itself contain player-authored text or the full instructions given to the AI narrator.

**Why this priority**: This is a live, currently-occurring exposure (confirmed present today) rather than a hypothetical risk, but it doesn't block gameplay or block the classifier-verification work of User Story 1 — it's independently fixable and independently verifiable.

**Independent Test**: Can be fully tested by playing a turn and inspecting the resulting telemetry data directly, independent of whether the audit trail (Story 2) or classifier verification (Story 1) exist yet.

**Acceptance Scenarios**:

1. **Given** a real player takes a turn in production configuration, **When** the resulting telemetry data is inspected, **Then** it contains no player-authored narrative text and no full copy of the instructions given to the narrator.
2. **Given** someone is running the verification suite from User Story 1 (a non-production, synthetic-data context), **When** they choose to, **Then** they may still capture full content in that context for debugging the verification itself.

---

### User Story 4 - Find the operational data for a turn after the process that handled it is gone (Priority: P2)

An operator investigating a reported problem needs to find the relevant monitoring data (what happened, how long it took, whether anything failed) for a turn that occurred at some point in the past — potentially after the serving process has since restarted, been redeployed, or scaled down.

**Why this priority**: Directly enables diagnosing production issues; currently impossible because operational data only exists in a single process's own console output for as long as that process is alive.

**Independent Test**: Can be fully tested by taking a turn, restarting the serving process, and confirming the monitoring data for that turn is still retrievable through a query rather than by reading a specific process's console.

**Acceptance Scenarios**:

1. **Given** a turn was taken and the process that served it has since restarted, **When** an operator looks for that turn's monitoring data, **Then** they can retrieve it through a query rather than needing that specific process's console output.
2. **Given** a turn failed or took unusually long, **When** an operator investigates, **Then** they can find and correlate the relevant data without reproducing the failure live.

---

### User Story 5 - Detect when the narrator's story contradicts the settled facts (Priority: P3)

A maintainer wants to know, across a body of known test scenarios, how often the narrator describes something happening that contradicts what was actually mechanically resolved (e.g., describing an injury that the resolved outcome says did not occur), so this class of issue can be tracked and reduced over time rather than only discovered by accident.

**Why this priority**: A real, already-observed instance of this exists, but unlike Story 1 it concerns narrative *tone/content* fidelity rather than a game-breaking mechanical failure, and is inherently a matter of degree (an LLM narrator's prose is judged, not exactly matched) rather than a hard pass/fail — it builds on the verification approach from Story 1 rather than standing alone.

**Independent Test**: Can be fully tested by running a curated set of scenarios with a known settled outcome through the narrator and checking whether the narrated result asserts anything the settled outcome doesn't support, independent of the other stories.

**Acceptance Scenarios**:

1. **Given** a scenario where the settled outcome states no adverse event occurred to the player, **When** the narrator generates its output for that scenario, **Then** the result is checked for language asserting an adverse event occurred, and flagged if so.
2. **Given** a body of such scenarios is run repeatedly over time (e.g., after a narrator prompt or model change), **Then** the rate of flagged contradictions can be compared across runs.

### Edge Cases

- What happens when the curated verification scenarios (Story 1/5) become stale because the adventure's content changed (e.g., a zone was renamed or removed)? The verification suite must fail loudly and identifiably as a stale-fixture problem, not be silently skipped or produce a misleading pass.
- How does the system handle a narrated-vs-settled-fact check (Story 5) that is itself judged by an AI and disagrees with a human reviewer? Such checks are advisory signal for trend-tracking, not an automatic gate that blocks a change by itself.
- What happens to a campaign's audit record (Story 2) when the campaign or account it belongs to is deleted (e.g., a GDPR erasure request)? The audit record must not outlive the data-deletion guarantees already made elsewhere in the system.
- What happens when the redaction in Story 3 hides information that would have been genuinely useful for diagnosing a specific reported problem? An operator must have a deliberate, auditable way to opt into fuller detail for a specific investigation, rather than redaction being silently absolute with no recourse.
- What happens if the volume of audit records (Story 2) or telemetry data (Story 4) grows very large over a long-lived campaign or many campaigns? Older records may be summarized or aged out, but the most recent activity for an active campaign must always be reconstructable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a repeatable, on-demand way to verify the intent classifier's behavior against a curated set of known player scenarios, reporting a clear pass/fail (or equivalent score) per scenario.
- **FR-002**: The verification in FR-001 MUST be runnable before a classifier prompt or model change is accepted into the shared codebase, not only as an after-the-fact discovery when a live problem surfaces.
- **FR-003**: The verification in FR-001 MUST check not only which action the classifier chose, but also whether any supporting details that action required (e.g., a destination, a target) were correctly supplied.
- **FR-004**: System MUST persist a durable, per-campaign record of every mechanically significant determination made during play (which action was dispatched, which probabilistic outcome was determined and for which encounter, and whether a required supporting detail came from the AI itself or a deterministic fallback), independent of and outliving the lifetime of the process that made the determination.
- **FR-005**: The record in FR-004 MUST be reconstructable for a given campaign after the fact, without needing to re-run that campaign or inspect a specific process's transient console output.
- **FR-006**: System MUST NOT include player-authored narrative text or the full instructions given to the narrator in operational telemetry data collected from real production play by default.
- **FR-007**: System MUST provide a deliberate, auditable way for an operator to capture fuller telemetry detail (including content otherwise redacted per FR-006) for a specific investigation, distinct from the default production behavior.
- **FR-008**: System MUST retain operational monitoring data (traces, logs, metrics) in a form queryable after the serving process that generated it has stopped running, for at least long enough to investigate a reported problem after the fact.
- **FR-009**: System MUST provide a way to check, for a given turn with a known settled mechanical outcome, whether the narrator's output asserts an event contradicting that outcome, and to run this check repeatably across a curated set of such scenarios.
- **FR-010**: None of the verification or audit mechanisms introduced by this feature MUST alter, delay, or add a dependency to a real player's live turn — they operate against curated scenarios and after-the-fact records, not live production traffic scoring.
- **FR-011**: The audit record in FR-004 MUST be deleted or rendered irrecoverable when the campaign or account it belongs to is deleted, consistent with existing data-erasure guarantees elsewhere in the system.

### Key Entities

- **Regression Case**: A single named, versioned scenario used to verify the classifier — a player situation and action, paired with the mechanical decision (and any required supporting details) it is expected to produce.
- **Regression Dataset**: A curated, versioned collection of Regression Cases, plus the overall pass/fail result of running them against a given classifier configuration.
- **Audit Record**: A durable, per-campaign entry describing one mechanically significant determination (what was determined, for what situation, and whether a required detail came from the AI or a fallback), independent of the serving process's lifetime.
- **Telemetry Record**: Operational monitoring data (a trace, log, or metric) for a turn, retained in queryable form after the fact, and — by default — excluding player-authored content and full narrator instructions.
- **Narrative Fidelity Finding**: The result of checking one scenario's narrated output against its settled mechanical outcome — whether the narration asserted something the outcome doesn't support.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer changing the classifier's instructions or the model it uses can determine, without a live play session, whether every previously-passing scenario in the regression dataset still passes.
- **SC-002**: For 100% of campaigns played after this feature ships, every mechanically significant determination in that campaign can be reconstructed after the fact by someone other than the player, without access to the original serving process.
- **SC-003**: 0% of telemetry records generated from real production play contain player-authored narrative text or the full narrator system instructions.
- **SC-004**: An operator investigating a turn that occurred before the serving process most recently restarted can retrieve that turn's monitoring data 100% of the time.
- **SC-005**: The rate of narrative-fidelity contradictions (Story 5) across the curated scenario set can be measured and compared between any two narrator configurations (e.g., before/after a prompt or model change).
- **SC-006**: A regression case that would have caught the classifier bug described in this feature's motivating incident exists in the regression dataset from the first release of this feature onward.

## Assumptions

- The existing deterministic dispatch layer (mechanical action execution, dice/probability resolution) is assumed correct and remains the source of truth for "what actually happened" — this feature governs the AI-facing decision points around it (classification, narration), not the deterministic core itself.
- This feature is explicitly offline/batch and after-the-fact by design (per prior architecture decisions already made for this system) — it does not include real-time scoring of live production traffic, and User Story 1/5's verification suites run against curated scenarios, not real player sessions.
- The existing operational-monitoring instrumentation already present in the system is assumed to remain the underlying mechanism; this feature completes and redirects it (durability, redaction) rather than replacing it.
- A persistence gap where a campaign's account association can be lost on a server restart is a separate, already-tracked concern about game-state durability, not about auditing or evaluating AI decisions, and is out of scope for this feature.
- The curated regression dataset (Story 1) and narrative-fidelity scenario set (Story 5) require ongoing maintenance as the adventure's content and the classifier/narrator prompts evolve; that maintenance is an accepted ongoing cost of this capability, not a one-time setup.
- Audit records (Story 2) follow the same retention/deletion lifecycle as the campaign data they describe, including existing data-erasure guarantees (e.g., account/campaign deletion).
