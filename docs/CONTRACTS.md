# CONTRACTS.md — Authoritative cross-module contracts (Tech Lead)

> **Status: APPROVED by Tech Lead.** This is the single source of truth for every
> cross-module interface in the Phase-1 MVP. The Portuguese specs in `docs/00..08`
> are the *requirements* source of truth; this file is their **English code contract**.
> If you must deviate from anything here, STOP and message the lead — do not drift silently.
>
> **Cycle-2 amendment (2026-06-21, ADR-010 ratified):** §6 tool count 17 → **18** — added
> `update_world`; added `start_combat` enemy validation; added `FleeResult.hero_alive` and an
> unambiguous flee-death `winner` in §5.

## 0. Global rules (every teammate)

1. **Trailing space in the repo path.** The project dir is
   `"/Users/rafaelventura/CascadeProjects/fantasy-gamebook-engine "` (note the trailing
   space). ALWAYS quote paths in shell. Prefer `uv run ...` from inside the dir.
2. **English only** in code, identifiers, comments, docstrings, and docs. Specs are
   Portuguese — translate using the mapping below.
3. **Golden rule:** every module depends only on *interfaces*, never on concrete
   implementations. `interfaces.py` ≠ `implementation.py`. The ONE exception is the
   **composition root** (`mcp/server.py` `main()`), which is the single place allowed to
   construct concrete impls and inject them.
4. **Do NOT run `uv add`.** Deps are already installed (`pydantic`, `mcp`, `pytest`). If
   you need a new dependency, message the lead.
5. **Determinism:** `rules` is pure; RNG is injected. Tests use a seeded RNG.
6. **Atomic storage:** never corrupt state on a mid-write crash (temp file + `os.replace`).
7. **JSON round-trip:** object → JSON → identical object, for every domain model.
8. **The AI never rolls dice in prose** — all randomness/state goes through MCP tools.
9. Use `/adr` for design decisions and `/learning-lesson` for non-obvious discoveries,
   *as you go*. These skills append an index to root `CLAUDE.md`; the lead reconciles it.

### Identifier mapping (PT spec → EN code)
`Ficha`→`CharacterSheet` · `Mundo`→`World` · `Evento`→`Event` · `Combate`→`Combat` ·
`RegistroArquivo`→`ArchiveRecord` · `Atributo`→`Attribute` · `habilidade`→`skill` ·
`energia`→`stamina` · `sorte`→`luck` · `inventario`→`inventory` · `ouro`→`gold` ·
`provisoes`→`provisions` · `condicoes`→`conditions` · `vivo`→`alive` ·
`local_atual`→`current_location` · `locais_visitados`→`visited_locations` ·
`npcs_conhecidos`→`known_npcs` · `flags`→`flags` · `turno`→`turn` · `tipo`→`type` ·
`dados`→`data` · `inimigos`→`enemies` · `rodada`→`round` · `fuga_permitida`→`flee_allowed` ·
`encerrado`→`ended` · `vencedor`→`winner` · `desfecho`→`outcome` · `causa`→`cause` ·
`inventario_final`→`final_inventory`.
Literals: `"heroi"`→`"hero"`, `"inimigo"`→`"enemy"`, `"empate"`→`"tie"`,
`"morte"`→`"death"`, `"vitoria"`→`"victory"`, `"cemiterio"`→`"graveyard"`,
`"hall_da_fama"`→`"hall_of_fame"`.

---

## 1. Module layering (where each type lives)

- **`domain`** holds only the **persistent entities** (things that get stored):
  `Attribute, CharacterSheet, World, Event, Combat, ArchiveRecord` (+ value objects
  `Npc`, `Enemy`). Schema designed to map ~1:1 to Postgres tables later. No logic except
  validation. Depends on nothing.
- **`rules`** holds the **rules result types** (`DiceResult, GeneratedAttributes,
  LuckTestResult, RoundResult`) and the `RandomSource` protocol, plus pure functions.
  Imports only `domain` types (for `Attribute`).
- **`storage`** holds `StorageBackend` (Protocol) + impls. Imports only `domain`.
- **`combat`** holds combat lifecycle result types (`RoundOutcome, FleeResult,
  FinalResult`) + `CombatEngine` (Protocol) + impl. Imports `rules.interfaces`,
  `storage.interfaces`, `domain` — **never** `storage.json_storage`.
- **`mcp`** is the façade; imports all `*.interfaces` + `domain`. Only `server.main()`
  constructs concretes.

