# Feature Specification: Deterministic Turn Dispatcher (Pure Narrator)

**Feature Branch**: `009-deterministic-turn-dispatcher`

**Created**: 2026-07-05

**Status**: Draft

**Input**: User description: "cria a proxima spec para implementação do sistema discutido
da ADR 034" — implement the pure-narrator + deterministic-dispatcher architecture
documented in `docs/adrs/ADR-033-engine-side-guard-against-narrator-supplied-attribute-values.md`
(revised 2026-07-05): separate *deciding what happened* (a deterministic layer) from
*narrating it* (the AI), so a hero's stats can never be changed by an invented outcome —
regardless of which AI model powers the narration — while preserving free-text play and
making the same adventure play out differently each time it's started.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A hero's stats can never be corrupted by an invented outcome (Priority: P1)

A player takes an action with an uncertain result (a risky leap, a fight, resting to
recover). Whatever happens to their hero's health, luck, or skill afterward is always
the outcome of something that was actually checked — never a number the story simply
asserts. This holds no matter which AI model is narrating that session.

**Why this priority**: This is the foundational integrity guarantee of the whole
project — "the numbers are never invented" — and it has been shown, with real play
sessions against two very different AI models (a cheap one and the strongest available),
to currently fail. Nothing else in this feature matters if this doesn't hold.

**Independent Test**: Play through actions with uncertain outcomes (a risky attempt, a
fight, resting) across more than one AI model choice, including a weaker/cheaper one,
and confirm every resulting stat change traces back to something that was actually
checked, never to a value that was simply narrated into being.

**Acceptance Scenarios**:

1. **Given** an action with an uncertain outcome, **When** the turn resolves, **Then**
   the recorded result always matches something that was actually checked — never a
   value the story asserted on its own.
2. **Given** a moment where the hero is healed or hurt, **When** the stat changes,
   **Then** the new value is always the result of an actual computation, never an
   arbitrary number woven into the narration.
3. **Given** the AI model powering the narration is switched to a different one
   (including a cheaper/weaker option), **When** the same kinds of situations are
   played through again, **Then** the integrity guarantee holds identically — it does
   not depend on which model is narrating.
4. **Given** a completed turn, **When** its recorded history is reviewed, **Then**
   every stat change and logged outcome tied to an uncertain moment can be traced to an
   actual check that happened, not merely asserted.

---

### User Story 2 - The same adventure never plays out exactly the same way twice (Priority: P2)

A player starts the same adventure a second time. The overall story — its setting, its
final antagonist, what it takes to win — is recognizably the same adventure. But which
dangers they run into along the way, and how everything is told, are not guaranteed to
match the first playthrough.

**Why this priority**: This is what makes an AI-narrated adventure worth playing more
than once, without turning the adventure into either a rigid, always-identical script or
an ungrounded free-for-all.

**Independent Test**: Play the same adventure from the start twice and confirm the
overarching story stays recognizable (same setting, same final antagonist, same
condition for winning) while the specific dangers encountered along the way, and the
narration itself, are free to differ.

**Acceptance Scenarios**:

1. **Given** two separate playthroughs of the same adventure, **When** comparing them,
   **Then** both share the same overall setting, the same key figures, and the same
   condition for winning.
2. **Given** two separate playthroughs of the same adventure, **When** comparing which
   dangers or encounters appeared along the way, **Then** they are not guaranteed to be
   identical between the two playthroughs.
3. **Given** a danger or encounter's presence at a location has already been determined
   earlier in a playthrough, **When** the player returns to that same location later in
   the same playthrough, **Then** its presence or absence is remembered, not decided
   again from scratch.

---

### User Story 3 - A player can act in their own words without being boxed into a menu (Priority: P2)

A player types something in their own words that the adventure's design never
specifically anticipated. The story continues to respond sensibly, rather than erroring
out or forcing the player to pick from a fixed list.

**Why this priority**: Free-form play is the entire appeal of an AI-narrated gamebook
over a traditional fixed-choice one; this must not be lost in exchange for the
integrity guarantee in Story 1.

**Independent Test**: Type an unanticipated free-text action and confirm the story
continues with a sensible response rather than an error or a forced menu choice.

**Acceptance Scenarios**:

1. **Given** a player describes an action in their own words, **When** it carries no
   game-mechanical stakes, **Then** the story continues with a freely narrated response.
2. **Given** a player describes an action that does carry game-mechanical stakes (risk,
   a fight, recovery), **When** it is recognized as such, **Then** the appropriate check
   happens before the outcome is told to the player.
3. **Given** the system cannot confidently tell which of the two cases above applies,
   **When** it must decide how to proceed, **Then** it defaults to the freely narrated
   path rather than guessing at — and applying — a mechanical consequence.

---

### User Story 4 - An adventure's author can trust it plays safely before anyone else does (Priority: P3)

Someone building a new adventure reuses proven, common building blocks for risky
moments, fights, and recovery instead of inventing the rules for each one from scratch,
and gets a clear check of the adventure's structure before it's ever put in front of a
real player.

**Why this priority**: This is what keeps adding new adventures affordable and safe —
it supports the project's stated ability to swap in new adventures without rebuilding
the game's integrity guarantees each time.

**Independent Test**: Define a new adventure's structure reusing existing common
mechanical building blocks, run the automated structural check against it, and get a
clear pass/fail before it is available to players.

**Acceptance Scenarios**:

1. **Given** an adventure's author needs a common kind of mechanical moment (a risky
   attempt, a fight, resting), **When** they build it, **Then** they can reuse an
   existing, already-proven building block instead of designing new rules for it.
