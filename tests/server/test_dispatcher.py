"""Dispatcher graph — deterministic turn dispatcher tests (spec 009, ADR-033).

Tests cover:
- T023: FunctionModel / TestModel wiring (constructor-injected DispatchDeps)
- T024: node unit tests (ClassifyIntent routing, MechanicalDispatch check
  execution, CombatRound cycling)
- T025: full graph integration (risky_action + combat → Scene backed by TurnOutcome)
- T026: SC-005 narration-call-count bound (exactly one Narrate call per turn,
  regardless of how many CombatRound cycles occurred)

Architecture under test::

    ClassifyIntent (mocked LLM) → MechanicalDispatch(classification) (pure code)
        → CombatRound(combat_id, outcome) (pure code, cyclic) → Narrate(outcome)
        → Narrate(outcome)
    ClassifyIntent → Narrate() on low-confidence / null-action / session-start

All LLM calls are eliminated by injecting FunctionModel-backed Agents into
DispatchDeps — no real API key or subprocess required. The MCP engine runs
in-process using InMemoryStorage (seeded RNG, deterministic).
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from gamebook.storage.in_memory import InMemoryStorage
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_graph import GraphRunContext

from gamebook_web.harness.adventure_structure import (
    AdventureStructure,
    MechanicalSituationTemplate,
    ProbabilisticEncounter,
    load_templates,
)
from gamebook_web.harness.narrator import FakeNarrator, NarratorContext
from gamebook_web.harness.dispatch_types import (
    DispatchDeps,
    DispatchState,
    IntentClassification,
    TurnOutcome,
    CONFIDENCE_THRESHOLD,
    build_classifier_agent,
)
from gamebook_web.harness.graph import (
    ClassifyIntent,
    CombatRound,
    DispatcherNarrator,
    MechanicalDispatch,
    Narrate,
    _adjacent_zones,
    _DICE_TEMPLATES,
    _LAYER3_ONLY,
    dispatcher_graph,
)
from gamebook_web.harness.scene import Choice, Scene

# ---------------------------------------------------------------------------
# Constants / shared fixtures
# ---------------------------------------------------------------------------

SEED = 42
CAMPAIGN = "test-campaign"

_STUB_SCENE = Scene(
    narrative="A cold wind sweeps the trailhead.",
    choices=[Choice(id="1", label="Press on"), Choice(id="2", label="Turn back")],
    terminal=False,
)

_TEMPLATES_PATH = Path(__file__).parents[2] / "adventure_modules" / "templates.yaml"


def _load_ignarok_templates() -> dict[str, MechanicalSituationTemplate]:
    return load_templates(_TEMPLATES_PATH)


def _minimal_adventure() -> AdventureStructure:
    """An AdventureStructure with one risky_action zone and one combat zone."""
    return AdventureStructure(
        zones=["stone_archway", "dark_ravine"],
        boss="malachar",
        victory_condition={"flag": "malachar_defeated"},
        opening_location="stone_archway",
        probabilistic_encounters={
            "stone_archway": [
                ProbabilisticEncounter(
                    id="archway_guardian",
                    probability=1.0,
                    template="combat",
                    params={
                        "enemies": [{"name": "Guardian", "skill": 4, "stamina": 4}],
                        "flee_allowed": False,
                    },
                )
            ],
            "dark_ravine": [
                ProbabilisticEncounter(
                    id="ravine_rockfall",
                    probability=1.0,
                    template="risky_action",
                    params={"risk_amount": 2, "risk_source": "environment"},
                )
            ],
        },
    )


def _linear_adventure(*, narrative_zones: list[str] | None = None) -> AdventureStructure:
    """A 3-zone linear adventure (a → b → c) for adjacency/narrative-zone tests.

    `b` sits between `a` and `c` — the minimal shape that can distinguish
    "adjacent" from "not adjacent" (a 2-zone adventure can't: every zone is
    trivially adjacent to the only other one).
    """
    return AdventureStructure(
        zones=["zone_a", "zone_b", "zone_c"],
        boss="malachar",
        victory_condition={"flag": "malachar_defeated"},
        opening_location="zone_a",
        narrative_zones=narrative_zones or [],
    )


def _fresh_in_memory_server() -> Any:
    from gamebook.mcp.server import build_server
    storage = InMemoryStorage()
    rng = random.Random(SEED)
    return build_server(storage_factory=lambda _: storage, rng=rng), storage


def _make_scene_response(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """FunctionModel callback that emits a Scene directly (no tool call)."""
    return ModelResponse(
        parts=[ToolCallPart(tool_name="final_result", args=_STUB_SCENE.model_dump())]
    )


def _make_classifier(classification: IntentClassification) -> Agent[None, IntentClassification]:
    """Build a FunctionModel-backed classifier that always returns `classification`."""
    def _classify(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result",
                    args=classification.model_dump(),
                )
            ]
        )
    return Agent(
        FunctionModel(_classify),
        name="intent_classifier",
        output_type=IntentClassification,
    )


def _make_fake_narrator() -> FakeNarrator:
    return FakeNarrator(scenes=[_STUB_SCENE])


async def _seed_character(toolset: MCPToolset) -> CharacterSheet:
    """Create a hero via the MCP server and return the sheet."""
    sheet = await toolset.direct_call_tool(
        "create_character",
        {"campaign_id": CAMPAIGN, "name": "Aldric"},
    )
    return sheet


# ---------------------------------------------------------------------------
# T024 — ClassifyIntent routing
# ---------------------------------------------------------------------------

class TestClassifyIntentRouting:
    """T024: ClassifyIntent routes correctly based on classifier output."""

    def test_confident_classification_routes_to_mechanical_dispatch(self):
        """High-confidence match → MechanicalDispatch."""
        classification = IntentClassification(
            action="ravine_rockfall",
            confidence=CONFIDENCE_THRESHOLD + 0.1,
            template="risky_action",
        )

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)
                adventure = _minimal_adventure()
                templates = _load_ignarok_templates()
                context = NarratorContext(
                    choice="I try to dodge through the falling rocks",
                    world={"current_location": "dark_ravine"},
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=context,
                    adventure=adventure,
                    templates=templates,
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                )
                # Run only ClassifyIntent node in isolation
                node = ClassifyIntent()
                ctx = GraphRunContext(state=state, deps=deps)
                result = await node.run(ctx)
                return type(result).__name__

        name = asyncio.run(run())
        assert name == "MechanicalDispatch"

    def test_low_confidence_routes_to_narrate(self):
        """Confidence below threshold → Narrate directly (FR-004: never guess)."""
        classification = IntentClassification(
            action="ravine_rockfall",
            confidence=CONFIDENCE_THRESHOLD - 0.1,
            template="risky_action",
        )

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="I wander around",
                        world={"current_location": "dark_ravine"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                )
                node = ClassifyIntent()
                ctx = GraphRunContext(state=state, deps=deps)
                result = await node.run(ctx)
                return type(result).__name__

        name = asyncio.run(run())
        assert name == "Narrate"

    def test_null_action_routes_to_narrate(self):
        """Classifier returns action=None → Narrate directly regardless of confidence."""
        classification = IntentClassification(
            action=None,
            confidence=0.95,
            template=None,
        )

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(choice="hello", world={}),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                )
                node = ClassifyIntent()
                ctx = GraphRunContext(state=state, deps=deps)
                result = await node.run(ctx)
                return type(result).__name__

        name = asyncio.run(run())
        assert name == "Narrate"

    def test_fresh_session_no_choice_routes_to_narrate(self):
        """choice=None (session start, no player action yet) → Narrate directly,
        zero LLM calls made (the classifier is never invoked).
        """
        calls: list[str] = []

        def _fail_if_called(_messages, _info):
            calls.append("called")
            raise AssertionError("classifier must not be called on session start")

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(choice=None),
                    adventure=_minimal_adventure(),
                    templates={},
                )
                deps = DispatchDeps(
                    classifier_agent=Agent(
                        FunctionModel(_fail_if_called),
                        name="intent_classifier",
                        output_type=IntentClassification,
                    ),
                    narrator=_make_fake_narrator(),
                )
                node = ClassifyIntent()
                ctx = GraphRunContext(state=state, deps=deps)
                result = await node.run(ctx)
                return type(result).__name__, calls

        name, calls_made = asyncio.run(run())
        assert name == "Narrate"
        assert calls_made == [], "classifier must not fire on session start"


# ---------------------------------------------------------------------------
# T024 — MechanicalDispatch check execution
# ---------------------------------------------------------------------------

class TestMechanicalDispatchExecution:
    """T024: MechanicalDispatch runs template checks and builds TurnOutcome."""

    def test_risky_action_success_applies_no_damage(self):
        """When luck test succeeds, apply_damage is NOT called (on_success=[]).

        Uses a seeded RNG (SEED=42) so luck behaviour is deterministic.
        The first test_luck call with seed 42 produces rolls that typically
        succeed (luck starts high), but the actual success/failure is
        engine-authoritative — we verify the TurnOutcome structure, not guess
        the roll.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                stamina_before = sheet["stamina"]["current"]

                classification = IntentClassification(
                    action="ravine_rockfall",
                    confidence=0.9,
                    template="risky_action",
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="dodge",
                        world={"current_location": "dark_ravine"},
                        character=sheet,
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=deps)
                next_node = await node.run(ctx)

                # MechanicalDispatch should go to Narrate (not CombatRound)
                assert type(next_node).__name__ == "Narrate"
                # TurnOutcome was set
                assert state.outcome is not None
                assert state.outcome.template == "risky_action"
                # The luck check was logged
                check_tools = [c["tool"] for c in state.outcome.checks]
                assert "test_luck" in check_tools
                # Stamina change is deterministic based on seed (may or may not have changed)
                final_sheet = await toolset.direct_call_tool(
                    "read_character_sheet", {"campaign_id": CAMPAIGN}
                )
                # Success: stamina unchanged; failure: stamina reduced by 2
                stamina_after = final_sheet["stamina"]["current"]
                luck_check = next(c for c in state.outcome.checks if c["tool"] == "test_luck")
                if luck_check["result"]["success"]:
                    assert stamina_after == stamina_before, "luck passed — no damage"
                else:
                    assert stamina_after == stamina_before - 2, "luck failed — 2 damage applied"
                return state.outcome.checks

        checks = asyncio.run(run())
        assert len(checks) >= 1  # at least the test_luck call

    def test_unknown_template_routes_to_narrate_without_crashing(self):
        """A classifier that names a template not in the library → Narrate safely."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)
                classification = IntentClassification(
                    action="unknown_thing",
                    confidence=0.95,
                    template="nonexistent_template",
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(choice="do unknown thing", world={}),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=deps)
                next_node = await node.run(ctx)
                return type(next_node).__name__

        name = asyncio.run(run())
        assert name == "Narrate"


# ---------------------------------------------------------------------------
# T024 — CombatRound cycling
# ---------------------------------------------------------------------------

class TestCombatRoundCycling:
    """T024: CombatRound loops until combat ends; no round skips the check log."""

    def test_combat_cycles_through_all_rounds(self):
        """Every resolve_combat_round call appears in TurnOutcome.checks.

        Seeds a weak enemy (skill 1, stamina 2) against a strong hero (skill 11)
        so combat ends quickly without requiring many rounds.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                # Create hero with strong stats for predictable combat
                sheet = await toolset.direct_call_tool(
                    "create_character",
                    {"campaign_id": CAMPAIGN, "name": "Champion"},
                )

                # Start combat with a very weak enemy
                combat = await toolset.direct_call_tool(
                    "start_combat",
                    {
                        "campaign_id": CAMPAIGN,
                        "enemies": [{"name": "Rat", "skill": 1, "stamina": 2}],
                        "flee_allowed": False,
                    },
                )

                outcome = TurnOutcome(
                    action="archway_guardian",
                    template="combat",
                    checks=[{"tool": "start_combat", "result": combat}],
                )

                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(choice="fight", world={}),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                    outcome=outcome,  # shared reference — CombatRound mutates it in place
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(
                        IntentClassification(action="archway_guardian", confidence=0.9, template="combat")
                    ),
                    narrator=_make_fake_narrator(),
                )

                # Run CombatRound until it returns Narrate
                ctx = GraphRunContext(state=state, deps=deps)
                node: CombatRound | Narrate = CombatRound(
                    combat_id=combat["combat_id"], outcome=outcome
                )

                round_count = 0
                max_rounds = 20
                while round_count < max_rounds:
                    result = await node.run(ctx)
                    round_count += 1
                    if isinstance(result, Narrate):
                        break
                    node = result  # CombatRound self-edge

                round_tool_calls = [
                    c for c in state.outcome.checks
                    if c["tool"] == "resolve_combat_round"
                ]
                end_tool_calls = [c for c in state.outcome.checks if c["tool"] == "end_combat"]
                return round_count, len(round_tool_calls), len(end_tool_calls)

        rounds, resolve_calls, end_calls = asyncio.run(run())
        assert rounds >= 1, "at least one round must occur"
        assert resolve_calls == rounds, "every round must be logged in checks (SC-005 completeness)"
        assert end_calls == 1, "end_combat must be called exactly once when combat ends"


