# Feature Specification: Real OIDC Login Flow (Frontend)

**Feature Branch**: `008-oidc-frontend-login`

**Created**: 2026-07-04

**Status**: Draft

**Input**: User description: "Real OAuth2/OIDC authentication integration in the frontend
(SPA), replacing the current paste-a-token dev stub with a real browser-driven login flow
against the OIDC provider (Dex locally; any OIDC-compliant provider in production). The
backend already validates real OIDC JWTs fail-closed (ADR-022), proven live against a
real Dex instance in a docker-compose stack. What's missing is entirely on the
frontend/callback side: a real 'Login' redirect to the identity provider, the player
authenticating on the provider's own page, and a secure exchange of the returned
authorization code for a token (without exposing the client secret to browser JS). Goal:
a fully functional login system in the UI, talking to the real backend/database, enabling
genuine end-to-end tests that simulate the real user experience — no scripts or manual
token-pasting required."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Sign in with real credentials through the browser (Priority: P1)

A player opens the app for the first time, clicks "Login", is taken to the identity
provider's own real sign-in page, enters real credentials there, and is returned to the
app already signed in — with no token ever typed or pasted, and no external tool or
script involved anywhere in the flow.

**Why this priority**: This is the entire point of the feature. Without it, there is no
way to exercise the real backend authentication path (already proven to work, ADR-022)
from an actual browser session — the current paste-a-token field cannot represent what a
real player experiences, and every end-to-end validation of "does auth actually work" is
stuck depending on a hand-run script.

**Independent Test**: Using only a browser (no scripts, no API client), open the sign-in
page, click "Login", complete sign-in on the identity provider's page, land back in the
app already authenticated, and confirm the first subsequent action in the app (e.g.
viewing the dashboard) succeeds.

**Acceptance Scenarios**:

1. **Given** a signed-out visitor on the sign-in page, **When** they click "Login",
   **Then** their browser is taken to the identity provider's own authorization page.
2. **Given** the player enters valid credentials on the identity provider's page,
   **When** they submit, **Then** the browser returns to the app already signed in, with
   no token-entry step visible anywhere in the app itself.
3. **Given** the player enters invalid credentials on the identity provider's page,
   **When** they submit, **Then** the identity provider shows its own error and the
   player can retry without restarting or reloading the app from scratch.
4. **Given** the return trip to the app completes, **When** the app makes its first
   authenticated request, **Then** it succeeds using credentials obtained entirely
   through the redirect flow — never typed or pasted by the player into this app.

---

### User Story 2 - Session persists without repeating the manual flow (Priority: P2)

A player who is already signed in reloads the page, closes and reopens the tab, or
returns later within their valid session, and remains signed in — or, if their session
has expired, is cleanly sent back through the same real login flow rather than shown a
broken state or asked to paste anything.

**Why this priority**: A login flow that only works once per browser session isn't
usable for actually playing (or testing) the app; this is what makes Story 1 usable for
more than a single request.

**Independent Test**: Complete Story 1, reload the tab, and confirm continued access
without repeating any manual step; separately, invalidate the session and confirm the
next protected action returns the player to the real login flow.

**Acceptance Scenarios**:

1. **Given** a signed-in player with a still-valid session, **When** they reload the
   page, **Then** they remain signed in without repeating the login flow.
2. **Given** a signed-in player whose session has expired, **When** they take an action
   that requires authentication, **Then** they are cleanly returned to the real login
   flow from Story 1, not an error page or a dead end.

---

### User Story 3 - No long-lived secret ever reaches the browser (Priority: P3)

An operator or reviewer can inspect everything the browser sends, receives, and ships
(network traffic and the built application code) during a complete login flow and find
no long-lived shared secret at any point.

**Why this priority**: Not something a player perceives directly, but part of what "done"
means for this feature — the credential exchange must not leak a secret that would let
anyone impersonate the application.

**Independent Test**: Capture a full login flow with browser developer tools (network
tab) and inspect the shipped JS bundle; confirm no long-lived shared secret value appears
in either.

**Acceptance Scenarios**:

