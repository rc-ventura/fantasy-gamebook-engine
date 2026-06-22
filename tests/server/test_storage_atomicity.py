"""Atomic-write safety for ``JSONStorage``.

These tests are JSON-specific: they assert that the temp-file + ``os.replace``
strategy never leaves a half-written or corrupted file behind, and that a
failed rename preserves the previously committed state.
"""

from __future__ import annotations

import pytest

from gamebook.storage import json_storage as json_storage_module


def _temp_leftovers(estado_dir) -> list[str]:
    return [p.name for p in estado_dir.iterdir() if p.name.endswith(".tmp")]


def test_save_leaves_no_temp_files(json_storage, sample_character, tmp_path) -> None:
    json_storage.save_character(sample_character)
    estado = tmp_path / "estado"
    assert (estado / "character.json").is_file()
    assert _temp_leftovers(estado) == []


def test_replace_failure_preserves_previous_state(
    json_storage, sample_character, monkeypatch, tmp_path
) -> None:
    # Establish a known-good committed state.
    json_storage.save_character(sample_character)
    assert json_storage.load_character() == sample_character

    def boom(src, dst):  # pragma: no cover - trivial stub
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(json_storage_module.os, "replace", boom)

    newer = sample_character.model_copy(update={"gold": 999})
    with pytest.raises(OSError):
        json_storage.save_character(newer)

    monkeypatch.undo()

    # Previous state intact and still loadable; no temp file left behind.
    estado = tmp_path / "estado"
    assert json_storage.load_character() == sample_character
    assert _temp_leftovers(estado) == []


def test_append_event_replace_failure_preserves_events(
    json_storage, sample_events, monkeypatch, tmp_path
) -> None:
    for event in sample_events:
        json_storage.append_event(event)
    assert json_storage.load_events() == sample_events

    def boom(src, dst):  # pragma: no cover - trivial stub
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(json_storage_module.os, "replace", boom)

    extra = sample_events[0].model_copy(update={"turn": 77})
    with pytest.raises(OSError):
        json_storage.append_event(extra)

    monkeypatch.undo()

    estado = tmp_path / "estado"
    assert json_storage.load_events() == sample_events
    assert _temp_leftovers(estado) == []