**Audit rule (binding on QA):** the ONLY forbidden cross-module imports are storage
*concrete* impls (`gamebook.storage.json_storage`, `gamebook.storage.in_memory`) inside
`combat` and `mcp` non-root modules. `rules.implementation` (pure functions) MAY be
imported by `combat`/`mcp` — `rules` is the stable core, not a swap boundary, so it has
no interface/impl split to enforce. `combat` references `storage.interfaces.StorageBackend`
under `if TYPE_CHECKING:` (so it has NO runtime dependency on storage at all — even better
than importing the interface). Consequence for runtime isolation checks: `combat`'s
`sys.modules` will NOT contain `storage.interfaces`; assert only that it does NOT contain
`storage.json_storage` / `storage.in_memory` / `gamebook.mcp`. The ast audit still sees the
`TYPE_CHECKING` import and will catch any concrete leak.

---

## 2. `domain/models.py` (pydantic v2 `BaseModel`)

```python
class Attribute(BaseModel):
    initial: int            # >= 0
    current: int            # invariant: 0 <= current <= initial  (validate in dominio)

class CharacterSheet(BaseModel):
    name: str
    skill: Attribute
    stamina: Attribute
    luck: Attribute
    inventory: list[str] = []
    gold: int = 0           # >= 0
    provisions: int = 0     # >= 0
    conditions: list[str] = []
    alive: bool = True

class Npc(BaseModel):
    name: str
    state: str

class World(BaseModel):
    current_location: str = ""
    visited_locations: list[str] = []
    known_npcs: list[Npc] = []
    flags: dict[str, bool] = {}
    turn: int = 0           # >= 0

class Event(BaseModel):
    turn: int
    type: str
    data: dict[str, Any] = {}
    timestamp: str          # ISO-8601 string

class Enemy(BaseModel):     # an enemy *instance* inside a Combat (current stamina mutates)
    name: str
    skill: int
    stamina: int

class Combat(BaseModel):
    combat_id: str
    enemies: list[Enemy]
    round: int = 0
    flee_allowed: bool = True
    ended: bool = False
    winner: Literal["hero", "enemy"] | None = None

class ArchiveRecord(BaseModel):
    name: str
    turns: int
    outcome: Literal["death", "victory"]
    location: str
    cause: str | None = None
    final_inventory: list[str] = []
```

- **Invariant enforcement lives in `dominio`** (e.g. `@field_validator`/`@model_validator`
  on `Attribute`: raise on `current > initial` or `current < 0`). `update_character_sheet`
  relies on these raising.
- **Round-trip:** `Model.model_validate(json.loads(m.model_dump_json())) == m` must hold.

---

## 3. `rules/interfaces.py` + `rules/implementation.py`

```python
# interfaces.py
class RandomSource(Protocol):
    def randint(self, a: int, b: int) -> int: ...   # compatible with random.Random

class DiceResult(BaseModel):      rolls: list[int]; total: int
class GeneratedAttributes(BaseModel):  skill: Attribute; stamina: Attribute; luck: Attribute
class LuckTestResult(BaseModel):  roll: int; success: bool; luck_after: int
class RoundResult(BaseModel):
    hero_as: int; enemy_as: int
    hitter: Literal["hero", "enemy", "tie"]
    base_damage: int              # 2 to the loser, 0 on tie

# implementation.py — pure functions, RNG injected
def roll_dice(notation: str, rng: RandomSource) -> DiceResult
    # parse "NdM", "NdM+K", "NdM-K"; invalid notation -> raise ValueError
def generate_attributes(rng: RandomSource) -> GeneratedAttributes
    # skill = 1d6+6, stamina = 2d6+12, luck = 1d6+6; initial == current
def test_luck(current_luck: int, rng: RandomSource) -> LuckTestResult
    # roll = sum of 2d6 (NOT 1d6 — luck is 7..12, 1d6 would always succeed);
    # success = roll <= current_luck; luck_after = current_luck - 1 (ALWAYS -1)
def resolve_round(hero_skill: int, enemy_skill: int, rng: RandomSource) -> RoundResult
    # attack strength (AS) = skill + 2d6; higher AS hits, base_damage=2; tie -> 0
def apply_luck_modifier(hitter: Literal["hero","enemy"], base_damage: int,
                        luck_success: bool) -> int
    # hero hit (won) + lucky -> 4 ; won + unlucky -> 1
    # enemy hit (lost) + lucky -> 1 ; lost + unlucky -> 3
```
Attribute ranges (tests): skill 7–12, stamina 14–24, luck 7–12.

---

## 4. `storage/interfaces.py` — `StorageBackend` (Protocol)