1. **Given** a completed login flow captured via browser developer tools, **When** the
   network trace and the shipped application code are inspected, **Then** no long-lived
   shared secret appears in either.

---

### Edge Cases

- What happens when the player closes the browser or cancels while on the identity
  provider's page, never completing sign-in? → They return to (or remain on) the sign-in
  page as if never signed in; no partial or broken app state.
- What happens when the identity provider redirects back with an error (e.g. access
  denied, invalid request)? → The sign-in page shows a clear, safe error and offers to
  retry the login flow.
- What happens if the same return trip is replayed (e.g. browser back button, then
  forward again, or a bookmarked callback URL)? → The second attempt fails cleanly and
  the player is returned to the sign-in page to start over; it must not silently sign
  them in twice or reuse a spent credential.
- What happens if the identity provider is unreachable during the redirect step? → A
  clear, safe error is shown; the system does not silently fall back to a less-secure
  method of signing in.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The sign-in page MUST offer a "Login" action that begins a real
  identity-provider sign-in flow; this MUST be the primary path to a real (non-mock)
  signed-in session.
- **FR-002**: The system MUST NOT expose any long-lived shared secret in
  browser-executable code or in browser-visible network traffic at any point in the
  login flow.
- **FR-003**: After completing sign-in on the identity provider, the player MUST be
  returned to the app in a signed-in state without any manual token entry.
- **FR-004**: A signed-in player's session MUST survive a page reload without repeating
  the login flow, for as long as the underlying session/token remains valid.
- **FR-005**: When the session has expired or is otherwise invalid, the system MUST
  route the player back into the real login flow rather than into an unhandled error
  state.
- **FR-006**: If the identity provider returns an error or the player cancels mid-flow,
  the system MUST present a clear, safe error state and allow retrying the login flow.
- **FR-007**: This feature MUST NOT weaken the existing backend's fail-closed OIDC token
  validation (ADR-022) — it changes how a token is obtained by the browser, not how the
  backend validates it.
- **FR-008**: A return trip from the identity provider MUST NOT be usable more than once
  (no replay of a spent authorization).
- **FR-009**: The existing local-development token-entry affordance MAY remain available
  for development/test convenience but MUST NOT be reachable in a production build or
  deployment.

### Key Entities *(include if feature involves data)*

- **Player Session (browser-side)**: Whether the current browser tab/app instance is
  authenticated, and whatever is needed to make authenticated calls on the player's
  behalf. Created after a successful round trip to the identity provider; cleared on
  sign-out or on expiry (Story 2).
- **Authorization Handoff**: The transient, one-time-use link between the outgoing
  redirect to the identity provider and the matching incoming return trip. Must not be
  guessable or reusable once consumed (FR-008, edge case: replayed return trip).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new player can go from "not signed in" to "signed in and able to play"
  using only a browser, with zero manual token entry and zero external tooling.
- **SC-002**: 100% of sign-in attempts that fail due to invalid credentials are handled
  entirely on the identity provider's own page, with zero unhandled errors surfacing
  inside the app.
- **SC-003**: A review of the login flow's network traffic and shipped application code
  finds zero long-lived secrets exposed to the browser.
- **SC-004**: A signed-in player who reloads the page remains signed in without
  re-authenticating, for the full lifetime of their valid session.
- **SC-005**: A complete sign-in-through-gameplay path can be exercised by browser
  automation with no reliance on scripts, backdoors, or manually-obtained tokens to
  represent a real player.

## Assumptions

- Dex remains the local development identity provider; production deployments point at
  any OIDC-compliant provider via configuration, consistent with ADR-022 — this feature
  must not hardcode Dex-specific behavior into the app itself.
- Account registration (creating new identity-provider credentials) continues to be the
  identity provider's own responsibility; this app does not build its own
  credential-registration UI as part of this feature.
- The existing offline mock-signed-in mode (used for isolated frontend development and
  testing without any backend) is unaffected by this feature — it is a separate, fully
  offline path and is not "real" sign-in by definition.
- The existing local-development token-entry affordance is retained behind the same kind
  of production guard already established elsewhere in this project (dev-only paths are
  disabled in production builds/deployments), rather than deleted outright.
