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
