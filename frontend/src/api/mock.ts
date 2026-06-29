/**
 * Mock API handlers — deterministic fixture data matching the frozen OpenAPI contract.
 *
 * Activated when VITE_USE_MOCK=true (set in .env.local).
 * Allows the full play loop to be exercised without a running backend.
 *
 * State advances through: opening → exploring → in_combat → ended
 * State is stored in sessionStorage so it persists across component re-renders.
 *
 * The mock honours the core invariant: every number comes from a "mock engine" —
 * no value is fabricated at render time, all values are pre-computed here and
 * returned as API responses exactly as the real backend would.
 */

import type {
  Account,
  CampaignState,
  CampaignSummary,
  CharacterSheet,
  CombatRoundResponse,
  CombatState,
  Scene,
  SessionLease,
  TurnResponse,
  WorldState,
} from '../types'

// ── Mock state machine ────────────────────────────────────────────────────────

type MockStage = 'no_character' | 'opening' | 'exploring' | 'in_combat' | 'ended'

const MOCK_CAMPAIGN_ID = 'mock-campaign-001'

function getMockStage(): MockStage {
  const stored = sessionStorage.getItem('mock_stage')
  if (
    stored === 'no_character' ||
    stored === 'opening' ||
    stored === 'exploring' ||
    stored === 'in_combat' ||
    stored === 'ended'
  ) {
    return stored
  }
  return 'no_character'
}

function setMockStage(stage: MockStage): void {
  sessionStorage.setItem('mock_stage', stage)
}

// ── Mock data fixtures ────────────────────────────────────────────────────────

const MOCK_ACCOUNT: Account = {
  id: 'mock-account-001',
  email: 'adventurer@grimoire.local',
}

/** Character sheet with engine-realistic attribute values. */
function makeMockCharacter(alive = true): CharacterSheet {
  return {
    name: 'Aldric the Bold',
    skill: { initial: 10, current: 10 },
    stamina: { initial: 20, current: 20 },
    luck: { initial: 9, current: 9 },
    gold: 15,
    provisions: 10,
    inventory: [
      { id: 'sword', name: 'Sword', quantity: 1 },
      { id: 'lantern', name: 'Lantern', quantity: 1 },
      { id: 'rope', name: 'Hemp Rope', quantity: 1 },
    ],
    conditions: [],
    alive,
  }
}

const MOCK_WORLD_OPENING: WorldState = {
  location: 'village_of_stonebrook',
  visited: ['village_of_stonebrook'],
  flags: {},
}

const MOCK_WORLD_EXPLORING: WorldState = {
  location: 'grey_mountain_foothills',
  visited: ['village_of_stonebrook', 'grey_mountain_foothills'],
  flags: { quest_accepted: true },
}

const MOCK_WORLD_COMBAT: WorldState = {
  location: 'grey_mountain_pass',
  visited: ['village_of_stonebrook', 'grey_mountain_foothills', 'grey_mountain_pass'],
  flags: { quest_accepted: true },
}

const OPENING_SCENE: Scene = {
  narrative: `The ancient village of Stonebrook lies shrouded in morning mist as you stride toward the Grey Mountain. Your sword hangs reassuringly at your hip, a gift from your mentor who vanished into those dark peaks three seasons ago.

Old Marta, the village elder, intercepts you at the gate. Her weathered hands grasp your arm with surprising strength. "You seek the sorcerer Malachar," she whispers. "Tread carefully, adventurer. The mountain has teeth."

The road forks ahead: the left path winds through the Whispering Wood, faster but haunted by fell creatures; the right climbs the exposed ridgeline, slower but safer. A ragged traveller rests by the roadside, nursing a wound — perhaps he carries news of the path ahead.`,
  choices: [
    { id: '1', label: 'Take the left path through the Whispering Wood' },
    { id: '2', label: 'Take the right path along the exposed ridgeline' },
    { id: '3', label: 'Speak to the wounded traveller' },
  ],
  effects: [],
}

const EXPLORING_SCENE: Scene = {
  narrative: `The wounded traveller, a merchant named Corvin, warns you of a pack of Dire Wolves that patrol the Whispering Wood. "I barely escaped with my life," he says, bandaging a savage gash on his forearm. "But I did spy something interesting — a cave entrance hidden behind the great oak at the crossroads. Rumour has it the hermit Elara shelters there; she knows secret paths through the mountain."

He offers you a flask of healing draught in exchange for a coin, and points you toward the ridgeline path as the safer choice.

The morning is advancing. You must choose your route before midday, when the mountain mists thicken.`,
  choices: [
    { id: '1', label: 'Pay Corvin 2 gold for the healing draught and head for the cave' },
    { id: '2', label: 'Thank him and take the ridgeline path' },
    { id: '3', label: 'Head into the Whispering Wood regardless of his warning' },
  ],
  effects: [
    { type: 'register_event', params: { payload: 'Met wounded merchant Corvin at the crossroads' } },
  ],
}

