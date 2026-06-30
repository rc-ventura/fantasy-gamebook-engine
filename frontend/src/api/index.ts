/**
 * API module — re-exports the typed client.
 *
 * All HTTP calls to the backend go through these functions.
 * The mock mode is controlled by VITE_USE_MOCK=true in .env.local.
 */

export {
  // Auth seam
  setTokenProvider,
  setAuthToken,
  clearAuthToken,
  isAuthenticated,
  // Account
  getAccount,
  // Campaigns
  listCampaigns,
  createCampaign,
  getCampaign,
  deleteCampaign,
  // Session lease
  acquireSession,
  takeoverSession,
  releaseSession,
  // Character
  createCharacter,
  getCharacter,
  // Play loop
  takeTurn,
  getCurrentScene,
  // Save
  saveCampaign,
} from './client'
