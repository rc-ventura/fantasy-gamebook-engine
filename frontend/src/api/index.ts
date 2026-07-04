/**
 * API module — re-exports the typed client.
 *
 * All HTTP calls to the backend go through these functions.
 * The mock mode is controlled by VITE_USE_MOCK=true in .env.local.
 *
 * Routes are /me/game/... (D1 backend-scoped, spec 006 ADR-017).
 */

export {
  // Auth seam
  setTokenProvider,
  setAuthToken,
  clearAuthToken,
  isAuthenticated,
  // Account
  getAccount,
  // Game (one active game per account)
  createGame,
  getGame,
  deleteGame,
  // Character
  createCharacter,
  getCharacter,
  // Play loop
  takeTurn,
  getCurrentScene,
  // Save
  saveGame,
  // Graveyard
  getGraveyard,
  // Session lease (stub — real impl in slice 004)
  acquireSession,
  takeoverSession,
  releaseSession,
} from './client'