2. **Given** a newly authored adventure structure, **When** it is checked before
   release, **Then** structural mistakes (a broken reference, an impossible chance
   value, an unreachable location) are caught automatically.
3. **Given** an adventure's structure has passed its automated check, **When** it is
   intended for real players, **Then** a person still reviews it at least once before
   release — passing the automated check alone is not enough for a first release.

---

### Edge Cases

- What happens when the system can't confidently tell what mechanical action (if any) a
  player's free text corresponds to? It defaults to free narration — it never guesses
  at a mechanical consequence and applies it anyway (Story 3, Scenario 3).
- What happens when a danger that was earlier determined *not* to be present at a
  location is revisited later in the same playthrough? It stays absent for the rest of
  that playthrough; its presence is not re-decided.
- What happens if an adventure's structure hasn't yet received human review? It cannot
  be released for real players to play, even if the automated check passed (FR-011).
- What happens during an extended encounter with many back-and-forth exchanges (e.g. a
  long fight)? Every exchange still resolves under the same integrity guarantee as a
  single check — nothing about a longer encounter allows an invented outcome to slip in
  (FR-012).
- What happens if an adventure's structure references a mechanical building block that
  doesn't exist, or a location that was never defined? It is rejected before release,
  never discovered later by a player running into a broken moment.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST ensure that any change to a hero's core stats (health,
  luck, skill) is always the result of an actual computed check, never a value asserted
  without one.
- **FR-002**: The system MUST ensure this guarantee holds regardless of which AI model
  is powering the narration — switching models MUST NOT weaken it.
- **FR-003**: The system MUST recognize which of the player's stated actions carry
  game-mechanical stakes (risk, a fight, resting, moving) versus which are purely
  narrative, and handle each accordingly.
- **FR-004**: When the system cannot confidently recognize a mechanical action, it MUST
  default to free narration rather than guessing at, and applying, a mechanical
  consequence.
- **FR-005**: The system MUST support an adventure having a fixed identity (its overall
  setting, its principal antagonist, its condition for winning) that stays the same
  across every playthrough of it.
- **FR-006**: The system MUST support some dangers or encounters within an adventure
  being determined per playthrough (present or absent), so the same adventure is not
  mechanically identical every time it is played.
- **FR-007**: Once a per-playthrough danger or encounter's presence has been determined
  for a location, the system MUST remember that determination for the rest of that
  playthrough rather than deciding it again.
- **FR-008**: The system MUST let a player act in free text for moments that carry no
  mechanical stakes, without constraining them to a fixed menu.
- **FR-009**: The system MUST provide a reusable library of common mechanical
  situations (a risky attempt, a skill test, resting/recovery, moving, a fight) that any
  adventure can reuse instead of defining from scratch.
- **FR-010**: The system MUST automatically check a new or changed adventure's
  structure for internal consistency (broken references, impossible chance values,
  unreachable locations) before it is available for play.
- **FR-011**: An adventure's structure MUST receive human review at least once before
  its first release to real players, even after it has passed the automated check.
- **FR-012**: Extended encounters with multiple exchanges (e.g. a fight) MUST resolve
  under the same integrity guarantee as any single check — every exchange's outcome
  comes from an actual computation.
- **FR-013**: The system MUST preserve a player's ability to attempt something the
  adventure's author never anticipated; such an attempt MUST be handled narratively,
  never simply rejected.

### Key Entities *(include if feature involves data)*

- **Adventure Structure**: An adventure's identity — its fixed elements (setting,
  principal antagonist, winning condition), its per-playthrough dangers/encounters
  (each may or may not be present, determined once per playthrough and then
  remembered), and its purely narrative areas (no predefined mechanical content, the
  story is free to invent there).
- **Mechanical Situation Pattern**: A reusable, named kind of game-mechanical moment (a
  risky attempt, a skill test, resting, moving, a fight) with bounded parameters,
  shared across every adventure rather than redefined per adventure.
- **Turn Outcome**: What actually happened as the result of a recognized mechanical
  action in a given turn — handed to the narration step as settled fact, never
  something the narration step invents itself.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across every supported AI model choice, including the cheapest/weakest
  one, 0% of recorded stat changes trace to a value that wasn't the result of an actual
  computed check, across repeated play-testing.
- **SC-002**: Two full playthroughs of the same adventure share the same recognizable
  overall story and winning condition, while differing in at least the dangers
  encountered along the way and in the narration itself.
- **SC-003**: Players attempting an unanticipated free-text action receive a sensible
  narrative continuation, not an error, in effectively all attempts.
- **SC-004**: A new adventure reusing the existing library of mechanical situations can
  be authored and pass its automated consistency check without inventing new mechanical
  rules from scratch.
- **SC-005**: Every mechanical-action turn resolves in a consistent, bounded number of
  narration steps, regardless of how many mechanical checks occur within it (e.g. a
  fight with many exchanges).

## Assumptions

- The engine's existing core mechanical operations (dice rolls, luck tests, combat
  resolution, healing/damage) remain the ultimate source of truth for numbers; this
  feature changes who decides *when* they're invoked, not *how* they're computed.
- The first adventure (Ignarok) is migrated to the new structure incrementally, one
  area at a time, rather than all at once; areas not yet migrated continue to behave as
  free narrative areas in the meantime.
- An AI-assisted first draft of an adventure's structure, produced from its existing
  lore, is an acceptable starting point — provided it still receives human review
  before release (FR-011); the review requirement applies regardless of how the draft
  was produced.
- Adventures/campaigns already in progress under the prior narration approach are out
  of scope for retroactive migration; this feature covers new and ongoing play under
  the new approach going forward.