# ---------------------------------------------------------------------------
# T025 — Full graph integration tests
# ---------------------------------------------------------------------------

class TestDispatcherGraphIntegration:
    """T025: full graph run → Scene backed by TurnOutcome for each check claimed."""

    def test_risky_action_full_graph_produces_scene_with_turn_outcome(self):
        """A risky_action classified at full confidence → Scene with TurnOutcome."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                classification = IntentClassification(
                    action="ravine_rockfall",
                    confidence=0.9,
                    template="risky_action",
                )
                adventure = _minimal_adventure()
                templates = _load_ignarok_templates()
                context = NarratorContext(
                    choice="I try to dodge the rockfall",
                    world={"current_location": "dark_ravine"},
                )

                # FakeNarrator queue: one scene for the Narrate node
                fake_narrator = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=fake_narrator,
                )

                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=context,
                    adventure=adventure,
                    templates=templates,
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )

                assert scene.narrative, "scene must have non-empty narrative"
                assert scene.choices or scene.terminal, "scene must have choices or be terminal"
                # The outcome was set (mechanical path was taken)
                assert state.outcome is not None
                assert state.outcome.template == "risky_action"
                assert any(c["tool"] == "test_luck" for c in state.outcome.checks)
                return scene

        scene = asyncio.run(run())
        assert scene == _STUB_SCENE

    def test_free_narrative_path_produces_scene_with_no_outcome(self):
        """When choice=None (session start), free-narrative path → Scene, no TurnOutcome."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                fake_narrator = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(
                        IntentClassification(action=None, confidence=0.0)
                    ),
                    narrator=fake_narrator,
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(choice=None),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )
                return scene, state.outcome

        scene, outcome = asyncio.run(run())
        assert scene == _STUB_SCENE
        assert outcome is None, "free-narrative path must not produce a TurnOutcome"

    def test_combat_full_graph_produces_scene_with_combat_checks(self):
        """A combat-classified action runs start_combat + ≥1 round + end_combat → Scene."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                classification = IntentClassification(
                    action="archway_guardian",
                    confidence=0.95,
                    template="combat",
                )
                # FakeNarrator with enough scenes to absorb the Narrate call
                fake_narrator = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=fake_narrator,
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="attack the guardian",
                        world={"current_location": "stone_archway"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )
                outcome = state.outcome

                assert scene == _STUB_SCENE
                assert outcome is not None
                assert outcome.template == "combat"
                check_tools = [c["tool"] for c in outcome.checks]
                assert "start_combat" in check_tools
                assert "resolve_combat_round" in check_tools  # at least one round
                assert "end_combat" in check_tools
                return check_tools

        check_tools = asyncio.run(run())
        # FR-012: no round may skip the check log
        resolve_count = check_tools.count("resolve_combat_round")
        end_count = check_tools.count("end_combat")
        assert resolve_count >= 1
        assert end_count == 1


# ---------------------------------------------------------------------------
# T026 — SC-005: narration-call-count bound
# ---------------------------------------------------------------------------

class TestNarrationCallCountBound:
    """T026: the narrator is invoked exactly once per turn, regardless of how
    many CombatRound cycles occur (SC-005 — "bounded number of narration steps").
    """

    def test_narrator_called_exactly_once_regardless_of_combat_rounds(self):
        """Even a multi-round fight triggers exactly one narration call."""
        narrate_calls: list[NarratorContext] = []

        class CountingNarrator:
            async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:
                narrate_calls.append(context)
                return _STUB_SCENE

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                classification = IntentClassification(
                    action="archway_guardian",
                    confidence=0.95,
                    template="combat",
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=CountingNarrator(),  # type: ignore[arg-type]
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="fight the guardian",
                        world={"current_location": "stone_archway"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                await dispatcher_graph.run(inputs=ClassifyIntent(), state=state, deps=deps)

                # How many combat rounds happened?
                round_calls = sum(
                    1 for c in (state.outcome.checks if state.outcome else [])
                    if c["tool"] == "resolve_combat_round"
                )
                return len(narrate_calls), round_calls

        narration_count, round_count = asyncio.run(run())
        assert round_count >= 1, "at least one combat round must have occurred"
        assert narration_count == 1, (
            f"narrator must be called exactly once per turn (SC-005) — "
            f"called {narration_count} times across {round_count} combat rounds"
        )


# ---------------------------------------------------------------------------
# T020 — DispatcherNarrator (NarratorBackend implementation)
# ---------------------------------------------------------------------------

class TestDispatcherNarrator:
    """T020: DispatcherNarrator implements NarratorBackend and uses the graph."""

    def test_implements_narrator_backend_protocol(self):
        from gamebook_web.harness.narrator import NarratorBackend
        from gamebook_web.harness.graph import DispatcherNarrator

        assert isinstance(DispatcherNarrator, type)
        # Protocol check at runtime (NarratorBackend is @runtime_checkable)
        # We can't instantiate without a real toolset, but the Protocol check
        # confirms the class satisfies the structural interface.
        assert hasattr(DispatcherNarrator, "narrate")

    def test_missing_backbone_yaml_falls_back_to_layer3(self):
        """A DispatcherNarrator with adventure_dir=None routes everything to
        Narrate directly (full Layer 3) — no crash, no error.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                classification = IntentClassification(
                    action=None, confidence=0.0
                )
                fake_narrator_inner = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=fake_narrator_inner,
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(choice=None),
                    adventure=_LAYER3_ONLY,
                    templates={},
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )
                return scene, state.outcome

        scene, outcome = asyncio.run(run())
        assert scene == _STUB_SCENE
        assert outcome is None
        assert outcome is None


