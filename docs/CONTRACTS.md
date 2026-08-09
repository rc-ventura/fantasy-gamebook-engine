# CONTRACTS.md — Authoritative cross-module contracts (Tech Lead)

> **Status: APPROVED by Tech Lead.** This is the single source of truth for every
> cross-module interface in the Phase-1 MVP. The Portuguese specs in `docs/00..08`
> are the *requirements* source of truth; this file is their **English code contract**.
> If you must deviate from anything here, STOP and message the lead — do not drift silently.
>
> **Cycle-2 amendment (2026-06-21, ADR-010 ratified):** §6 tool count 17 → **18** — added
> `update_world`; added `start_combat` enemy validation; added `FleeResult.hero_alive` and an
> unambiguous flee-death `winner` in §5.
>
> **Slice-003 amendment (2026-06-27):** Added §9 (HTTP API), §10 (Scene), §11 (Postgres
> mapping) — folded from `specs/001-web-platform-migration/contracts/`.  Added
> `fastapi`, `pydantic-ai[anthropic]` (resolved: 2.0.0), `anthropic`, `uvicorn` to
> §0a (installed in pyproject.toml: 003-T001).  MCPToolset pattern: ADR-014.
>
> **Slice-004 amendment (2026-06-28, ADR-017/018/019):** Added §12 (Accounts & Identity),
> §13 (Session Lease), §14 (Privacy/GDPR), §15 (Observability).  Added
> `python-jose[cryptography]`, `httpx` (promoted to main), `opentelemetry-*` to §0a
> (installed in pyproject.toml: 004-T001). Auth seam swap via FastAPI dependency override
> (ADR-017). Session lease via `session_lease` table + `LeaseGuardMiddleware` (ADR-018).
> OTel auto-instrumentation + no-PII-in-spans rule (ADR-019).
>
> **Issue-9 amendment (2026-07-03):** `_configure_narrator` (`gamebook_web/api/app.py`) no
> longer hardcodes the activation gate to `ANTHROPIC_API_KEY`. It resolves the API-key env
> var from `NARRATOR_MODEL`'s `provider:model` prefix via `_PROVIDER_KEY_MAP` — see §0b.
> No new dependency: `pydantic-ai` (the full, non-slim package) already installs
> `pydantic-ai-slim` with the `openai` extra regardless of which extras are requested on
> `pydantic-ai[...]` in `pyproject.toml` (verified via `uv tree`), so OpenAI/OpenRouter
> models work with zero `pyproject.toml` changes.

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
4. **Dependencies are managed via `uv add`.** Do not add a dependency without recording
   it in this file. Phase-1 deps: `pydantic`, `mcp`. Phase-2 deps listed in §0a below.
5. **Determinism:** `rules` is pure; RNG is injected. Tests use a seeded RNG.
6. **Atomic storage:** never corrupt state on a mid-write crash (temp file + `os.replace`).
7. **JSON round-trip:** object → JSON → identical object, for every domain model.
8. **The AI never rolls dice in prose** — all randomness/state goes through MCP tools.
9. Use `/adr` for design decisions and `/learning-lesson` for non-obvious discoveries,
   *as you go*. These skills append an index to root `CLAUDE.md`; the lead reconciles it.

### 0a. Phase-2 Dependencies (added 2026-06-26, feature 001-web-platform-migration)

