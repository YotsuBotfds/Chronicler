"""Pure file guards: the reader must not overwrite or escape its evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/read_scientific_publication_native_proof.py"
SPEC = importlib.util.spec_from_file_location("native_proof_reader_under_test", SCRIPT)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)


@pytest.fixture
def evidence(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "data.bin").write_bytes(b"retained evidence")
    report = {"files": {"data.bin": READER.sha(root / "data.bin")}}
    (root / "report.json").write_text(json.dumps(report))
    return root, tmp_path / "new-readout.json"


def test_success_creates_only_new_external_output_and_keeps_inputs(evidence):
    root, destination = evidence
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    inputs = READER.EvidenceInputs(root, destination)
    assert inputs.input("data.bin") == root / "data.bin"
    inputs.write_result({"observed": 7})
    assert json.loads(destination.read_text()) == {"observed": 7}
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before


@pytest.mark.parametrize("name", ["report.json", "checkpoint_turn_3.ckpt", "worker-identity.json", "new.json"])
def test_any_output_inside_evidence_is_rejected_before_analysis(evidence, monkeypatch, name):
    root, _ = evidence
    before = (root / "report.json").read_bytes()
    def forbidden(*args):
        raise AssertionError("no checkpoint should be read")
    monkeypatch.setattr(READER, "read_checkpoint", forbidden)
    with pytest.raises((ValueError, FileExistsError)):
        READER.main(root, root / name)
    assert (root / "report.json").read_bytes() == before
    if name != "report.json":
        assert not (root / name).exists()


@pytest.mark.parametrize("kind", ["ordinary", "hardlink", "symlink", "dangling"])
def test_existing_destination_and_aliases_never_overwrite(evidence, kind):
    root, destination = evidence
    target = root / "data.bin"
    if kind == "ordinary":
        destination.write_bytes(b"other existing output")
    elif kind == "hardlink":
        os.link(target, destination)
    else:
        destination.symlink_to(target if kind == "symlink" else root / "missing")
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        READER.EvidenceInputs(root, destination)
    assert target.read_bytes() == before


def test_destination_parent_alias_into_evidence_is_rejected(evidence):
    root, destination = evidence
    alias = destination.parent / "parent-alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="outside evidence"):
        READER.EvidenceInputs(root, alias / "new.json")
    assert not (root / "new.json").exists()


@pytest.mark.parametrize("name", ["../outside.bin", "/absolute.bin", "C:/absolute.bin", "..\\outside.bin", ".", "a/../data.bin"])
def test_unsafe_inventory_paths_are_rejected_before_output(evidence, name):
    root, destination = evidence
    outside = destination.parent / "outside.bin"
    outside.write_bytes(b"private outside content")
    (root / "report.json").write_text(json.dumps({"files": {name: hashlib.sha256(outside.read_bytes()).hexdigest()}}))
    with pytest.raises(ValueError, match="relative file paths"):
        READER.EvidenceInputs(root, destination)
    assert outside.read_bytes() == b"private outside content" and not destination.exists()


@pytest.mark.parametrize("parent_link", [False, True])
def test_inventory_symlink_escape_is_rejected(evidence, parent_link):
    root, destination = evidence
    outside = destination.parent / "outside.bin"
    outside.write_bytes(b"outside")
    if parent_link:
        (root / "escape").symlink_to(outside.parent, target_is_directory=True)
        name = "escape/outside.bin"
    else:
        (root / "escape").symlink_to(outside)
        name = "escape"
    (root / "report.json").write_text(json.dumps({"files": {name: READER.sha(outside)}}))
    with pytest.raises(ValueError, match="escapes evidence"):
        READER.EvidenceInputs(root, destination)
    assert not destination.exists()


def test_report_itself_cannot_be_a_symlink_outside_root(evidence):
    root, destination = evidence
    report = root / "report.json"
    outside = destination.parent / "external-report.json"
    report.rename(outside)
    report.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes evidence"):
        READER.EvidenceInputs(root, destination)
    assert not destination.exists()


@pytest.mark.parametrize("kind", ["missing", "mismatched", "unrecorded", "oversized", "too_many"])
def test_missing_changed_unrecorded_and_unbounded_inputs_fail_closed(evidence, monkeypatch, kind):
    root, destination = evidence
    if kind == "missing":
        (root / "data.bin").unlink()
    elif kind == "mismatched":
        (root / "data.bin").write_bytes(b"changed")
    elif kind == "oversized":
        monkeypatch.setattr(READER, "MAX_FILE_BYTES", 1)
    elif kind == "too_many":
        monkeypatch.setattr(READER, "MAX_FILES", 0)
    with pytest.raises((ValueError, FileNotFoundError)):
        inputs = READER.EvidenceInputs(root, destination)
        inputs.input("not-recorded.bin")
    assert not destination.exists()


@pytest.mark.parametrize("changed", ["data.bin", "report.json"])
def test_input_hashes_are_rechecked_before_any_output(evidence, changed):
    root, destination = evidence
    inputs = READER.EvidenceInputs(root, destination)
    (root / changed).write_bytes(b"changed after initial verification")
    with pytest.raises(ValueError, match="changed"):
        inputs.write_result({"observed": 7})
    assert not destination.exists()


def test_exclusive_creation_rejects_hardlink_appearing_after_validation(evidence, monkeypatch):
    root, destination = evidence
    inputs = READER.EvidenceInputs(root, destination)
    original = inputs._destination
    def race(candidate):
        path = original(candidate)
        os.link(root / "data.bin", path)
        return path
    monkeypatch.setattr(inputs, "_destination", race)
    with pytest.raises(FileExistsError):
        inputs.write_result({"must_not_overwrite": True})
    assert destination.read_bytes() == (root / "data.bin").read_bytes() == b"retained evidence"