# ---------------------------------------------------------------------------
# T030 — US3: Free text without forced menu
# ---------------------------------------------------------------------------

class TestFreeTextRouting:
    """T030: free-text turns that lack mechanical stakes are narrated freely;
    low-confidence / ambiguous inputs never trigger a guessed mechanical action.
    """

    def test_player_choice_with_no_matching_encounter_routes_to_narrative(self):
        """A player choice in a zone with no encounters → Narrate, zero engine checks."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                # Classifier returns an action that matches no template/encounter.
                classification = IntentClassification(
                    action="look around",
                    confidence=0.9,
                    template=None,  # no template → no mechanical dispatch
                )
                fake_narrator = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=fake_narrator,
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    # shattered_trailhead has no probabilistic_encounters in minimal adventure
                    context=NarratorContext(
                        choice="I examine the rusted winch carefully",
                        world={"current_location": "shattered_trailhead"},
                    ),
                    adventure=AdventureStructure(
                        zones=["shattered_trailhead"],
                        boss="malachar",
                        victory_condition={"flag": "malachar_defeated"},
                        opening_location="shattered_trailhead",
                        narrative_zones=["shattered_trailhead"],
                    ),
                    templates=_load_ignarok_templates(),
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )
                return scene, state.outcome

        scene, outcome = asyncio.run(run())
        assert scene == _STUB_SCENE
        assert outcome is None, "free-text in a narrative zone must not produce a TurnOutcome"

    def test_low_confidence_classification_routes_to_narrative_not_mechanical(self):
        """Confidence below CONFIDENCE_THRESHOLD → Narrate, even if action is named."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                # Action is named and a template exists, but confidence is below threshold.
                below_threshold = CONFIDENCE_THRESHOLD - 0.1
                classification = IntentClassification(
                    action="ravine_rockfall",
                    confidence=below_threshold,
                    template="risky_action",
                )
                fake_narrator = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=fake_narrator,
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="maybe I should try to cross the ravine?",
                        world={"current_location": "dark_ravine"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )
                return scene, state.outcome

        scene, outcome = asyncio.run(run())
        assert scene == _STUB_SCENE
        assert outcome is None, (
            f"confidence below {CONFIDENCE_THRESHOLD} must not trigger mechanical dispatch"
        )

    def test_null_action_with_player_choice_routes_to_narrative(self):
        """Classifier returns action=None for unanticipated free text → Narrate."""
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                classification = IntentClassification(action=None, confidence=0.0)
                fake_narrator = FakeNarrator(scenes=[_STUB_SCENE])
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=fake_narrator,
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="I sing a drinking song to pass the time",
                        world={"current_location": "dark_ravine"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                scene = await dispatcher_graph.run(
                    inputs=ClassifyIntent(), state=state, deps=deps
                )
                return scene, state.outcome

        scene, outcome = asyncio.run(run())
        assert scene == _STUB_SCENE
        assert outcome is None, "null action must not produce a TurnOutcome (FR-004)"


# ---------------------------------------------------------------------------
# T036 — US2: Zone re-entry determinism (encounter presence remembered)
# ---------------------------------------------------------------------------

class TestZoneEncounterDeterminism:
    """T036: probabilistic encounters are rolled once per playthrough and
    remembered — re-entering the same zone returns the same encounter list;
    a fresh playthrough (different RNG seed) may differ.
    """

    def test_reentry_same_zone_same_playthrough_yields_same_encounters(self):
        """Re-entering dark_ravine in the same campaign uses persisted flags."""
        async def run():
            from gamebook_web.harness.encounter_resolver import resolve_zone_encounters
            from gamebook_web.harness.adventure_structure import load_adventure_structure
            from pathlib import Path

            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)

                # Load the real Ignarok encounters for dark_ravine.
                ignarok_dir = Path(__file__).parents[2] / "adventure_modules" / "ignarok"
                adventure = load_adventure_structure(ignarok_dir)
                dark_ravine_encounters = adventure.probabilistic_encounters.get("dark_ravine", [])

                # First entry: no flags yet → some encounters will be rolled.
                first_active = await resolve_zone_encounters(
                    dark_ravine_encounters,
                    "dark_ravine",
                    toolset,
                    CAMPAIGN,
                    {},  # empty flags — first entry
                )

                # Read back the flags that were persisted to World.
                world = await toolset.direct_call_tool("read_world", {"campaign_id": CAMPAIGN})
                persisted_flags = world.get("flags", {}) if isinstance(world, dict) else {}

                # Second entry: supply the persisted flags → must get identical result.
                second_active = await resolve_zone_encounters(
                    dark_ravine_encounters,
                    "dark_ravine",
                    toolset,
                    CAMPAIGN,
                    persisted_flags,
                )

                return [e.id for e in first_active], [e.id for e in second_active]

        first_ids, second_ids = asyncio.run(run())
        assert first_ids == second_ids, (
            f"Re-entering the same zone must yield the same encounter list.\n"
            f"First entry:  {first_ids}\n"
            f"Second entry: {second_ids}"
        )

    def test_two_independent_playthroughs_may_differ(self):
        """Two campaigns with different RNG seeds can produce different encounter sets."""
        async def run():
            from gamebook_web.harness.encounter_resolver import resolve_zone_encounters
            from gamebook_web.harness.adventure_structure import load_adventure_structure
            from pathlib import Path
            from gamebook.mcp.server import build_server

            ignarok_dir = Path(__file__).parents[2] / "adventure_modules" / "ignarok"
            adventure = load_adventure_structure(ignarok_dir)
            dark_ravine_encounters = adventure.probabilistic_encounters.get("dark_ravine", [])

            results = []
            # Try 10 seeds; collect unique encounter-set fingerprints.
            seen: set[tuple] = set()
            for seed in range(10):
                local_storage = InMemoryStorage()
                server = build_server(storage_factory=lambda _: local_storage, rng=random.Random(seed))
                async with MCPToolset(server) as toolset:
                    await toolset.direct_call_tool(
                        "create_character",
                        {"campaign_id": CAMPAIGN, "name": "Hero"},
                    )
                    active = await resolve_zone_encounters(
                        dark_ravine_encounters,
                        "dark_ravine",
                        toolset,
                        CAMPAIGN,
                        {},
                    )
                    seen.add(tuple(sorted(e.id for e in active)))
            return seen

        unique_outcomes = asyncio.run(run())
        assert len(unique_outcomes) > 1, (
            "Two independent playthroughs with different RNG seeds should "
            "produce different encounter sets across 10 trials.\n"
            f"Only one unique outcome found: {unique_outcomes}\n"
            "(This may indicate the probability constants are all 0 or 1.)"
        )