```python
class StorageBackend(Protocol):
    # Character
    def load_character(self) -> CharacterSheet | None: ...
    def save_character(self, character: CharacterSheet) -> None: ...
    # World  (returns a fresh default World if none persisted yet)
    def load_world(self) -> World: ...
    def save_world(self, world: World) -> None: ...
    # Events (append-only)
    def append_event(self, event: Event) -> None: ...
    def load_events(self) -> list[Event]: ...
    # Narrative summary
    def load_summary(self) -> str: ...
    def save_summary(self, text: str) -> None: ...
    # In-progress combat
    def load_combat(self, combat_id: str) -> Combat | None: ...
    def save_combat(self, combat: Combat) -> None: ...
    def remove_combat(self, combat_id: str) -> None: ...
    # End states
    def archive(self, record: ArchiveRecord,
                destination: Literal["graveyard", "hall_of_fame"]) -> None: ...
    # Save slots
    def save_slot(self, name: str) -> None: ...
    def load_slot(self, name: str) -> None: ...
```
Impls: `InMemoryStorage` (tests), `JSONStorage` (one file per entity under `estado/`,
English filenames e.g. `character.json`, `world.json`, `events.json`, `summary.md`,
`combat_<id>.json`; atomic write = temp file + `os.replace`).

---

## 5. `combat/interfaces.py` — `CombatEngine` (Protocol) + impl `CombatService`

```python
class RoundOutcome(BaseModel):
    hero_as: int; enemy_as: int
    hitter: Literal["hero", "enemy", "tie"]
    damage_applied: int
    hero_stamina: int; enemy_stamina: int
    luck_used: LuckUse | None = None     # LuckUse = {roll:int, success:bool}
    ended: bool = False
    winner: Literal["hero", "enemy"] | None = None

class FleeResult(BaseModel):
    damage_taken: int = 2; hero_stamina: int; ended: bool = True
    hero_alive: bool = True   # False if the 2 flee-damage killed the hero (cycle 2)

class FinalResult(BaseModel):
    winner: Literal["hero", "enemy"] | None
    hero_final_stamina: int
    luck_spent: int; rounds: int
    drops: list[str] | None = None

class CombatEngine(Protocol):
    def start_combat(self, enemies: list[Enemy], flee_allowed: bool) -> Combat: ...
    def resolve_round(self, combat_id: str, use_luck: bool) -> RoundOutcome: ...
    def flee(self, combat_id: str) -> FleeResult: ...
    def end_combat(self, combat_id: str) -> FinalResult: ...
```
`CombatService.__init__(self, storage: StorageBackend, rng: RandomSource)` — injected.
- Active enemy = first enemy with `stamina > 0`.
- `resolve_round`: read sheet + combat → `regras.resolve_round` → if `use_luck` and hero
  is involved in the hit, call `test_luck` (persist luck −1 on the sheet) then
  `apply_luck_modifier`; apply damage; persist sheet + combat; hero stamina 0 → hero loses
  → `sheet.alive = False`, combat ends; last enemy stamina 0 → hero wins, combat ends.
- `start_combat`: reject an empty `enemies` list or all-`stamina<=0` enemies with `ValueError` (no soft-lock).
- `flee`: only if `flee_allowed`; hero takes 2 damage; combat ends. Sets `FleeResult.hero_alive`
  (`False` if those 2 damage dropped the hero to 0) so a fatal flee is distinguishable from a safe escape.
- `end_combat`: victory → persist hero stamina; **hero not alive (death in combat OR while fleeing)
  → `winner = "enemy"`** (unambiguous death signal); successful escape with the hero alive →
  `winner = None`. Returns `FinalResult`; removes the in-progress combat record.

---

## 6. `mcp/server.py` — MCP tool contract (stdio transport, server name `gamebook`)

Tool names MUST match `^[a-z0-9_]+$` (no hyphens). Exactly these 18 tools (`update_world` added in cycle 2 per ADR-010):

| tool | params | returns |
|---|---|---|
| `roll_dice` | `notation: str` | `{rolls, total}` |
| `test_luck` | — | `{roll, success, luck_after}` (persists luck −1) |
| `create_character` | `name: str` | `CharacterSheet` (rolls attributes, persists, alive) |
| `read_character_sheet` | — | `CharacterSheet` |
| `update_character_sheet` | `changes: dict` | `CharacterSheet` (validates invariants) |
| `read_world` | — | `World` |
| `update_world` | `changes: dict` | `World` (patch + allowlist; persists via `save_world`) |
| `register_event` | `type: str, data: dict` | the created `Event` |
| `read_events` | — | `list[Event]` |
| `read_summary` | — | `str` |
| `update_summary` | `text: str` | `{ok: true}` |
| `start_combat` | `enemies: list, flee_allowed: bool` | `Combat` |
| `resolve_combat_round` | `combat_id: str, use_luck: bool` | `RoundOutcome` |
| `flee_combat` | `combat_id: str` | `FleeResult` |
| `end_combat` | `combat_id: str` | `FinalResult` |
| `archive_character` | `destination: str` | `{ok: true}` |
| `save_progress` | `slot: str \| None` | `{ok: true, slot}` |
| `load_progress` | `slot: str \| None` | `{ok: true, slot}` |