| Package | Version constraint | Purpose |
|---|---|---|
| `fastapi[standard]` | `>=0.115.0` | HTTP API server + OpenAPI generation (T009, T020–T021) |
| `sqlalchemy[asyncio]` | `>=2.0.0` | Async ORM/Core for PostgresStorage (T007) — **installed in pyproject.toml: 002-T001** |
| `asyncpg` | `>=0.30.0` | PostgreSQL async driver (T007) — **installed in pyproject.toml: 002-T001** |
| `alembic` | `>=1.14.0` | Schema migrations (T005–T006) — **installed in pyproject.toml: 002-T001** |
| `uvicorn` | `>=0.32.0` | ASGI server for `gamebook_web` (003-T001) |
| `pydantic-ai[anthropic]` | `>=0.0.15` (resolved: **2.0.0**) | Agent-based narrator harness emitting `Scene` (ADR-011, ADR-014) — MCPToolset.direct_call_tool for routes; toolsets=[] for agent runs |
| `anthropic` | `>=0.40.0` | Anthropic SDK; default model `claude-opus-4-8` (ADR-011) |
| `python-jose[cryptography]` | `>=3.3.0` | JWT decoding + JWKS key construction for OIDC auth (004-T003, ADR-017) |
| `httpx` | `>=0.27.0` | JWKS endpoint fetching + FastAPI test client; promoted to main deps (004-T001) |
| `opentelemetry-sdk` | `>=1.30.0` | Tracing/metrics/logs implementation (004-T019) |
| `opentelemetry-api` | `>=1.30.0` | OTel API surface (004-T019) |
| `opentelemetry-exporter-otlp-proto-grpc` | `>=1.30.0` | OTLP/gRPC exporter to operator-chosen backend (004-T019) |
| `opentelemetry-instrumentation-fastapi` | `>=0.50b0` | Auto-instrumentation for FastAPI (004-T019, ADR-019) |
| `opentelemetry-instrumentation-httpx` | `>=0.50b0` | Auto-instrumentation for httpx (JWKS calls visible in traces; 004-T019) |
| `pyyaml` | `>=6.0.3` | `backbone.yaml`/`templates.yaml` parsing for the adventure-structure loader (spec 009, §16) — was previously present only transitively (via `mcp[cli]`); promoted to a direct dependency since core code now imports it directly |

Dev-only:
| `pytest-asyncio` | `>=0.24.0` | Async test support for FastAPI/SQLAlchemy tests |

### 0b. Narrator provider selection (env vars, added 2026-07-03, issue #9)

`NARRATOR_MODEL` is a PydanticAI model string `provider:model` (default
`anthropic:claude-opus-4-8`, ADR-011). `_configure_narrator` activates
`PydanticNarrator` when the env var for the model's provider prefix is set,
else falls back to `FakeNarrator` (dev/test). Provider → key mapping
(`_PROVIDER_KEY_MAP` in `gamebook_web/api/app.py`):

| Provider prefix | Model string example | API key env var | Notes |
|---|---|---|---|
| `anthropic` | `anthropic:claude-opus-4-8` | `ANTHROPIC_API_KEY` | Default; unchanged behaviour. |
| `openai` | `openai:gpt-4o` | `OPENAI_API_KEY` | Routed via the `openai` SDK, already installed transitively (see amendment above). |
| `openrouter` | `openrouter:anthropic/claude-opus-4-8` | `OPENROUTER_API_KEY` | Native PydanticAI `OpenRouterModel`/`OpenRouterProvider` — **not** the `openai:openrouter/<id>` + `OPENAI_BASE_URL` workaround; pydantic-ai 2.0+ has first-class OpenRouter support. |

Setting `OPENAI_BASE_URL` still works for pointing the `openai` provider at any
OpenAI-compatible endpoint (the `openai` SDK reads it directly) but is not required
for OpenRouter — use the `openrouter:` prefix instead. An unset/unknown provider
prefix resolves to no API key, so the narrator falls back to `FakeNarrator` rather
than erroring — startup never fails from a bad `NARRATOR_MODEL` value.

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
    flags: dict[str, bool | int | str] = {}   # mostly bool; zone-dwell tracking (issue #28) needs int/str too
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

Tool names MUST match `^[a-z0-9_]+$` (no hyphens). Exactly these 20 tools (`update_world`
added in cycle 2 per ADR-010; `apply_healing`/`apply_damage` added in spec 009 per
ADR-033 — see §16). **Every tool takes `campaign_id: str` as its first parameter**
(ADR-018 Option A — one server process, all campaigns isolated by `campaign_id`; the
harness/narrator injects it via `ScopedMCPToolset`):

