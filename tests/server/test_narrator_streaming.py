"""Streaming narrator unit tests (issue #20).

Covers the two ``StreamingNarratorBackend`` implementations directly (no
HTTP layer — that's ``test_turn_streaming.py``):

* ``PydanticNarrator.narrate_stream`` — pydantic-ai's structured-output
  streaming (``run_stream`` + ``stream_output``, partial ``trailing-strings``
  validation) against the real ``Scene`` model, including its
  ``narrative_not_empty`` field validator.
* ``DispatcherNarrator.narrate_stream`` — the queue-bridge
  (``_StreamingNarratorProxy``) that lets ``dispatcher_graph.run()`` be reused
  unmodified (``ClassifyIntent``/``MechanicalDispatch``/``CombatRound``) while
  only the terminal ``Narrate`` node's LLM call streams: correctness, failure
  propagation (no hang), and cancellation cleanup (no leaked background task).

``FunctionModel``'s local async generators complete faster than real network
token delivery, so these tests assert *correctness* (delta concatenation
equals the final narrative, choices intact) rather than an exact delta count —
a real provider will show more granular deltas; the streaming plumbing itself
doesn't care how many there are.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gamebook_web.harness.agent import PydanticNarrator
from gamebook_web.harness.dispatch_types import DispatchDeps, build_classifier_agent
from gamebook_web.harness.graph import DispatcherNarrator, _LAYER3_ONLY
from gamebook_web.harness.narrator import NarratorContext, StreamingNarratorBackend
from gamebook_web.harness.scene import Scene

SCENE_JSON_CHUNKS = [
    '{"narrative": "You step',
    ' into the misty pass',
    '. The wind howls',
    ' around jagged stones.",',
    ' "choices": [{"id": "1",',
    ' "label": "Press on"},',
    ' {"id": "2", "label": "Retreat"}],',
    ' "terminal": false}',
]


async def _staggered_scene_stream(messages: list[ModelMessage], info: AgentInfo):
    """Deltas with real inter-chunk latency (asyncio.sleep) — without it,
    pydantic-ai's local FunctionModel run completes before the consumer ever
    starts iterating, collapsing to a single yield regardless of chunking."""
    for chunk in SCENE_JSON_CHUNKS:
        await asyncio.sleep(0.01)
        yield chunk


# ---------------------------------------------------------------------------
# PydanticNarrator.narrate_stream
# ---------------------------------------------------------------------------

class TestPydanticNarratorStream:
    def test_satisfies_streaming_protocol(self):
        narrator = PydanticNarrator(model=FunctionModel(stream_function=_staggered_scene_stream))
        assert isinstance(narrator, StreamingNarratorBackend)

    @pytest.mark.asyncio
    async def test_deltas_concatenate_to_final_narrative(self):
        narrator = PydanticNarrator(model=FunctionModel(stream_function=_staggered_scene_stream))
        ctx = NarratorContext(character={"name": "Aldric"}, world={"current_location": "gate"})

        deltas: list[str] = []
        final: Scene | None = None
        async for event in narrator.narrate_stream("camp-1", ctx):
            if isinstance(event, Scene):
                final = event
            else:
                deltas.append(event)

        assert final is not None
        assert "".join(deltas) == final.narrative
        assert final.narrative == "You step into the misty pass. The wind howls around jagged stones."

    @pytest.mark.asyncio
    async def test_final_item_carries_choices_and_passes_output_validator(self):
        """The last stream_output() item is strictly validated (allow_partial=
        False) — same output_validator as narrate(), so a structurally invalid
        scene would ModelRetry/raise here exactly as it does non-streamed."""
        narrator = PydanticNarrator(model=FunctionModel(stream_function=_staggered_scene_stream))
        ctx = NarratorContext(character=None, world={})

        final: Scene | None = None
        async for event in narrator.narrate_stream("camp-2", ctx):
            if isinstance(event, Scene):
                final = event

        assert final is not None
        assert len(final.choices) == 2
        assert final.terminal is False

    @pytest.mark.asyncio
    async def test_stream_and_non_stream_agree_on_final_scene(self):
        """narrate() and narrate_stream() must produce the same Scene for the
        same (deterministic) model output — streaming is an observation
        mechanism, not a different code path for what gets returned."""
        ctx = NarratorContext(character=None, world={})

        streamed = PydanticNarrator(model=FunctionModel(stream_function=_staggered_scene_stream))
        final: Scene | None = None
        async for event in streamed.narrate_stream("camp-3", ctx):
            if isinstance(event, Scene):
                final = event

        async def non_streaming(messages: list[ModelMessage], info: AgentInfo):
            from pydantic_ai.messages import ModelResponse, TextPart
            return ModelResponse(parts=[TextPart(content="".join(SCENE_JSON_CHUNKS))])

        plain = PydanticNarrator(model=FunctionModel(non_streaming))
        direct = await plain.narrate("camp-3", ctx)

        assert final is not None
        assert final.narrative == direct.narrative
        assert final.choices == direct.choices


# ---------------------------------------------------------------------------
# DispatcherNarrator.narrate_stream — queue-bridge over dispatcher_graph
# ---------------------------------------------------------------------------

def _make_dispatcher_narrator(model: FunctionModel) -> DispatcherNarrator:
    """Construct a DispatcherNarrator without touching disk (no adventure_dir),
    matching the ADR-033 "fully-Layer-3" fallback the class itself documents."""
    narrator = DispatcherNarrator.__new__(DispatcherNarrator)
    narrator._toolset = None
    narrator._adventure = _LAYER3_ONLY
    narrator._templates = {}
    narrator._deps = DispatchDeps(
        classifier_agent=build_classifier_agent(model),
        narrator=PydanticNarrator(model=model),
    )
    return narrator


class TestDispatcherNarratorStream:
    def test_satisfies_streaming_protocol(self):
        narrator = _make_dispatcher_narrator(FunctionModel(stream_function=_staggered_scene_stream))
        assert isinstance(narrator, StreamingNarratorBackend)

    @pytest.mark.asyncio
    async def test_session_open_bridges_through_to_narrate(self):
        """choice=None skips ClassifyIntent (session-open path, graph.py's own
        documented behavior) and goes straight to Narrate — the simplest path
        through the queue bridge, with zero mechanical dispatch involved."""
        narrator = _make_dispatcher_narrator(FunctionModel(stream_function=_staggered_scene_stream))
        ctx = NarratorContext(character=None, world={}, choice=None)

        deltas: list[str] = []
        final: Scene | None = None
        async for event in narrator.narrate_stream("camp-4", ctx):
            if isinstance(event, Scene):
                final = event
            else:
                deltas.append(event)

        assert final is not None
        assert "".join(deltas) == final.narrative
        assert len(final.choices) == 2

    @pytest.mark.asyncio
    async def test_failure_before_narrate_propagates_not_hangs(self):
        """A classifier failure (before the graph ever reaches Narrate) must
        raise through narrate_stream(), not leave the consumer awaiting a
        queue item that will never arrive."""
        async def boom_stream(messages: list[ModelMessage], info: AgentInfo):
            raise RuntimeError("simulated classifier failure")
            yield  # pragma: no cover — unreachable, keeps this an async generator

        narrator = _make_dispatcher_narrator(FunctionModel(stream_function=_staggered_scene_stream))
        narrator._deps = DispatchDeps(
            classifier_agent=build_classifier_agent(FunctionModel(stream_function=boom_stream)),
            narrator=narrator._deps.narrator,
        )
        ctx = NarratorContext(character=None, world={"current_location": "gate"}, choice="look around")

        with pytest.raises(Exception):
            async for _event in narrator.narrate_stream("camp-5", ctx):
                pass

    @pytest.mark.asyncio
    async def test_mid_stream_disconnect_cancels_background_task(self):
        """Closing the generator early (what an SSE client disconnect does)
        must not leave the graph's background task running — it would burn
        LLM/MCP calls for an abandoned request."""
        narrator = _make_dispatcher_narrator(FunctionModel(stream_function=_staggered_scene_stream))
        ctx = NarratorContext(character=None, world={}, choice=None)

        gen = narrator.narrate_stream("camp-6", ctx)
        first = await gen.__anext__()
        assert isinstance(first, str)
        await gen.aclose()
        await asyncio.sleep(0.1)

        current = asyncio.current_task()
        leaked = [t for t in asyncio.all_tasks() if not t.done() and t is not current]
        assert not leaked, f"background graph task(s) leaked after aclose(): {leaked}"