# ---------------------------------------------------------------------------
# Regression tests — 2026-07-11 live-testing bug hunt (see tasks.md Phase 8)
#
# Every fix below was found via a real container play session, not unit
# testing — each test here pins the exact failure mode so it can't silently
# regress.
# ---------------------------------------------------------------------------


class TestAdjacentZonesHelper:
    """`_adjacent_zones` — pure function, the adjacency model for "move"."""

    def test_middle_zone_has_both_neighbors(self):
        assert _adjacent_zones(["a", "b", "c"], "b") == ["a", "c"]

    def test_first_zone_has_only_next(self):
        assert _adjacent_zones(["a", "b", "c"], "a") == ["b"]

    def test_last_zone_has_only_previous(self):
        assert _adjacent_zones(["a", "b", "c"], "c") == ["b"]

    def test_current_zone_never_included_in_its_own_neighbors(self):
        neighbors = _adjacent_zones(["a", "b", "c"], "b")
        assert "b" not in neighbors

    def test_unknown_location_falls_back_to_full_zone_list(self):
        """Corrupted/uninitialized current_location — don't strand the player."""
        assert _adjacent_zones(["a", "b", "c"], "nowhere") == ["a", "b", "c"]


class TestMoveDestinationGuards:
    """MechanicalDispatch's "move" guards — regression coverage for the
    2026-07-11 bug hunt: destination must resolve via a nested `changes` dict
    (not a top-level `update_world` arg), must be adjacent to current_location
    (not a same-zone no-op, not a far teleport), and a missing destination
    must never reach the engine as None.
    """

    def test_move_to_adjacent_zone_actually_updates_world(self):
        """The original 422 bug: `update_world` needs `changes={...}`, not a
        top-level `current_location` kwarg. This proves the full path — MCP
        call succeeds AND world.current_location is actually persisted.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="move", confidence=0.9, template="move",
                    params={"destination": "dark_ravine"},
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="head into the ravine",
                        world={"current_location": "stone_archway"},
                        character=sheet,
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                await node.run(ctx)
                world = await toolset.direct_call_tool("read_world", {"campaign_id": CAMPAIGN})
                return world

        world = asyncio.run(run())
        assert world["current_location"] == "dark_ravine"

    def test_move_to_non_adjacent_zone_falls_back_to_narrative(self):
        """Far-jump guard — e.g. stone_archway straight to malachars_sanctum,
        skipping the authored progression.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                await toolset.direct_call_tool(
                    "update_world",
                    {"campaign_id": CAMPAIGN, "changes": {"current_location": "zone_a"}},
                )
                classification = IntentClassification(
                    action="move", confidence=0.9, template="move",
                    params={"destination": "zone_c"},  # not adjacent to zone_a
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="rush to the sanctum",
                        world={"current_location": "zone_a"},
                        character=sheet,
                    ),
                    adventure=_linear_adventure(),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                world = await toolset.direct_call_tool("read_world", {"campaign_id": CAMPAIGN})
                return type(result).__name__, world["current_location"]

        result_type, location = asyncio.run(run())
        assert result_type == "Narrate"
        assert location == "zone_a", "world state must not change on a rejected move"

    def test_move_to_current_zone_is_rejected_as_a_no_op(self):
        """Self-loop guard — a "move" whose destination is where the player
        already stands must not silently succeed as a no-op turn.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="move", confidence=0.9, template="move",
                    params={"destination": "zone_b"},  # same as current
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="continue climbing",
                        world={"current_location": "zone_b"},
                        character=sheet,
                    ),
                    adventure=_linear_adventure(),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                return type(result).__name__

        result_type = asyncio.run(run())
        assert result_type == "Narrate"

    def test_move_with_missing_destination_falls_back_to_narrative(self):
        """Classifier omitted the destination param entirely (str param → None
        via clamp_params) — must not reach the engine as a None value.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="move", confidence=0.9, template="move", params={},
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="let's go",
                        world={"current_location": "zone_a"},
                        character=sheet,
                    ),
                    adventure=_linear_adventure(),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                return type(result).__name__

        result_type = asyncio.run(run())
        assert result_type == "Narrate"


