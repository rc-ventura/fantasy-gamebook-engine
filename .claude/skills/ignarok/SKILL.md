---
name: ignarok
description: Adventure module (lore pack) for the gamebook engine — the "Ignarok" debut adventure. The Game Master loads this to improvise every scene: opening hook, the progressive zones of the Grey Mountain, the bestiary (enemies plug directly into start_combat), the victory condition, and special rules (traps, bribes, healing). Use this whenever running or narrating an Ignarok session. Original content; not the engine and not the rules — pure static lore.
---

# Ignarok — Adventure Module

> **What this is.** A *static lore pack* (the `AdventureModule` contract). The Game Master
> reads it and **improvises** scenes inside its boundaries. It contains **no game rules and
> no numbers-in-prose** — all randomness, combat math, and state changes go through the MCP
> tools. Swapping the adventure = swapping this file; the engine never changes.
>
> **Original work.** Inspired by classic Fighting-Fantasy dungeon crawls in *style only*.
> No names, text, maps, or puzzles are taken from any copyrighted book.

## metadata

- **name:** Ignarok — The Ashes of the Grey Mountain
- **description:** A lone sellsword climbs the cursed Grey Mountain to end the archmage
  Malachar before his ritual drains the valley below. Six descending-into-the-deep zones,
  one archmage, one way out.
- **tone:** Grim, terse high fantasy. Second person, present-tense dread. The mountain is
  old, hostile, and indifferent; victories are bought with stamina and luck. Show cold,
  weight, echo, and rot. Never jokey, never purple.

## opening (the hook)

Use this verbatim-in-spirit as the first scene after a character exists. Narrate it in
2–4 paragraphs, end with numbered choices.

> For three nights the valley has not slept. A green light pulses behind the clouds that
> crown the **Grey Mountain**, and with every pulse a field withers, a well turns brackish,
> a child wakes screaming. The elders name the cause without wanting to: **Malachar**, the
> archmage who climbed into the mountain a generation ago and was never seen again — now
> awake, now *working* at something.
>
> They could not pay an army. They paid **you**. A purse of gold, a name, and a single
> condition: climb, find Malachar, and stop him — before the ritual finishes and the light
> stops pulsing for good. The trailhead is a wound in the mountain's flank, choked with
> fallen rock. Behind you, the valley. Ahead, the dark.

Opening choices should always include: examine the trailhead, check your gear (`/hero`),
and begin the climb. The clock is implicit — the ritual *will* complete if the player
dawdles forever, but never punish exploration mechanically; use it as narrative pressure.

## zones (progressive — difficulty 1 → 6)

The player moves roughly in order, but the world is yours to improvise within each zone.
On entering a new zone, **register it**: set `current_location` and append to
`visited_locations` via `update_world`, and usually `register_event` the
transition. `difficulty` is a tuning hint for which bestiary entries belong here — it is
**not** a number to read aloud.

### 1 — The Shattered Trailhead  · difficulty 1
- **description:** A collapsed switchback path into the mountain's flank; broken scaffolding
  from old miners, a rusted winch, claw-marks too high to be comfortable.
- **atmosphere:** Wind, scree shifting underfoot, the green light flickering far above.
- **content seeds:** a loose-rock **trap** (rockfall — luck test, see special rules); a
  **Scree Scavenger** lurking in the timbers; an old miner's cache (a little gold or a
  torch). Gentle on-ramp: teach the player that choices route through dice/luck, not prose.

### 2 — The Drowned Mines  · difficulty 2
- **description:** Flooded gallery tunnels, ore carts half-sunk, water black and waist-deep.
- **atmosphere:** Drip-echo, cold that bites, the smell of old iron and rot.
- **content seeds:** a **Toll-Lurker** that blocks the only dry crossing and will take a
  **bribe** (gold) to let the player pass — or a fight if they refuse (`flee_allowed: true`);
  a submerged side-cache reachable with a luck test.

### 3 — The Sunless Caverns  · difficulty 3
- **description:** A natural cathedral of stone where pale fungus gives the only light;
  vast, branching, easy to get turned around.
- **atmosphere:** Bioluminescent green-white glow, spores drifting, distant clicking.
- **content seeds:** edible **provisions** (glow-cap fungus — heal stamina, see special
  rules) but some are foul (luck test to pick safely); a **Stone-Jawed Hound** pack
  ambush; a carved arrow left by an earlier, failed climber pointing deeper.

### 4 — The Thrall Halls  · difficulty 4
- **description:** Worked corridors now — Malachar's domain begins. Hollow servants and
  enslaved minds shuffle through dormitory-halls under the green pulse.
- **atmosphere:** Unnatural order, lamplight, the wrongness of people who do not blink.
- **content seeds:** a **Mind-Thrall** that can be **freed** (a choice/bribe path) rather
  than killed — sparing it can earn information or a later ally beat; a patrolling
  **Hollow Sentinel** guarding a stair; a chance to learn Malachar's weakness via a freed
  thrall (`register_event` the clue, set a World flag like `knows_weakness` via `update_world`).

### 5 — The Arcane Vaults  · difficulty 5
- **description:** Malachar's storehouses and warded laboratories; floors that aren't safe,
  doors that bite, shelves of confiscated relics.
- **atmosphere:** Sigils that hum, air that tastes of copper, the green light now bright.
- **content seeds:** trap-dense — **glyph traps** and a **warded door** (luck tests, and a
  key item — a *rusted key* dropped by a Hollow Sentinel, or a *vault sigil* taken here —
  to open the way to the Sanctum); a **Vault Golem** guarding the final stair; a relic the
  player may take into the boss fight (give it a narrative edge, not a secret number).

