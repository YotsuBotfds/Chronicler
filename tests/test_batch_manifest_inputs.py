"""A verified batch cannot acquire new oracle inputs after it was recorded."""
from copy import deepcopy

import pytest

from chronicler.batch_manifest import (
    VALIDATION_INPUT_FILES,
    file_sha256,
    verify_batch_manifest,
)


@pytest.fixture
def recorded(tmp_path):
    seed = tmp_path / "seed_7"
    seed.mkdir()
    bundle = seed / "chronicle_bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    relative = bundle.relative_to(tmp_path).as_posix()
    manifest = {
        "status": "complete", "turns": 20,
        "runs": [{"seed": 7, "dir": "seed_7", "bundle": relative,
                  "total_turns": 20, "files": {relative: file_sha256(bundle)}}],
    }
    assert verify_batch_manifest(tmp_path, manifest, [bundle]) == []
    return tmp_path, seed, bundle, manifest


@pytest.mark.parametrize("name", [name for name in VALIDATION_INPUT_FILES if name != "chronicle_bundle.json"] + [
    "validation_summary/graph_10.json", "validation_summary/nested/needs_10.json",
])
def test_unrecorded_oracle_input_blocks_verified_status(recorded, name):
    root, seed, bundle, manifest = recorded
    original = deepcopy(manifest)
    added = seed / name
    added.parent.mkdir(parents=True, exist_ok=True)
    added.write_bytes(b"unrecorded oracle data")
    problems = verify_batch_manifest(root, manifest, [bundle])
    assert len(problems) == 1
    assert added.relative_to(root).as_posix() + " (not hashed)" in problems[0]
    assert manifest == original
    added.unlink()
    assert verify_batch_manifest(root, manifest, [bundle]) == []


def test_recorded_sidecar_still_requires_its_exact_bytes(recorded):
    root, seed, bundle, manifest = recorded
    sidecar = seed / "validation_summary.json"
    sidecar.write_bytes(b"recorded oracle data")
    manifest["runs"][0]["files"][sidecar.relative_to(root).as_posix()] = file_sha256(sidecar)
    assert verify_batch_manifest(root, manifest, [bundle]) == []
    sidecar.write_bytes(b"changed oracle data")
    assert "validation_summary.json (changed)" in verify_batch_manifest(root, manifest, [bundle])[0]


def test_unrelated_exports_can_be_added_or_pruned(recorded):
    root, seed, bundle, manifest = recorded
    for name in ("state.json", "chronicle.md", "memories.json", "diagnostics.txt"):
        path = seed / name
        path.write_bytes(b"not an oracle input")
        assert verify_batch_manifest(root, manifest, [bundle]) == []
        path.unlink()
    assert verify_batch_manifest(root, manifest, [bundle]) == []


def test_hash_from_another_run_does_not_record_this_runs_added_input(recorded):
    root, seed, bundle, manifest = recorded
    sidecar = seed / "validation_summary.json"
    sidecar.write_bytes(b"same bytes in separate seeds")
    manifest["runs"][0]["files"]["seed_8/validation_summary.json"] = file_sha256(sidecar)
    other = root / "seed_8"
    other.mkdir()
    (other / "validation_summary.json").write_bytes(sidecar.read_bytes())
    assert "seed_7/validation_summary.json (not hashed)" in verify_batch_manifest(root, manifest, [bundle])[0]