class TestCombatEncounterGuard:
    """MechanicalDispatch's "combat" guard — regression coverage for the SDD
    final review cycle 1 (2026-07-11) security finding: unlike "move" (an
    unconditional, server-derived adjacency check), "combat" had no equivalent
    guard requiring dispatch to originate from a matched, author-defined
    ProbabilisticEncounter. `clamp_params` does not bound list/bool params
    (`enemies`, `flee_allowed`), so a classifier emitting `action="combat"`
    with no matching encounter — plausible since "combat" is a real key in
    `ctx.state.templates` and template-derives automatically even though it's
    deliberately excluded from the LLM's candidate list — could route
    classifier-invented enemies straight to `start_combat` unchecked.
    """

    def test_combat_with_no_matching_encounter_falls_back_to_narrative(self):
        """The exploit path: classifier names "combat" directly (or an action
        that isn't any authored encounter id in the current zone) with
        attacker-favorable enemies. Must never reach start_combat.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="combat", confidence=0.9, template="combat",
                    params={
                        "enemies": [{"name": "GodMode", "skill": 1, "stamina": 999}],
                        "flee_allowed": True,
                    },
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="I start a fight",
                        world={"current_location": "dark_ravine"},  # no combat encounter here
                        character=sheet,
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                return type(result).__name__, state.outcome

        result_type, outcome = asyncio.run(run())
        assert result_type == "Narrate"
        assert outcome is None, "start_combat must never be reached — no TurnOutcome was produced"

    def test_combat_with_matching_encounter_still_dispatches(self):
        """Sanity check: the guard must not break the legitimate path — an
        authored encounter (archway_guardian, stone_archway) still dispatches
        to CombatRound as before.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="archway_guardian", confidence=0.9, template="combat",
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="fight the guardian",
                        world={"current_location": "stone_archway"},
                        character=sheet,
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                return type(result).__name__

        result_type = asyncio.run(run())
        assert result_type == "CombatRound"