| tool | params | returns |
|---|---|---|
| `roll_dice` | `campaign_id: str, notation: str` | `{rolls, total}` |
| `test_luck` | `campaign_id: str` | `{roll, success, luck_after}` (persists luck −1) |
| `create_character` | `campaign_id: str, name: str` | `CharacterSheet` (rolls attributes, persists, alive) |
| `read_character_sheet` | `campaign_id: str` | `CharacterSheet` |
| `update_character_sheet` | `campaign_id: str, changes: dict` | `CharacterSheet` (validates invariants) |
| `apply_healing` | `campaign_id: str, amount: int, source: str` | `CharacterSheet` (relative; §16) |
| `apply_damage` | `campaign_id: str, amount: int, source: str` | `CharacterSheet` (relative; §16) |
| `read_world` | `campaign_id: str` | `World` |
| `update_world` | `campaign_id: str, changes: dict` | `World` (patch + allowlist; persists via `save_world`) |
| `register_event` | `campaign_id: str, type: str, data: dict` | the created `Event` |
| `read_events` | `campaign_id: str` | `list[Event]` |
| `read_summary` | `campaign_id: str` | `str` |
| `update_summary` | `campaign_id: str, text: str` | `{ok: true}` |
| `start_combat` | `campaign_id: str, enemies: list, flee_allowed: bool` | `Combat` |
| `resolve_combat_round` | `campaign_id: str, combat_id: str, use_luck: bool` | `RoundOutcome` |
| `flee_combat` | `campaign_id: str, combat_id: str` | `FleeResult` |
| `end_combat` | `campaign_id: str, combat_id: str` | `FinalResult` |
| `archive_character` | `campaign_id: str, destination: str` | `{ok: true}` |
| `save_progress` | `campaign_id: str, slot: str \| None` | `{ok: true, slot}` |
| `load_progress` | `campaign_id: str, slot: str \| None` | `{ok: true, slot}` |

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

**Composition root:** provide `build_server(storage_factory: Callable[[str], StorageBackend],
rng: RandomSource) -> FastMCP` taking a factory and a `RandomSource` (ADR-018 — `CombatService`
is constructed inside `build_server` from the factory, keeping it out of module scope). `main()`
builds the factory (one-per-campaign `JSONStorage` or `PostgresStorage`) and passes `random.Random()`
as the RNG, then calls `.run()` for stdio. `python -m gamebook.mcp.server` is the entry point.
`.mcp.json` at repo root registers: `command: "uv"`, `args: ["run","python","-m","gamebook.mcp.server"]`.
Tools contain NO game rules — they orchestrate `regras`/`combate`/`storage` only.

**Phase-2 `main()` factory (ADR-018 Option A, feature 001, 2026-06-26):** `main()` builds a
`storage_factory = lambda campaign_id: PostgresStorage(url, campaign_id)` when `DATABASE_URL` is
set, otherwise `lambda campaign_id: JSONStorage(f"estado/{campaign_id}")`. The factory is cached
by `campaign_id` inside `main()` (dict MVP; LRU pending for scale). `build_server` is unchanged —
it only receives the factory interface, never a concrete backend.

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

---

## 9. Phase-2 HTTP API contract (feature 001-web-platform-migration, 2026-06-26)

> Folded from `specs/001-web-platform-migration/contracts/http-api.md` per Principle III.

The HTTP API (FastAPI, `src/gamebook_web/api/`) exposes the engine as a documented,
authenticated REST/JSON API.  **No privileged hidden path** — the UI and external
clients use the same surface (FR-017).  Every route requires `Authorization: Bearer <JWT>`
validated against the OIDC IdP (FR-010); all operations are scoped to the authenticated
account (FR-009).

### Conventions
- **Auth**: `Authorization: Bearer <JWT>` — signature/aud/exp validated via JWKS (§9a).
- **Format**: JSON in/out; OpenAPI auto-generated at `/docs` (FR-016).
- **Scoping**: `{campaign_id}` must belong to the caller's account → `404`/`403`.
- **Write gating**: state-changing routes require holding the campaign session lease (FR-025);
  otherwise → `409 not_session_holder`.
- **Numbers**: every numeric/state change is produced by the engine via MCP — never the client.

