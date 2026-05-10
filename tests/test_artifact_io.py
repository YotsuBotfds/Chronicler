"""Tests for strict, atomic validation artifact IO helpers."""
from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path

import pytest


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


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


def test_atomic_write_text_uses_umask_permissions_for_new_artifacts(tmp_path):
    from chronicler import artifact_io

    target = tmp_path / "artifact.txt"
    old_umask = os.umask(0o027)
    try:
        artifact_io.atomic_write_text(target, "content")
    finally:
        os.umask(old_umask)

    assert _mode(target) == 0o640


def test_atomic_write_text_does_not_mutate_process_umask(monkeypatch, tmp_path):
    from chronicler import artifact_io

    def forbidden_umask(mask):  # pragma: no cover - should not be called
        raise AssertionError("atomic writes must not mutate process-global umask")

    monkeypatch.setattr(artifact_io.os, "umask", forbidden_umask, raising=False)

    artifact_io.atomic_write_text(tmp_path / "artifact.txt", "content")


def test_atomic_write_text_preserves_existing_target_permissions(tmp_path):
    from chronicler import artifact_io

    target = tmp_path / "artifact.txt"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o640)

    artifact_io.atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert _mode(target) == 0o640


def test_atomic_write_text_applies_existing_private_mode_before_writing(monkeypatch, tmp_path):
    from chronicler import artifact_io

    target = tmp_path / "artifact.txt"
    target.write_text("old-secret", encoding="utf-8")
    target.chmod(0o600)
    original_set_mode = artifact_io._set_open_file_mode
    observed: dict[str, object] = {}

    def recording_set_mode(file_descriptor, temp_path, mode):
        observed["mode_before_set"] = _mode(temp_path)
        observed["content_before_set"] = Path(temp_path).read_text(encoding="utf-8")
        original_set_mode(file_descriptor, temp_path, mode)
        observed["mode_after_set"] = _mode(temp_path)
        observed["content_after_set"] = Path(temp_path).read_text(encoding="utf-8")

    monkeypatch.setattr(artifact_io, "_set_open_file_mode", recording_set_mode)
    old_umask = os.umask(0o022)
    try:
        artifact_io.atomic_write_text(target, "new-secret")
    finally:
        os.umask(old_umask)

    assert observed == {
        "mode_before_set": 0o600,
        "content_before_set": "",
        "mode_after_set": 0o600,
        "content_after_set": "",
    }
    assert target.read_text(encoding="utf-8") == "new-secret"
    assert _mode(target) == 0o600


def test_atomic_write_text_replaces_symlink_without_exposing_private_target_mode(tmp_path):
    from chronicler import artifact_io

    private_target = tmp_path / "private-target.txt"
    private_target.write_text("private-target", encoding="utf-8")
    private_target.chmod(0o600)
    symlink_path = tmp_path / "artifact-link.txt"
    symlink_path.symlink_to(private_target)

    old_umask = os.umask(0o022)
    try:
        artifact_io.atomic_write_text(symlink_path, "replacement")
    finally:
        os.umask(old_umask)

    assert not symlink_path.is_symlink()
    assert symlink_path.read_text(encoding="utf-8") == "replacement"
    assert _mode(symlink_path) == 0o600
    assert private_target.read_text(encoding="utf-8") == "private-target"
    assert _mode(private_target) == 0o600


def test_atomic_write_text_fsyncs_parent_directory_after_replace(monkeypatch, tmp_path):
    from chronicler import artifact_io

    target = tmp_path / "artifact.txt"
    original_open = os.open
    original_close = os.close
    original_fsync = os.fsync
    parent_dir_fds: set[int] = set()
    fsynced_fds: set[int] = set()
    closed_fds: set[int] = set()

    def recording_open(path, flags, *args):
        fd = original_open(path, flags, *args)
        if Path(path) == target.parent:
            parent_dir_fds.add(fd)
        return fd

    def recording_fsync(fd):
        fsynced_fds.add(fd)
        return original_fsync(fd)

    def recording_close(fd):
        closed_fds.add(fd)
        return original_close(fd)

    monkeypatch.setattr(artifact_io.os, "open", recording_open)
    monkeypatch.setattr(artifact_io.os, "fsync", recording_fsync)
    monkeypatch.setattr(artifact_io.os, "close", recording_close)

    artifact_io.atomic_write_text(target, "durable")

    assert parent_dir_fds
    assert parent_dir_fds <= fsynced_fds
    assert parent_dir_fds <= closed_fds


def test_atomic_write_text_treats_unsupported_parent_directory_fsync_as_best_effort(monkeypatch, tmp_path):
    from chronicler import artifact_io

    target = tmp_path / "artifact.txt"
    original_open = os.open

    def open_with_unsupported_directory_fsync(path, flags, *args):
        if Path(path) == target.parent:
            raise PermissionError(errno.EACCES, "directory fsync unsupported")
        return original_open(path, flags, *args)

    monkeypatch.setattr(artifact_io.os, "open", open_with_unsupported_directory_fsync)

    artifact_io.atomic_write_text(target, "content")

    assert target.read_text(encoding="utf-8") == "content"


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
