"""Filesystem boundaries shared by the memory and world-state save methods."""

from dataclasses import asdict
import json
import os
from pathlib import Path

import pytest

from chronicler.memory import MemoryStream
from chronicler.models import WorldState


@pytest.fixture(params=("memory", "world"))
def save_case(request, sample_world):
    if request.param == "memory":
        stream = MemoryStream("Kethani")
        stream.add("First event", turn=1, importance=5)
        return request.param, stream
    sample_world.turn = 1
    return request.param, sample_world


def _expected_bytes(kind, value) -> bytes:
    if kind == "world":
        text = value.model_dump_json(indent=2)
        return text.replace("\n", os.linesep).encode("utf-8")
    data = {
        "civilization_name": value.civilization_name,
        "entries": [asdict(entry) for entry in value.entries],
        "reflections": [asdict(entry) for entry in value.reflections],
    }
    # Path.write_text(newline=None) translates formatting newlines on Windows.
    # json.dumps defaults to ensure_ascii=True, so the default text encoding
    # used by MemoryStream.save produces the same bytes for this payload.
    text = json.dumps(data, indent=2)
    return text.replace("\n", os.linesep).encode("ascii")


def test_save_creates_nested_parent_and_overwrites_exact_bytes(save_case, tmp_path):
    kind, value = save_case
    path = tmp_path / "new" / "nested" / f"{kind}.json"

    value.save(path)
    first_bytes = path.read_bytes()
    assert first_bytes == _expected_bytes(kind, value)

    if kind == "memory":
        value.add("Second event", turn=2, importance=6)
    else:
        value.turn = 2
    value.save(path)

    second_bytes = path.read_bytes()
    assert second_bytes == _expected_bytes(kind, value)
    assert second_bytes != first_bytes
    if kind == "memory":
        assert len(MemoryStream.load(path).entries) == 2
    else:
        assert WorldState.load(path).turn == 2


def test_save_rejects_parent_file_without_modifying_it(save_case, tmp_path):
    kind, value = save_case
    parent = tmp_path / "parent-is-file"
    parent.write_bytes(b"preserve this file")

    with pytest.raises(OSError):
        value.save(parent / f"{kind}.json")

    assert parent.read_bytes() == b"preserve this file"


def test_save_probe_oserror_falls_back_to_mkdir(save_case, tmp_path, monkeypatch):
    kind, value = save_case
    parent = tmp_path / "new" / "nested"
    path = parent / f"{kind}.json"
    original_is_dir = Path.is_dir
    failed_probes = 0

    def fail_first_probe(self, *args, **kwargs):
        nonlocal failed_probes
        if self == parent and failed_probes == 0:
            failed_probes += 1
            raise PermissionError("simulated Path.is_dir failure")
        return original_is_dir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_dir", fail_first_probe)
    value.save(path)

    assert failed_probes == 1
    assert path.read_bytes() == _expected_bytes(kind, value)