### Identity & Account
| Method & path | Purpose |
|---|---|
| `GET /me` | Current account summary (created from JWT `sub` on first call) |
| `GET /me/export` | Export this account's game data (GDPR export) |
| `DELETE /me` | Delete account + all owned game data (GDPR erasure; cascade) |

### Campaigns
| Method & path | Purpose |
|---|---|
| `GET /campaigns` | List the caller's campaigns |
| `POST /campaigns` | Start a new campaign |
| `GET /campaigns/{id}` | Full campaign state (character sheet + world + events + summary) |
| `DELETE /campaigns/{id}` | Delete one campaign |

### Session Lease (FR-025)
| Method & path | Purpose |
|---|---|
| `POST /me/game/session` | Acquire/refresh the play-session lease |
| `POST /me/game/session/takeover` | Force-take the lease (validates current_token, ADR-023) |
| `DELETE /me/game/session` | Release the lease |

### Character
| Method & path | Purpose |
|---|---|
| `POST /campaigns/{id}/character` | Create the hero (attributes rolled by engine via MCP) |
| `GET /campaigns/{id}/character` | Read the character sheet (real engine state) |

### Play Loop
| Method & path | Purpose |
|---|---|
| `POST /campaigns/{id}/turn` | Take a turn (returns a validated `Scene`; all effects via MCP) |
| `GET /campaigns/{id}/scene` | Re-fetch the current scene (resume/refresh) |

### Save/Resume
| Method & path | Purpose |
|---|---|
| `POST /campaigns/{id}/save` | Checkpoint progress (durable, atomic) |
| `GET /campaigns/{id}` | Resume from the exact recorded point (FR-003) |

### Error Envelope (consistent shape across all endpoints)
```json
{ "error": { "code": "<code>", "message": "<human-readable>" } }
```
| HTTP | `code` | Meaning |
|---|---|---|
| 401 | `unauthenticated` | Missing/invalid token |
| 403/404 | `forbidden`/`not_found` | Campaign not owned by caller |
| 409 | `not_session_holder` | Lacks write lease |
| 409 | `run_ended` | Acting on a finished campaign |
| 422 | `invalid_scene` | Narrator output failed schema validation (never persisted) |
| 503 | `auth_unavailable` | IdP down; signed-in players continue read-only until expiry |

### 9a. Auth implementation details
- OIDC JWT/JWKS validation (`src/gamebook_web/auth/oidc_auth.py`) validates against the OIDC JWKS endpoint (PyJWT, migrated from python-jose).
- JWKS keys are cached in memory (5-minute TTL) for graceful degradation (FR-024).
- `RequireAuth = Depends(get_current_account_sub)` is the FastAPI dependency used by all protected routes.
- Environment variables: `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`.

---

## 10. Phase-2 `Scene` contract (narrator structured output, updated spec 007, 2026-06-30)

> Folded from `specs/001-web-platform-migration/contracts/scene.md` per Principle III.
> **Updated by spec 007-narrator-tool-use-refactor (ADR-029):** `effects[]` removed;
> narrator calls MCP tools directly during `agent.run()`.