const COMBAT_SCENE: Scene = {
  narrative: `You choose the ridgeline path. The wind tears at your cloak as you climb, loose shale skittering down the slope with each step. Then you hear it — a low, guttural growl from behind a cluster of boulders.

A Dire Wolf, larger than any hound you have seen, steps into the path. Its eyes glow with unnatural intelligence, its grey fur bristling. It guards something — a cairn of stones that marks, you realise, the hidden entrance to a mountain tunnel.

There is no room to run on this narrow ledge. You must fight.`,
  choices: [],
  effects: [
    {
      type: 'start_combat',
      params: {
        enemies: [{ name: 'Dire Wolf', skill: 8, stamina: 10 }],
        flee_allowed: false,
      },
    },
  ],
}

const VICTORY_SCENE: Scene = {
  narrative: `The Dire Wolf falls with a final, shuddering breath. You stand over the fallen beast, your sword arm trembling from the exertion. Beyond the cairn, just as you suspected, lies the entrance to the tunnel — a dark throat in the mountain that leads deeper toward Malachar's lair.

You take a moment to tend your wounds and catch your breath. The battle is won, but the mountain has many more dangers ahead. Your quest continues.`,
  choices: [
    { id: '1', label: 'Enter the tunnel and press forward' },
    { id: '2', label: 'Rest here and tend your wounds before continuing' },
  ],
  effects: [
    { type: 'end_combat', params: {} },
    { type: 'register_event', params: { payload: 'Defeated the Dire Wolf guarding the mountain tunnel entrance' } },
  ],
}

const ENDED_SCENE: Scene = {
  narrative: `Your wounds proved too grievous. The mountain claims another soul, as it has claimed so many before you. The quest for Malachar ends here, on this cold ridge, your blood staining the grey shale.

Perhaps another adventurer will take up the quest. Perhaps the sorcerer will never be stopped. The world is a crueller place tonight.

*— Your adventure ends here —*`,
  choices: [],
  effects: [],
}

const MOCK_COMBAT: CombatState = {
  participants: [
    { name: 'Aldric the Bold', skill: 10, stamina: 20 },
    { name: 'Dire Wolf', skill: 8, stamina: 10 },
  ],
  rounds: [],
  flee_allowed: false,
  active: true,
}

// ── Campaign state builders ───────────────────────────────────────────────────

function buildCampaignState(stage: MockStage): CampaignState {
  switch (stage) {
    case 'no_character':
      return {
        id: MOCK_CAMPAIGN_ID,
        status: 'active',
        world: MOCK_WORLD_OPENING,
      }

    case 'opening':
      return {
        id: MOCK_CAMPAIGN_ID,
        status: 'active',
        character: makeMockCharacter(),
        world: MOCK_WORLD_OPENING,
        current_scene: OPENING_SCENE,
        combat: null,
      }

    case 'exploring':
      return {
        id: MOCK_CAMPAIGN_ID,
        status: 'active',
        character: { ...makeMockCharacter(), luck: { initial: 9, current: 8 } },
        world: MOCK_WORLD_EXPLORING,
        current_scene: EXPLORING_SCENE,
        combat: null,
      }

    case 'in_combat': {
      const char: CharacterSheet = {
        ...makeMockCharacter(),
        stamina: { initial: 20, current: 16 },
        luck: { initial: 9, current: 7 },
      }
      return {
        id: MOCK_CAMPAIGN_ID,
        status: 'active',
        character: char,
        world: MOCK_WORLD_COMBAT,
        current_scene: COMBAT_SCENE,
        combat: MOCK_COMBAT,
      }
    }

    case 'ended':
      return {
        id: MOCK_CAMPAIGN_ID,
        status: 'ended',
        character: { ...makeMockCharacter(false), stamina: { initial: 20, current: 0 } },
        world: MOCK_WORLD_COMBAT,
        current_scene: ENDED_SCENE,
        combat: null,
      }
  }
}

// ── Mock handlers (public API) ────────────────────────────────────────────────

