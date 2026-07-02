/**
 * Navigation helpers used outside the React Router tree (hooks that must
 * force a full reload, e.g. on auth failure). Kept in a module so unit tests
 * can mock the redirect instead of fighting jsdom's non-navigating location.
 */

/** Hard-redirect to the auth page (drops all in-memory state). */
export function redirectToAuth(): void {
  window.location.href = '/auth'
}