`Scene` is the validated unit produced by the PydanticAI narrator for one turn (ADR-011,
swap boundary #3).  **Safety invariant**: the narrator calls MCP tools during generation,
sees real results, and narrates only those real results (Principle I).  The `Scene` carries
only prose and player choices — no deferred engine operations.
Invalid `Scene` objects are rejected with `422 invalid_scene` and never persisted.

```python
class Scene(BaseModel):
    narrative: str                   # 2–4 paragraphs, 2nd person, adventure-module tone
    choices:   list[Choice]          # numbered options offered to the player (empty = terminal)
    terminal:  bool = False          # True = death/victory; empty choices expected

class Choice(BaseModel):
    id:    str    # stable id ("1", "2", …)
    label: str    # what the player sees
```

**Validation rules (Pydantic v2):**
- `narrative` non-empty (field validator).
- `terminal=False` and `choices=[]` → `output_validator` raises `ModelRetry` (non-terminal scene
  must include choices — the non-tautological fix from spec 007).
- `terminal=True` → `choices` expected empty (death/victory end-states).
- No `effects` field — removed by spec 007 (ADR-029).

**Lifecycle (ADR-029):**
`POST /campaigns/{id}/turn` → narrator calls MCP tools during `agent.run()` → narrator emits
`Scene` (structural validator) → API re-reads engine state (post-turn reality) →
checks terminal state → stores scene → returns `TurnResponse`.

**Terminal scenes:** death/victory → `terminal=True`, `choices=[]`, campaign → `ended`, `ArchiveRecord` written.
Acting on an already-`ended` campaign → `409 run_ended`.

**File:** `src/gamebook_web/harness/scene.py` (Pydantic v2 `BaseModel`).

### 9b. `TurnResponse` shape (updated spec 007)

```json
{
  "scene": {
    "narrative": "...",
    "choices": [{"id": "1", "label": "..."}, ...]
  },
  "character": { ... },
  "world": { ... }
}
```

`effects_applied` field removed by spec 007 (ADR-029). All state changes happen inside
`narrator.narrate()` during `agent.run()`. The API re-reads state after narration and returns
the engine-authoritative values in `character` and `world`.

---

## 11. Phase-2 Postgres Mapping (swap boundary #1, 2026-06-26; updated 2026-07-02 by spec 006)

> Folded from `specs/001-web-platform-migration/data-model.md` §B per Principle III.
> **Implementation delivered by slice 002-persistence-foundation.**

All engine tables are scoped to a `campaign`.  The `StorageBackend` interface signature is
**unchanged**; `PostgresStorage` implements it against these tables
(`src/gamebook/storage/postgres.py`).  Each write runs in a single transaction (atomic,
Principle V).

**Deferred to slice 004:** `account`, `session_lease` (ownership / OIDC / session hold).
The `campaign` table therefore has **no `account_id` FK** until slice 004 lands.

```text
-- Slice 002 (this slice) — engine tables only:
campaign        (id PK text, status text DEFAULT 'active',
                 created_at timestamptz, updated_at timestamptz,
                 summary_text text DEFAULT '')
                  -- summary_text stores the narrative summary (load_summary/save_summary)
character_sheet (campaign_id PK FK→campaign CASCADE, data JSONB, alive bool)
world           (campaign_id PK FK→campaign CASCADE, location text, visited JSONB,
                 flags JSONB, turn int, data JSONB)
                  -- data column holds the full World model_dump(mode="json") for round-trip
event           (id PK text, campaign_id FK→campaign CASCADE, seq int,
                 payload JSONB, created_at timestamptz)
                  UNIQUE(campaign_id, seq)         -- append-only; seq preserves insertion order
combat          (campaign_id PK FK→campaign CASCADE, state JSONB nullable)
                  -- state = {combat_id: <Combat JSON>, ...}; NULL = no active fight
archive_record  (id PK text, campaign_id FK→campaign CASCADE, destination text,
                 payload JSONB, archived_at timestamptz)
save_slot       (campaign_id FK→campaign CASCADE, name text,
                 snapshot JSONB, created_at timestamptz)
                  PRIMARY KEY(campaign_id, name)

-- Slice 004 (deferred):
account         (id PK text, idp_subject UNIQUE text, created_at timestamptz)
session_lease   (campaign_id PK FK→campaign CASCADE, session_token text,
                 holder text, expires_at timestamptz)
-- campaign gains account_id FK→account CASCADE in slice 004
```

**Transaction semantics (Principle V):**
- Every `StorageBackend` method completes in a **single SQL transaction** — no partial writes.
- `_restore_snapshot` (used by `load_slot`) restores character, world, events, summary, and
  combats atomically in one transaction.

**Sync/async bridge (ADR-014):**
The `StorageBackend` protocol is synchronous; asyncpg/SQLAlchemy-asyncio is async.  A private
asyncio event loop in a daemon thread bridges the two.  Each storage method calls
`asyncio.run_coroutine_threadsafe(coro, self._loop).result()`, blocking until the coroutine
commits.  Works from any calling context (sync or already-running event loop).

**TLS policy (ADR-026, FR-037 — spec 006):**
- Connections require TLS **by default** (`ssl=require`).  Plaintext is allowed only with
  the explicit dev override `POSTGRES_SSL_MODE=disable`, which is **refused in production**
  (`ENV=production`).  Every deployment URL is therefore TLS-protected unless a developer
  deliberately opts out locally.

**Concurrency-safe event sequence (ADR-027, FR-038 — spec 006):**
- `append_event` serializes concurrent appends per campaign with a transaction-scoped
  advisory lock (`pg_advisory_xact_lock(hashtext(campaign_id))`) before computing
  `MAX(seq)+1`.  The prior unserialized `MAX(seq)+1` had a race: two concurrent
  transactions could compute the same seq.  `UNIQUE(campaign_id, seq)` remains the backstop.

**Deterministic lifecycle (ADR-027, FR-039 — spec 006):**
- `PostgresStorage.close()` disposes the async engine and stops the daemon event loop
  (thread joined).  It MUST be called on MCP server graceful shutdown and in live-Postgres
  test teardown.  Safe to call more than once.

**Consistent snapshots (ADR-027, FR-040 — spec 006):**
- `save_slot` builds its snapshot inside an explicit **read-only transaction**, so the
  captured character/world/events/summary/combat all belong to one consistent point in time.

**Identifier validation (ADR-027, FR-041 — spec 006):**
- `save_slot`, `load_slot`, `load_combat`, and `remove_combat` reject empty/`None`/`/`/`\`/
  `..` identifiers — parity with `JSONStorage` (no path-like identifiers reach SQL).

**Other notes:**
- `data JSONB` on `character_sheet` / `world` stores `model_dump(mode="json")` for exact
  round-trip (Principle V).  Attribute bounds stay enforced in `domain`, not the DB.
- Reads/writes are filtered by `campaign_id` (and `account_id` at the API layer in slice 004).
- Migration: `alembic/versions/0001_initial_schema.py` — apply with
  `DATABASE_URL=postgresql+asyncpg://... uv run alembic upgrade head`.
- Phase-2 MCP path (ADR-018 Option A): `DATABASE_URL=... uv run python -m gamebook.mcp.server`
  — one shared engine process; every tool takes `campaign_id` as its first parameter
  (the legacy `GAMEBOOK_CAMPAIGN_ID` boot-time scoping is retired).
- Test coverage: `tests/server/test_postgres_storage.py` (TLS, concurrency, lifecycle,
  snapshot, identifiers), `tests/server/test_atomic_writes.py` (crash **after** a real
  `execute()` → rollback, incl. multi-statement restore), `tests/qa/test_storage_swap.py`
  (consumer-level swap proof across memory/json/mock/**postgres**).

---

## 12. Accounts & Identity (slice 004)

**PII policy:** The engine DB stores only `sub` (opaque OIDC subject string) + `created_at`. No email, no display name. Account identity is owned by the OIDC provider.

### DB table: `account`

```sql
account (
  id         TEXT  PRIMARY KEY,      -- UUID string
  sub        TEXT  NOT NULL UNIQUE,  -- OIDC subject claim
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

### Auth seam

Routes `Depends(gamebook_web.auth.dev_auth.get_current_account)`. In production the lifespan installs:
```python
app.dependency_overrides[dev_auth.get_current_account] = oidc_auth.get_current_account
```
The play loop routes (003) are unchanged. Tests set `GAMEBOOK_DEV_MODE=1` to keep the dev stub.

### Account dataclass

```python
@dataclass(frozen=True)
class Account:
    account_id: str   # DB UUID (from account.id, NOT the OIDC sub)
```

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/me` | required | Return `{account_id, sub, created_at}` |
| `GET` | `/me/export` | required | Portable export of all owned game data (GDPR) |
| `DELETE` | `/me` | required | Cascade-delete account → campaigns → engine rows; `204` |

### GDPR cascade rules

`DELETE /me` cascade order:
1. `session_lease` rows for owned campaigns
2. Engine rows via FK `ON DELETE CASCADE` (character_sheet, world, event, combat, archive_record, save_slot)
3. `campaign` rows
4. `account` row

### JWT validation

ENV: `OIDC_JWKS_URI`, `OIDC_AUDIENCE`, `OIDC_ISSUER`  
Algorithms: RS256, ES256  
Key cache TTL: 5 min; force-refresh on unknown `kid` (key rotation)  
Validated-token cache: keyed on `(sha256(token), exp)` (full SHA-256 digest); serves cached `account_id` when JWKS unreachable; TTL = 60s (H-03)  

---

## 13. Session Lease (slice 004)

### DB table: `session_lease`

```sql
session_lease (
  campaign_id       TEXT  PRIMARY KEY REFERENCES campaign(id) ON DELETE CASCADE,
  lease_token       TEXT  NOT NULL,   -- UUID string
  acquired_at       TIMESTAMPTZ NOT NULL,
  expires_at        TIMESTAMPTZ NOT NULL,
  holder_account_id TEXT  NOT NULL REFERENCES account(id)
)
```

TTL: 30 minutes default; renewed on every successful state-changing request.

### LeaseService API

| Method | Raises | Description |
|---|---|---|
| `acquire(campaign_id, account_id)` | 409 `not_session_holder` | Create or renew lease; reject if another account holds unexpired lease (no `force_takeover` — H-01) |
| `validate(campaign_id, account_id, lease_token)` | 409 `not_session_holder` / `lease_expired` | Assert token AND account match the current unexpired holder (H-02; `hmac.compare_digest`) |
| `renew(campaign_id, lease_token)` | 409 `not_session_holder` | Extend TTL on success |
| `release(campaign_id, account_id, lease_token)` | — | Delete lease row (only if account + token match; H-02) |
| `takeover(campaign_id, account_id, current_token)` | 409 `not_session_holder` | Atomically replace holder; validates `current_token` (FR-027) |

### Lease endpoints

| Method | Path | Header | Description |
|---|---|---|---|
| `POST` | `/me/game/session` | — | Acquire lease → `{session_token, expires_at}` |
| `POST` | `/me/game/session/takeover` | — | Take over → new `{session_token, expires_at}` (validates `current_token`) |
| `DELETE` | `/me/game/session` | `X-Session-Lease` | Release lease |

### Lease enforcement (route-level `require_lease` dependency, ADR-031)

All mutating `/me/game/**` routes (`POST /me/game`, `POST /me/game/turn`, `POST /me/game/character`, `POST /me/game/save`, `DELETE /me/game`) have `Depends(require_lease)` which resolves the caller's active `campaign_id` from their account (D1) and calls `LeaseService.validate(campaign_id, account_id, X-Session-Lease)`. The lease is opt-in: enforcement begins only after a session calls `POST /me/game/session` to acquire a lease. `LeaseGuardMiddleware` is retained as a fail-closed guard for the OIDC-configured-but-no-database misconfiguration case only.

On token mismatch → `409 not_session_holder`  
On expiry → `409 lease_expired`  
On success → lease TTL renewed automatically  

---

## 14. Privacy / GDPR (slice 004)

Export (`GET /me/export`) returns:
```json
{
  "account": { "account_id": "...", "sub": "...", "created_at": "..." },
  "campaigns": [
    {
      "campaign_id": "...", "status": "...", "created_at": "...", "summary": "...",
      "character": { ... },
      "world": { ... },
      "events": [ ... ],
      "archive": [ { "destination": "...", "data": { ... }, "archived_at": "..." } ]
    }
  ]
}
```

The export includes all engine data for the account. PII in the export is limited to `sub` (opaque OIDC subject).

---

## 15. Observability (slice 004)

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OTLP_ENDPOINT` | (unset = InMemorySpanExporter) | OTLP gRPC endpoint, e.g. `http://localhost:4317` |
| `OTEL_SERVICE_NAME` | `gamebook-web` | OTel resource service name |

### Span attributes (no PII rule)

Allowed in spans: `campaign_id`, `account_id`, `turn_number` (opaque IDs).  
Forbidden: character name, inventory, narrative text, world flags, OIDC `sub` or email.

### Metric instruments

| Name | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | method, path, status | All HTTP requests |
| `turn_duration_seconds` | Histogram | — | Duration of /turn requests |
| `active_campaigns` | UpDownCounter | — | Currently active campaigns |
| `combat_rounds_total` | Counter | — | Combat rounds resolved |

### Error handling rule

On unhandled exception: set span status `ERROR` with `exception.type` only (no message, no traceback). Return `{"error": {"code": "internal_error", "message": "An error occurred"}}` to the client — never the raw exception.

---

## 16. Deterministic Turn Dispatcher & Adventure Structure (spec 009, ADR-033)

Closes the fabrication gap in §10's narrator contract: the narrator (`PydanticNarrator`
successor) no longer calls MCP tools at all. A `pydantic_graph.Graph`
(`harness/dispatcher.py`) sits between the player's input and the narrator: an intent
classifier (LLM, structured output, no tools) names the action; a deterministic
dispatcher (plain code, `call_engine()`/`direct_call_tool`, zero LLM calls) runs the
actual engine checks; the narrator (LLM, `output_type=Scene`, `toolsets=[]`) only
narrates the settled result. See `docs/adrs/ADR-033-*.md` and
`specs/009-deterministic-turn-dispatcher/` for full rationale.

### New MCP tools: `apply_healing` / `apply_damage`

Relative deltas on `stamina.current` — **not** absolute values like
`update_character_sheet`. `amount` MUST be a positive int (`amount <= 0` is rejected).
Clamped to `[0, initial]` by the same `Attribute` invariant `update_character_sheet`
already enforces. `apply_damage` sets `alive=False` if `stamina.current` reaches `0`.
Bounds the blast radius of any tool exposed to an LLM to a template's declared range,
rather than any in-bounds absolute value (defense in depth vs. `update_character_sheet`
alone).

### Narrator toolset (supersedes §10's tool-calling narrator)

The narrator's `Agent` receives `toolsets=[]` — zero tools, mutating or read-only. It
receives the turn's `TurnOutcome` (below) and the existing `NarratorContext` fields as
prompt content instead. `update_character_sheet`, `roll_dice`, `test_luck`, and the
combat tools remain in the 20-tool contract for the **dispatcher** and lifecycle
call-sites (`create_character`, etc.) — they are simply no longer LLM-reachable via the
narrator's toolset.

### Adventure structure files (swap boundary #2 extension — `SKILL.md` retained)

Two new file kinds, loaded by `harness/adventure_structure.py`:

- **`backbone.yaml`** (per module, co-located with that module's `SKILL.md` in
  `.claude/skills/<module>/`): the fixed backbone (`zones`, `key_npcs`, `boss`,
  `victory_condition`, `opening_location`), `probabilistic_encounters` (Layer 2, rolled
  once per zone per playthrough and persisted to `World.flags["encounter.<zone>.<id>"]`
  via `update_world`), `narrative_zones` (Layer 3, explicitly free), and the FR-011
  human-review gate fields `reviewed_by: str | None` / `reviewed_at: str | None`. A
  module with no `backbone.yaml` is fully Layer 3 by default (incremental migration).
- **`templates.yaml`** (shared across every module, at the top-level
  `adventure_modules/templates.yaml` — **not** under `.claude/skills/`, whose contract is
  "each subdirectory is a Claude Code Skill" and doesn't fit a bare shared-data file):
  the reusable `MechanicalSituationTemplate` library (`risky_action`, `skill_check`,
  `rest_heal`, `move`, `combat`), each with bounded `params` and a `mandatory_checks`
  list. `comparator` operations are a closed enum (`eq/ne/lt/le/gt/ge`) — **never**
  `eval()`/`exec()`.

Full schema: `specs/009-deterministic-turn-dispatcher/contracts/adventure-module-schema.md`
and `data-model.md`. Structural validation (FR-010/011, both structure and the
review-gate fields) is enforced by `tests/qa/test_adventure_structure.py`, part of the
mandatory pre-merge suite alongside the plugability audit.
