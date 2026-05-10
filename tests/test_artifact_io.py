"""Tests for strict, atomic validation artifact IO helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def test_strict_json_loads_rejects_nonfinite_constants():
    from chronicler.artifact_io import ArtifactIOError, strict_json_loads

    for constant in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ArtifactIOError, match="non-finite JSON constant"):
            strict_json_loads(f'{{"results": {constant}}}', label="report")


def test_strict_json_loads_rejects_duplicate_keys():
    from chronicler.artifact_io import ArtifactIOError, strict_json_loads

    text = '{"results": {"needs": {"status": "FAIL"}, "needs": {"status": "PASS"}}}'

    with pytest.raises(ArtifactIOError, match="duplicate JSON key: needs"):
        strict_json_loads(text, label="report")


def test_strict_json_dumps_rejects_nonfinite_without_partial_output():
    from chronicler.artifact_io import ArtifactIOError, strict_json_dumps

    with pytest.raises(ArtifactIOError, match="could not serialize JSON"):
        strict_json_dumps({"metric": float("nan")})


def test_strict_json_dumps_rejects_keys_that_would_duplicate_after_json_coercion():
    from chronicler.artifact_io import ArtifactIOError, strict_json_dumps

    for payload, expected_path in (
        ({1: "int", "1": "str"}, "<root>"),
        ({None: "none", "null": "str"}, "<root>"),
        ({"outer": {1: "int", "1": "str"}}, "outer"),
    ):
        with pytest.raises(ArtifactIOError, match="JSON object keys must be strings") as exc_info:
            strict_json_dumps(payload)
        assert expected_path in str(exc_info.value)


def test_atomic_write_json_rejects_coercion_duplicate_keys_before_touching_target(monkeypatch, tmp_path):
    from chronicler import artifact_io
    from chronicler.artifact_io import ArtifactIOError

    target = tmp_path / "artifact.json"
    target.write_text('{"old": true}', encoding="utf-8")
    replace_called = False

    def recording_replace(src, dst):  # pragma: no cover - should not be reached
        nonlocal replace_called
        replace_called = True
        raise AssertionError("replace should not be called after key validation failure")

    monkeypatch.setattr(artifact_io.os, "replace", recording_replace)

    with pytest.raises(ArtifactIOError, match="JSON object keys must be strings"):
        artifact_io.atomic_write_json(target, {1: "int", "1": "str"})

    assert replace_called is False
    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_text_replaces_from_same_directory(monkeypatch, tmp_path):
    from chronicler import artifact_io

    target = tmp_path / "nested" / "artifact.txt"
    original_replace = os.replace
    calls: list[tuple[Path, Path]] = []

    def recording_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(artifact_io.os, "replace", recording_replace)

    artifact_io.atomic_write_text(target, "complete\n")

    assert target.read_text(encoding="utf-8") == "complete\n"
    assert len(calls) == 1
    temp_path, replaced_path = calls[0]
    assert temp_path.parent == target.parent
    assert replaced_path == target
    assert not temp_path.exists()


def test_atomic_write_text_preserves_existing_target_when_replace_fails(monkeypatch, tmp_path):
    from chronicler import artifact_io
    from chronicler.artifact_io import ArtifactIOError

    target = tmp_path / "artifact.txt"
    target.write_text("old-content", encoding="utf-8")
    temp_paths: list[Path] = []

    def failing_replace(src, dst):
        temp_paths.append(Path(src))
        raise OSError("simulated replace failure")

    monkeypatch.setattr(artifact_io.os, "replace", failing_replace)

    with pytest.raises(ArtifactIOError, match="could not write artifact"):
        artifact_io.atomic_write_text(target, "new-content")

    assert target.read_text(encoding="utf-8") == "old-content"
    assert temp_paths
    assert all(not temp.exists() for temp in temp_paths)


def test_atomic_write_json_serializes_before_touching_target(monkeypatch, tmp_path):
    from chronicler import artifact_io
    from chronicler.artifact_io import ArtifactIOError

    target = tmp_path / "artifact.json"
    target.write_text('{"old": true}', encoding="utf-8")
    replace_called = False

    def recording_replace(src, dst):  # pragma: no cover - should not be reached
        nonlocal replace_called
        replace_called = True
        raise AssertionError("replace should not be called after serialization failure")

    monkeypatch.setattr(artifact_io.os, "replace", recording_replace)

    with pytest.raises(ArtifactIOError, match="could not serialize JSON"):
        artifact_io.atomic_write_json(target, {"bad": float("nan")})

    assert replace_called is False
    assert target.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_json_outputs_strict_parseable_json(tmp_path):
    from chronicler.artifact_io import atomic_write_json, strict_json_loads

    target = tmp_path / "artifact.json"
    atomic_write_json(target, {"ok": True, "items": [1, 2]})

    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {"ok": True, "items": [1, 2]}
    assert strict_json_loads(text, label="artifact") == {"ok": True, "items": [1, 2]}