/** Simulate network latency for realistic UX testing. */
function delay(ms = 600): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export const mockApi = {
  async getAccount(): Promise<Account> {
    await delay(200)
    return MOCK_ACCOUNT
  },

  async listCampaigns(): Promise<CampaignSummary[]> {
    await delay(300)
    return [
      {
        id: MOCK_CAMPAIGN_ID,
        status: getMockStage() === 'ended' ? 'ended' : 'active',
        created_at: '2026-06-27T10:00:00Z',
        updated_at: new Date().toISOString(),
      },
    ]
  },

  async createCampaign(): Promise<CampaignSummary> {
    await delay(400)
    setMockStage('no_character')
    return {
      id: MOCK_CAMPAIGN_ID,
      status: 'active',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
  },

  async getCampaign(_id: string): Promise<CampaignState> {
    await delay(400)
    const stage = getMockStage()
    return buildCampaignState(stage)
  },

  async createCharacter(_id: string, name?: string): Promise<CharacterSheet> {
    await delay(600)
    setMockStage('opening')
    // Simulate engine dice rolls: SKILL 1d6+6, STAMINA 2d6+12, LUCK 1d6+6
    const d6 = () => Math.floor(Math.random() * 6) + 1
    const skill = d6() + 6
    const stamina = d6() + d6() + 12
    const luck = d6() + 6
    const char = makeMockCharacter()
    return {
      ...char,
      name: name?.trim() || char.name,
      skill: { initial: skill, current: skill },
      stamina: { initial: stamina, current: stamina },
      luck: { initial: luck, current: luck },
    }
  },

  async getScene(_id: string): Promise<Scene> {
    await delay(300)
    const stage = getMockStage()
    const campaign = buildCampaignState(stage)
    return campaign.current_scene ?? OPENING_SCENE
  },

  async takeTurn(_id: string, choiceId: string | undefined, _freeText: string | undefined): Promise<TurnResponse> {
    await delay(800)
    const stage = getMockStage()

    let nextStage: MockStage = stage
    let scene: Scene

    if (stage === 'opening') {
      if (choiceId === '3') {
        nextStage = 'exploring'
        scene = EXPLORING_SCENE
      } else if (choiceId === '1') {
        nextStage = 'in_combat'
        scene = COMBAT_SCENE
      } else {
        nextStage = 'exploring'
        scene = EXPLORING_SCENE
      }
    } else if (stage === 'exploring') {
      if (choiceId === '3') {
        nextStage = 'in_combat'
        scene = COMBAT_SCENE
      } else {
        nextStage = 'in_combat'
        scene = COMBAT_SCENE
      }
    } else if (stage === 'in_combat') {
      // After combat, go to victory or ended based on stamina
      nextStage = 'exploring'
      scene = VICTORY_SCENE
    } else {
      scene = ENDED_SCENE
    }

    setMockStage(nextStage)
    const campaign = buildCampaignState(nextStage)
    campaign.current_scene = scene

    return { scene, campaign }
  },

  async combatRound(_id: string, testLuck: boolean): Promise<CombatRoundResponse> {
    await delay(700)
    const round = {
      hero_attack: 15, // engine-produced: skill(10) + 2d6(5)
      enemy_attack: 11, // engine-produced: skill(8) + 2d6(3)
      hero_damage: 2,
      enemy_damage: 0,
      luck_used: testLuck,
      luck_result: testLuck ? ('lucky' as const) : undefined,
    }

    const updatedCombat: CombatState = {
      ...MOCK_COMBAT,
      rounds: [...MOCK_COMBAT.rounds, round],
      participants: [
        { name: 'Aldric the Bold', skill: 10, stamina: 20 },
        { name: 'Dire Wolf', skill: 8, stamina: 8 }, // took 2 damage
      ],
    }

    setMockStage('exploring') // combat resolved
    const campaign = buildCampaignState('exploring')
    campaign.current_scene = VICTORY_SCENE
    campaign.combat = { ...updatedCombat, outcome: 'victory', active: false }

    return { round, combat: updatedCombat, campaign }
  },

  async fleeCombat(_id: string): Promise<{ campaign: CampaignState }> {
    await delay(500)
    setMockStage('exploring')
    const campaign = buildCampaignState('exploring')
    return { campaign }
  },

  async acquireSession(_id: string): Promise<SessionLease> {
    await delay(200)
    return {
      session_token: 'mock-session-token-' + Date.now().toString(),
      expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    }
  },

  async takeoverSession(_id: string): Promise<SessionLease> {
    await delay(300)
    return {
      session_token: 'mock-session-token-takeover-' + Date.now().toString(),
      expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
    }
  },

  async releaseSession(_id: string): Promise<void> {
    await delay(100)
  },

  async saveCampaign(_id: string): Promise<void> {
    await delay(300)
  },

  async deleteCampaign(_id: string): Promise<void> {
    await delay(300)
    sessionStorage.removeItem('mock_stage')
  },
}
