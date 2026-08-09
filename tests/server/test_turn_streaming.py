"""SSE streaming turn endpoint tests (issue #20).

``POST /me/game/turn/stream`` mirrors ``POST /me/game/turn`` exactly in its
pre/post-narration engine work (``_read_turn_context``/``_finalize_turn``) —
these tests confirm the SSE framing (``delta``/``done``/``error`` events), the
graceful-degradation fallback for narrators without streaming support, and
that the final ``done`` payload matches what the non-streaming endpoint
returns for equivalent input.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import pytest

from gamebook_web.harness.narrator import NarratorContext
from gamebook_web.harness.scene import Choice, Scene

AUTH = {"Authorization": "Bearer dev-token"}


def _create_game(client) -> str:
    resp = client.post("/me/game", headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()["campaign_id"]


def _create_character(client, name: str = "TestHero") -> dict:
    resp = client.post("/me/game/character", json={"name": name}, headers=AUTH)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse ``event: X\\ndata: Y\\n\\n`` blocks into ``[(event, data), ...]``."""
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event_line, data_line = block.split("\n", 1)
        assert event_line.startswith("event: ")
        assert data_line.startswith("data: ")
        events.append((event_line[len("event: "):], json.loads(data_line[len("data: "):])))
    return events


# ---------------------------------------------------------------------------
# Happy path — FakeNarrator satisfies StreamingNarratorBackend
# ---------------------------------------------------------------------------

def test_stream_emits_delta_then_done(api_client):
    _create_game(api_client)
    _create_character(api_client)

    resp = api_client.post("/me/game/turn/stream", json={"choice": "look around"}, headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert [e for e, _ in events].count("done") == 1
    kinds = [e for e, _ in events]
    assert kinds[-1] == "done"
    assert all(k == "delta" for k in kinds[:-1])

    done_data = events[-1][1]
    assert "scene" in done_data and "status" in done_data
    assert done_data["scene"]["narrative"]
    assert done_data["scene"]["choices"]


def test_stream_delta_text_concatenates_to_final_narrative(api_client):
    scene = Scene(
        narrative="You round the bend and see a stone archway ahead.",
        choices=[Choice(id="1", label="Approach"), Choice(id="2", label="Circle around")],
    )
    from gamebook_web.harness.narrator import FakeNarrator
    from gamebook_web.api.app import app

    app.state.narrator = FakeNarrator(scenes=[scene])
    _create_game(api_client)
    _create_character(api_client)

    resp = api_client.post("/me/game/turn/stream", json={"choice": "advance"}, headers=AUTH)
    events = _parse_sse(resp.text)
    deltas = "".join(d["text"] for e, d in events if e == "delta")
    done = next(d for e, d in events if e == "done")

    assert deltas == scene.narrative
    assert done["scene"]["narrative"] == scene.narrative


def test_stream_done_payload_matches_non_streaming_endpoint(api_client, fake_narrator):
    """Same narrator, same setup, same choice → same TurnResponse shape."""
    scene = Scene(narrative="A fixed scene for parity checking.", choices=[Choice(id="1", label="Go")])
    fake_narrator._queue = [scene]

    _create_game(api_client)
    _create_character(api_client)

    stream_resp = api_client.post("/me/game/turn/stream", json={"choice": "go"}, headers=AUTH)
    events = _parse_sse(stream_resp.text)
    done = next(d for e, d in events if e == "done")

    # Fresh game+character with the same next queued scene, taken via the
    # plain endpoint, should produce an equivalent response shape.
    fake_narrator._queue = [scene]
    plain_resp = api_client.post("/me/game/turn", json={"choice": "go"}, headers=AUTH)
    assert plain_resp.status_code == 200
    plain = plain_resp.json()

    assert done["scene"]["narrative"] == plain["scene"]["narrative"]
    assert done["scene"]["choices"] == plain["scene"]["choices"]
    assert done["status"] == plain["status"]


# ---------------------------------------------------------------------------
# Graceful degradation — narrator without StreamingNarratorBackend
# ---------------------------------------------------------------------------

class _NonStreamingNarrator:
    """Implements only ``narrate()`` — no ``narrate_stream`` at all."""

    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:
        return Scene(narrative="Plain narration, no streaming support.", choices=[Choice(id="1", label="Continue")])


def test_stream_falls_back_to_single_chunk_for_non_streaming_narrator(api_client):
    from gamebook_web.api.app import app

    app.state.narrator = _NonStreamingNarrator()
    _create_game(api_client)
    _create_character(api_client)

    resp = api_client.post("/me/game/turn/stream", json={"choice": "look"}, headers=AUTH)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    assert [e for e, _ in events].count("done") == 1
    done = next(d for e, d in events if e == "done")
    assert done["scene"]["narrative"] == "Plain narration, no streaming support."


# ---------------------------------------------------------------------------
# Error path — never an unhandled 500 mid-stream
# ---------------------------------------------------------------------------

class _FailingNarrator:
    async def narrate(self, campaign_id: str, context: NarratorContext) -> Scene:
        raise RuntimeError("boom")

    async def narrate_stream(
        self, campaign_id: str, context: NarratorContext
    ) -> AsyncIterator[str | Scene]:
        yield "partial text before the failure"
        raise RuntimeError("boom")
        yield  # pragma: no cover — unreachable, keeps this an async generator


def test_stream_emits_error_event_on_narrator_failure(api_client):
    from gamebook_web.api.app import app

    app.state.narrator = _FailingNarrator()
    _create_game(api_client)
    _create_character(api_client)

    resp = api_client.post("/me/game/turn/stream", json={"choice": "look"}, headers=AUTH)
    assert resp.status_code == 200  # headers already committed — error travels inside the stream
    events = _parse_sse(resp.text)

    assert events, "expected at least the error event"
    last_event, last_data = events[-1]
    assert last_event == "error"
    assert last_data["error"]["code"] == "stream_failed"
    assert "done" not in [e for e, _ in events]


# ---------------------------------------------------------------------------
# Lease / rate-limit wiring parity with the non-streaming endpoint
# ---------------------------------------------------------------------------

def test_stream_requires_active_campaign(api_client):
    resp = api_client.post("/me/game/turn/stream", json={"choice": "go"}, headers=AUTH)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "no_active_campaign"


def test_stream_after_delete_game_is_404_same_as_plain_endpoint(api_client):
    """Ended campaigns are no longer the account's *active* one (registry
    filters on status="active"), so both endpoints 404 with no_active_campaign
    rather than reaching the run_ended/409 guard — pre-existing behavior,
    unchanged by the streaming route; asserted here for parity."""
    _create_game(api_client)
    _create_character(api_client)
    api_client.delete("/me/game", headers=AUTH)

    stream_resp = api_client.post("/me/game/turn/stream", json={"choice": "go"}, headers=AUTH)
    plain_resp = api_client.post("/me/game/turn", json={"choice": "go"}, headers=AUTH)
    assert stream_resp.status_code == plain_resp.status_code == 404
    assert stream_resp.json()["error"]["code"] == plain_resp.json()["error"]["code"] == "no_active_campaign"