### 6 — Malachar's Sanctum  · difficulty 6  · (climax)
- **description:** The ritual chamber at the mountain's heart: a ring of standing focus-
  stones, the green light pouring up through a shaft, and **Malachar** at its center.
- **atmosphere:** Overwhelming power, the floor thrumming, the valley's stolen life visible
  as motes streaming upward.
- **content seeds:** the **boss fight** against Malachar (see bestiary). On his defeat, the
  Game Master **sets the World flag `malachar_defeated` = true** via
  `update_world({"flags": {"malachar_defeated": true}})` and `register_event`s it.
  Then the ritual destabilizes — a **collapse-escape** denouement (a luck test or two to
  flee as the chamber comes down) before the epilogue. If the player learned the weakness in
  zone 4 (`knows_weakness`), grant a narrative advantage in the fight (e.g. one free
  description of an opening), never a silent stat change.

## bestiary

Each entry's **name / skill / stamina** plug **directly** into `start_combat` as an
`Enemy{name, skill, stamina}`. `behavior` and `drops` are narration/loot guidance only.
Hero `skill` rolls 7–12, so these are tuned to rise with the zones.

| name | skill | stamina | behavior | drops |
|---|---|---|---|---|
| Scree Scavenger | 5 | 5 | Cowardly scrap-eater; ambushes from rubble, flees when hurt. `flee_allowed: true`. | a few gold |
| Toll-Lurker | 6 | 6 | Territorial crossing-guard; **bribable** with gold to pass without a fight. `flee_allowed: true`. | gold, a waterlogged trinket |
| Stone-Jawed Hound | 7 | 6 | Pack ambusher in the caverns; aggressive, no bribe, hard to outrun. | — |
| Hollow Sentinel | 8 | 9 | Animated armor; relentless, never flees, no bribe. `flee_allowed: false`. | rusted key |
| Mind-Thrall | 7 | 7 | Enslaved person; **can be freed** (choice/bribe) instead of killed — sparing yields a clue/ally. | (if freed) Malachar's weakness |
| Vault Golem | 9 | 11 | Stone guardian of the final stair; slow, immense, immovable. `flee_allowed: false`. | vault sigil |
| Malachar the Archmage | 11 | 14 | **Boss.** Casts the ritual's stolen power; defeating him sets the victory flag. `flee_allowed: false`. | the ritual is broken (no item drop) |

Notes:
- To start any fight, the Game Master delegates to the **combat-sub-agent** SKILL, passing
  the hero (skill/stamina/luck current values), the enemy list from this table, and
  `flee_allowed`. It runs the fight via MCP and returns a `FinalResult`.
- **Drops** are applied by the Game Master after a win via `update_character_sheet`
  (e.g. add to `inventory`, or `gold`) and may be surfaced in the combat-sub-agent's
  `FinalResult.drops`. Apply them as narration + a real state change, never a narrated-only
  item.
- Encounters can stack enemies (e.g. two Scree Scavengers, or a Hound pack) by passing
  multiple `Enemy` entries to `start_combat`.

## victory_condition

- **description:** Defeat Malachar in the Sanctum and break the ritual, then escape the
  collapsing mountain alive.
- **flag:** `malachar_defeated` — a boolean set `true` in the **World** (`flags`) via
  `update_world` the moment Malachar's combat ends in the hero's favor. This flag, verifiable in the World, is the
  single source of truth for victory. On victory: narrate the epilogue, then the Game Master
  archives the character to the **hall_of_fame** (`archive_character` with
  destination `"hall_of_fame"`).

## special_rules

All of these resolve through MCP tools — **never** narrate a number or a roll outcome the
engine didn't produce.

- **Traps (rockfall, glyphs, warded doors):** resolve with `test_luck`. Success = the player
  avoids/disarms it; failure = consequence, typically stamina loss applied via
  `update_character_sheet` (`{"stamina": {"current": <new>}}`). `test_luck` already spends
  1 luck — never decrement luck separately.
- **Bribes (Toll-Lurker, freeing a Mind-Thrall):** the player spends `gold`. Check the real
  value first (`read_character_sheet`); if affordable, deduct via
  `update_character_sheet` (`{"gold": <new total>}`) and skip/alter the fight. If they can't
  afford it, the option fails honestly — combat or another route.
- **Provisions / healing:** eating provisions restores `stamina.current`. Decrement
  `provisions` and raise `stamina.current` via `update_character_sheet` — **cap at
  `stamina.initial`**, never over-heal (the engine rejects `current > initial` and leaves
  state unchanged, so the Game Master must compute the cap). Read the sheet first to know
  `initial` and the current values.
- **Key items (rusted key / vault sigil):** gate access to the Sanctum. Track them as real
  `inventory` entries (`update_character_sheet`) and as a World flag (`update_world`) / event
  if they unlock a location, so progress survives a reload.
- **Knowing the weakness:** if the player frees a Mind-Thrall and learns Malachar's weakness,
  `register_event` it and optionally set a World flag (`knows_weakness`) via `update_world`. In the boss fight,
  grant a *narrative* advantage only — the combat math stays the engine's.
- **Death:** if the hero falls in any fight (`alive: false`), it's game over — the Game
  Master archives to the **graveyard** (`archive_character` destination `"graveyard"`). See
  the game-master SKILL for the exact end-state flow.