**`update_character_sheet(changes)` patch semantics (binding on infra + content):**
`changes` is a partial dict of `CharacterSheet` fields. Top-level scalar/list fields
(`name, inventory, gold, provisions, conditions, alive`) are shallow-replaced by the
provided value. The attribute fields (`skill, stamina, luck`) accept a partial sub-dict
that is **merged** into the existing `Attribute` — e.g. `{"stamina": {"current": 18}}`
updates only `current` and keeps `initial`. Unknown fields are rejected with a clear
error. After merging, `dominio` invariants are validated: healing cannot push `current`
above `initial` (caller caps at `initial`, otherwise the call raises and state is left
unchanged). Returns the full updated `CharacterSheet`.

**`update_world(changes)` patch semantics (cycle 2, ADR-010 — binding on infra + content):**
`changes` is a partial dict over the allowlist `_UPDATABLE_WORLD_FIELDS = {current_location,
visited_locations, known_npcs, flags, turn}`. Scalar/list fields (`current_location`,
`visited_locations`, `known_npcs`, `turn`) are shallow-replaced; `flags` is **merged** key-wise
into the existing dict, so `{"flags": {"malachar_defeated": true}}` sets one flag without
dropping others. Unknown fields are rejected with a clear error. After merging,
`World.model_validate` enforces invariants (`turn >= 0`); on any error nothing is persisted
(state unchanged). Persists via `storage.save_world` and returns the full updated `World`.
This is the **sole** legal path to set the victory flag and advance the turn counter.

**`start_combat` enemy validation (cycle 2):** an empty `enemies` list, or one where every enemy
has `stamina <= 0`, is rejected with a clear `ValueError` before any combat is created — never a
silent soft-lock. Enforced in `CombatService.start_combat` (engine invariant) and surfaced by the
`start_combat` tool.

**`create_character(name)`:** rolls attributes via `regras.generate_attributes`, persists a
living `CharacterSheet`, returns it. RAISES if a *living* character already exists (no
accidental overwrite); a dead or absent character may be replaced. **`test_luck` (tool)**
reads the sheet's current luck, applies the rule, persists luck −1, returns
`{roll, success, luck_after}`. **`save_progress(slot=None)`** snapshots all state to the
slot (`None` → `"autosave"`); **`load_progress`** restores it.

**Composition root:** provide `build_server(storage: StorageBackend, combat: CombatEngine,
rng: RandomSource) -> FastMCP` taking interfaces; `main()` builds concretes
(`JSONStorage("estado")`, `CombatService(storage, rng)`, `random.Random()`) and runs
stdio. `python -m gamebook.mcp.server` is the entry point. `.mcp.json` at repo root
registers: `command: "uv"`, `args: ["run","python","-m","gamebook.mcp.server"]`.
Tools contain NO game rules — they orchestrate `regras`/`combate`/`storage` only.

---

## 7. `ModuloAventura` contract (content-designer, module 06)

```
AdventureModule = {
  metadata: { name, description, tone },
  opening: str,
  zones: [{ id, name, description, atmosphere, difficulty: int }],
  bestiary: [{ name, skill, stamina, behavior, drops?: [str] }],  # name/skill/stamina plug into start_combat
  victory_condition: { description, flag: str },                   # flag set in World on win
  special_rules?: [str]
}
```
Ignarok: Grey Mountain, archmage Malachar, 5–7 progressive zones, victory =
`flag "malachar_defeated"` true. **Original** content (no names/text/puzzles from the
copyrighted book). Bestiary enemies map to `Enemy{name, skill, stamina}` for `start_combat`.

---

## 8. Harness & commands (content-designer, modules 07/08)

Game-master `SKILL.md`, combat sub-agent `SKILL.md`, root `CLAUDE.md` session-opening
rule, and slash commands `/hero /backpack /map /save` — all reference the **exact MCP
tool names in §6**. `/hero` always prints real MCP state (`read_character_sheet`), never
a narrated value. Files: `.claude/skills/{game-master,combat-sub-agent,ignarok}/SKILL.md`,
`.claude/commands/{hero,backpack,map,save}.md`.
```
```