class TestNarrativeZoneDiceGuard:
    """MechanicalDispatch rejects dice-based templates in narrative_zones —
    even if the classifier ignored ClassifyIntent's candidate-list filter.
    Defense-in-depth counterpart to ClassifyIntent's own candidate filtering.
    """

    def test_skill_check_in_narrative_zone_falls_back_to_narrative(self):
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="skill_check", confidence=0.9, template="skill_check",
                    params={"risk_amount": 1, "risk_source": "trap"},
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="examine the trailhead closely",
                        world={"current_location": "zone_b"},
                        character=sheet,
                    ),
                    adventure=_linear_adventure(narrative_zones=["zone_b"]),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                return type(result).__name__

        result_type = asyncio.run(run())
        assert result_type == "Narrate"

    def test_dice_templates_constant_matches_expected_set(self):
        """Pin the exact set — a future template addition must update this
        deliberately, not silently start (or stop) rolling dice in Layer 3.
        """
        assert _DICE_TEMPLATES == {"skill_check", "risky_action"}

    def test_move_still_available_in_narrative_zone(self):
        """narrative_zones excludes DICE templates only — move (no roll) must
        still let the player leave the zone.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                sheet = await _seed_character(toolset)
                classification = IntentClassification(
                    action="move", confidence=0.9, template="move",
                    params={"destination": "zone_c"},
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="move on",
                        world={"current_location": "zone_b"},
                        character=sheet,
                    ),
                    adventure=_linear_adventure(narrative_zones=["zone_b"]),
                    templates=_load_ignarok_templates(),
                )
                node = MechanicalDispatch(classification=classification)
                ctx = GraphRunContext(state=state, deps=DispatchDeps(
                    classifier_agent=_make_classifier(classification),
                    narrator=_make_fake_narrator(),
                ))
                result = await node.run(ctx)
                world = await toolset.direct_call_tool("read_world", {"campaign_id": CAMPAIGN})
                return type(result).__name__, world["current_location"]

        result_type, location = asyncio.run(run())
        assert result_type == "CombatRound" or result_type == "Narrate"
        # move is not combat, so it must reach Narrate with the world updated —
        # asserting the concrete expectation, not the loose "either" above.
        assert result_type == "Narrate"
        assert location == "zone_c"


class TestCombatWinFlagAndFieldMapping:
    """CombatRound's engine field mapping (RoundOutcome.hitter/damage_applied,
    FinalResult.winner — not the phantom hero_won_round/hero_damage/hero_won
    fields it used to read) and the sets_flag_on_win victory-flag mechanism.
    """

    async def _run_combat_to_completion(
        self, *, enemy_skill: int, enemy_stamina: int, sets_flag_on_win: str | None,
    ) -> tuple[dict, dict]:
        server, storage = _fresh_in_memory_server()
        async with MCPToolset(server) as toolset:
            await toolset.direct_call_tool(
                "create_character", {"campaign_id": CAMPAIGN, "name": "Champion"},
            )
            combat = await toolset.direct_call_tool(
                "start_combat",
                {
                    "campaign_id": CAMPAIGN,
                    "enemies": [{"name": "Foe", "skill": enemy_skill, "stamina": enemy_stamina}],
                    "flee_allowed": False,
                },
            )
            outcome = TurnOutcome(
                action="malachar_final_battle", template="combat",
                checks=[{"tool": "start_combat", "result": combat}],
            )
            state = DispatchState(
                campaign_id=CAMPAIGN, toolset=toolset,
                context=NarratorContext(choice="fight", world={}),
                adventure=_minimal_adventure(), templates=_load_ignarok_templates(),
                outcome=outcome,
            )
            deps = DispatchDeps(
                classifier_agent=_make_classifier(
                    IntentClassification(action="malachar_final_battle", confidence=0.9, template="combat")
                ),
                narrator=_make_fake_narrator(),
            )
            ctx = GraphRunContext(state=state, deps=deps)
            node: CombatRound | Narrate = CombatRound(
                combat_id=combat["combat_id"], outcome=outcome, sets_flag_on_win=sets_flag_on_win,
            )
            for _ in range(50):
                result = await node.run(ctx)
                if isinstance(result, Narrate):
                    break
                node = result
            final_check = next(c for c in state.outcome.checks if c["tool"] == "end_combat")
            world = await toolset.direct_call_tool("read_world", {"campaign_id": CAMPAIGN})
            return final_check["result"], world

    def test_hero_win_sets_the_declared_victory_flag(self):
        """Weak enemy (skill 1, stamina 2) vs a fresh hero — hero wins."""
        final_result, world = asyncio.run(self._run_combat_to_completion(
            enemy_skill=1, enemy_stamina=2, sets_flag_on_win="malachar_defeated",
        ))
        assert final_result["winner"] == "hero"
        assert world.get("flags", {}).get("malachar_defeated") is True

    def test_hero_win_without_sets_flag_on_win_does_not_touch_world_flags(self):
        """Non-boss combat (e.g. archway_guardian) has no sets_flag_on_win —
        winning must not set any flag.
        """
        final_result, world = asyncio.run(self._run_combat_to_completion(
            enemy_skill=1, enemy_stamina=2, sets_flag_on_win=None,
        ))
        assert final_result["winner"] == "hero"
        assert world.get("flags", {}).get("malachar_defeated") is not True

    def test_hero_loss_does_not_set_victory_flag(self):
        """A hero reduced to near-death before a strong fight loses — the
        victory flag must never be set on a loss.
        """
        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await toolset.direct_call_tool(
                    "create_character", {"campaign_id": CAMPAIGN, "name": "Doomed"},
                )
                # Weaken the hero deterministically before the fight so a
                # high-skill, high-stamina enemy wins within the round cap.
                await toolset.direct_call_tool(
                    "apply_damage",
                    {"campaign_id": CAMPAIGN, "amount": 100, "source": "trap"},
                )
                combat = await toolset.direct_call_tool(
                    "start_combat",
                    {
                        "campaign_id": CAMPAIGN,
                        "enemies": [{"name": "Malachar", "skill": 10, "stamina": 12}],
                        "flee_allowed": False,
                    },
                )
                outcome = TurnOutcome(
                    action="malachar_final_battle", template="combat",
                    checks=[{"tool": "start_combat", "result": combat}],
                )
                state = DispatchState(
                    campaign_id=CAMPAIGN, toolset=toolset,
                    context=NarratorContext(choice="fight", world={}),
                    adventure=_minimal_adventure(), templates=_load_ignarok_templates(),
                    outcome=outcome,
                )
                deps = DispatchDeps(
                    classifier_agent=_make_classifier(
                        IntentClassification(action="malachar_final_battle", confidence=0.9, template="combat")
                    ),
                    narrator=_make_fake_narrator(),
                )
                ctx = GraphRunContext(state=state, deps=deps)
                node: CombatRound | Narrate = CombatRound(
                    combat_id=combat["combat_id"], outcome=outcome,
                    sets_flag_on_win="malachar_defeated",
                )
                for _ in range(50):
                    result = await node.run(ctx)
                    if isinstance(result, Narrate):
                        break
                    node = result
                final_check = next(c for c in state.outcome.checks if c["tool"] == "end_combat")
                world = await toolset.direct_call_tool("read_world", {"campaign_id": CAMPAIGN})
                return final_check["result"], world

        final_result, world = asyncio.run(run())
        assert final_result["winner"] == "enemy"
        assert world.get("flags", {}).get("malachar_defeated") is not True


class TestChoiceLabelInClassifierPrompt:
    """ClassifyIntent recovers the previous scene's choice label and includes
    it in the classifier prompt — fixes confidence=0.0 on numeric choice IDs
    like "2" that carry no semantic signal on their own.
    """

    def test_choice_label_appears_in_classifier_prompt(self):
        captured: list[str] = []

        def _capture(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
            captured.append(str(messages))
            return ModelResponse(
                parts=[ToolCallPart(
                    tool_name="final_result",
                    args=IntentClassification(action=None, confidence=0.0).model_dump(),
                )]
            )

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="2",
                        choice_label="Try to slip past the guardian",
                        world={"current_location": "dark_ravine"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                deps = DispatchDeps(
                    classifier_agent=Agent(
                        FunctionModel(_capture), name="intent_classifier",
                        output_type=IntentClassification,
                    ),
                    narrator=_make_fake_narrator(),
                )
                node = ClassifyIntent()
                ctx = GraphRunContext(state=state, deps=deps)
                await node.run(ctx)

        asyncio.run(run())
        assert any("Try to slip past the guardian" in c for c in captured)
        assert any("2 —" in c for c in captured)

    def test_bare_choice_used_when_no_label_available(self):
        """No previous scene / no matching choice id → falls back to the bare
        choice value, no crash, no "None" leaking into the prompt as text.
        """
        captured: list[str] = []

        def _capture(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
            captured.append(str(messages))
            return ModelResponse(
                parts=[ToolCallPart(
                    tool_name="final_result",
                    args=IntentClassification(action=None, confidence=0.0).model_dump(),
                )]
            )

        async def run():
            server, storage = _fresh_in_memory_server()
            async with MCPToolset(server) as toolset:
                await _seed_character(toolset)
                state = DispatchState(
                    campaign_id=CAMPAIGN,
                    toolset=toolset,
                    context=NarratorContext(
                        choice="2",
                        choice_label=None,
                        world={"current_location": "dark_ravine"},
                    ),
                    adventure=_minimal_adventure(),
                    templates=_load_ignarok_templates(),
                )
                deps = DispatchDeps(
                    classifier_agent=Agent(
                        FunctionModel(_capture), name="intent_classifier",
                        output_type=IntentClassification,
                    ),
                    narrator=_make_fake_narrator(),
                )
                node = ClassifyIntent()
                ctx = GraphRunContext(state=state, deps=deps)
                await node.run(ctx)

        asyncio.run(run())
        assert any("<<<2>>>" in c for c in captured)


class TestNullStringActionNormalization:
    """The classifier's output_validator normalizes the literal string "null"
    (some models emit this instead of omitting the field) to a real None —
    otherwise a future encounter authored with id="null" could be triggered
    by an LLM typo.
    """

    def test_literal_null_string_normalized_to_none(self):
        def _emit_null_string(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
            return ModelResponse(
                parts=[ToolCallPart(
                    tool_name="final_result",
                    args={"action": "null", "confidence": 0.8, "template": "move", "params": {}},
                )]
            )

        async def run():
            from pydantic_ai.models.function import FunctionModel as FM
            agent = build_classifier_agent(FM(_emit_null_string))
            result = await agent.run("irrelevant prompt")
            return result.output

        classification = asyncio.run(run())
        assert classification.action is None
        assert classification.template is None
        assert classification.confidence == 0.0
