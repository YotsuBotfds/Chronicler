"""Synthetic cohorts cannot obtain verified identity from inconsistent facts."""
from copy import deepcopy
import importlib
import json
import os

import pytest

from chronicler.batch_manifest import (
    batch_cohort, file_sha256, verify_batch_manifest,
)
from chronicler.validation_io import ValidationRequestError, check_batch_manifest


def _write_batch(root, seeds=(7, 8), turns=20):
    root.mkdir()
    runs = []
    for index, seed in enumerate(seeds):
        directory = root / f"run_{index}"
        directory.mkdir()
        bundle = directory / "chronicle_bundle.json"
        bundle.write_text(json.dumps({
            "metadata": {"seed": seed, "total_turns": turns, "bundle_version": 4},
            "world_state": {"turn": turns, "agent_mode": "off", "regions": [], "artifacts": []},
            "history": [], "events_timeline": [],
        }), encoding="utf-8")
        relative = bundle.relative_to(root).as_posix()
        runs.append({"seed": seed, "dir": directory.name, "bundle": relative,
                     "total_turns": turns, "files": {relative: file_sha256(bundle)}})
    manifest = {"kind": "chronicler-batch", "schema_version": 1, "status": "complete",
                "seeds": list(seeds), "turns": turns, "simulation": {"turns": turns}, "runs": runs}
    _save(root, manifest)
    return root, manifest


def _save(root, manifest):
    (root / "batch_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _assert_rejected(root, manifest):
    _save(root, manifest)
    original = deepcopy(manifest)
    assert verify_batch_manifest(root, manifest, sorted(root.rglob("chronicle_bundle.json")))
    with pytest.raises(ValidationRequestError):
        check_batch_manifest(root)
    assert manifest == original


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(runs=[None]),
    lambda m: m["runs"].append(None),
    lambda m: m["runs"].append(deepcopy(m["runs"][0])),
    lambda m: m.update(seeds=list(range(200))),
    lambda m: m.update(seeds=[7, 7]),
    lambda m: m.update(seeds=[8, 7]),
    lambda m: m.pop("seeds"),
    lambda m: m.update(seeds=[True, 8]),
    lambda m: m["runs"][0].update(seed=True),
    lambda m: m["runs"][0].update(dir="other"),
    lambda m: m["runs"][0].update(dir="../other"),
    lambda m: m["runs"][0].update(bundle="run_0/./chronicle_bundle.json"),
], ids=["null-run", "extra-null-run", "duplicate-run", "invented-seeds", "duplicate-seed-list",
        "reordered-seeds", "missing-seeds", "boolean-seed-list", "boolean-run-seed",
        "wrong-directory", "parent-directory", "bundle-alias-spelling"])
def test_inconsistent_run_structure_is_rejected(tmp_path, mutation):
    root, manifest = _write_batch(tmp_path / "batch")
    mutation(manifest)
    _assert_rejected(root, manifest)


def test_zero_world_cohort_cannot_claim_two_hundred_five_hundred_turn_runs(tmp_path):
    root, manifest = _write_batch(tmp_path / "batch", seeds=())
    manifest.update(runs=[None], seeds=list(range(200)), turns=500)
    _assert_rejected(root, manifest)


@pytest.mark.parametrize("field", ["turns", "total_turns"])
@pytest.mark.parametrize("value", [None, True, False, "500", 500.0, -1])
def test_horizon_facts_require_nonnegative_nonboolean_integers(tmp_path, field, value):
    root, manifest = _write_batch(tmp_path / "batch")
    (manifest if field == "turns" else manifest["runs"][0])[field] = value
    _assert_rejected(root, manifest)


@pytest.mark.parametrize("field,value", [("seed", 99), ("seed", True), ("total_turns", 19),
                                         ("total_turns", None), ("total_turns", "20")])
def test_hashed_bundle_metadata_must_match_its_recorded_facts(tmp_path, field, value):
    root, manifest = _write_batch(tmp_path / "batch")
    path = root / manifest["runs"][0]["bundle"]
    bundle = json.loads(path.read_text())
    bundle["metadata"][field] = value
    path.write_text(json.dumps(bundle))
    manifest["runs"][0]["files"][manifest["runs"][0]["bundle"]] = file_sha256(path)
    _assert_rejected(root, manifest)


def test_twenty_actual_turns_cannot_claim_five_hundred(tmp_path):
    root, manifest = _write_batch(tmp_path / "batch")
    manifest["turns"] = manifest["simulation"]["turns"] = 500
    for run in manifest["runs"]:
        run["total_turns"] = 500
    _assert_rejected(root, manifest)


def test_terminal_world_turn_must_match_recorded_horizon(tmp_path):
    root, manifest = _write_batch(tmp_path / "batch")
    path = root / manifest["runs"][0]["bundle"]
    bundle = json.loads(path.read_text())
    bundle["world_state"]["turn"] = 19
    path.write_text(json.dumps(bundle))
    manifest["runs"][0]["files"][manifest["runs"][0]["bundle"]] = file_sha256(path)
    _assert_rejected(root, manifest)


@pytest.mark.parametrize("scope", ["parent", "absolute", "other-run"])
def test_recorded_hashes_are_scoped_to_their_own_runs_inputs(tmp_path, scope):
    root, manifest = _write_batch(tmp_path / "batch")
    if scope == "other-run":
        relative = manifest["runs"][1]["bundle"]
        path = root / relative
    else:
        path = tmp_path / "external.json"
        path.write_text("{}")
        relative = "../external.json" if scope == "parent" else str(path)
    manifest["runs"][0]["files"][relative] = file_sha256(path)
    _assert_rejected(root, manifest)


@pytest.mark.parametrize("alias", ["symlink", "hardlink"])
def test_two_determinism_runs_cannot_alias_one_physical_bundle(tmp_path, alias):
    root, manifest = _write_batch(tmp_path / "batch", seeds=(7, 7))
    first, second = [root / run["bundle"] for run in manifest["runs"]]
    second.unlink()
    try:
        second.symlink_to(first) if alias == "symlink" else os.link(first, second)
    except OSError as exc:
        pytest.skip(f"filesystem cannot create {alias}: {exc}")
    _assert_rejected(root, manifest)


def _track_loader(monkeypatch):
    io = importlib.import_module("chronicler.validation_io")
    original = io._load_bundle
    reads = []
    def tracked(path, **kwargs):
        reads.append(path)
        return original(path, **kwargs)
    monkeypatch.setattr(io, "_load_bundle", tracked)
    return reads


@pytest.mark.parametrize("module_name", ["chronicler.validate", "chronicler.validation_io"])
def test_normal_oracle_path_reconciles_at_its_existing_decode_only(tmp_path, monkeypatch, module_name):
    root, manifest = _write_batch(tmp_path / "batch")
    module = importlib.import_module(module_name)
    reads = _track_loader(monkeypatch)
    report = module.run_oracles(root, ["arcs"])
    assert reads == sorted(root.rglob("chronicle_bundle.json"))
    assert report["batch_manifest"] == batch_cohort(manifest, file_sha256(root / "batch_manifest.json"))


@pytest.mark.parametrize("module_name", ["chronicler.validate", "chronicler.validation_io"])
def test_invalid_last_payload_prevents_oracle_invocation_and_verified_report(tmp_path, monkeypatch, module_name):
    root, manifest = _write_batch(tmp_path / "batch", seeds=(7, 7))
    manifest["seeds"][1] = manifest["runs"][1]["seed"] = 8
    _save(root, manifest)
    module = importlib.import_module(module_name)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("invalid cohort reached scientific oracle")
    if module_name == "chronicler.validate":
        monkeypatch.setitem(module.ORACLE_RUNNERS, "arcs", forbidden)
    else:
        monkeypatch.setattr(module, "run_arc_oracle", forbidden)
    with pytest.raises(ValidationRequestError, match="metadata seed"):
        module.run_oracles(root, ["arcs"])
    assert calls == []


@pytest.mark.parametrize("module_name", ["chronicler.validate", "chronicler.validation_io"])
def test_empty_oracle_selection_still_requires_actual_bundle_facts(tmp_path, module_name):
    root, manifest = _write_batch(tmp_path / "batch")
    manifest["runs"][0]["total_turns"] = 500
    _save(root, manifest)
    with pytest.raises(ValidationRequestError, match="metadata total_turns"):
        importlib.import_module(module_name).run_oracles(root, [])


@pytest.mark.parametrize("module_name", ["chronicler.validate", "chronicler.validation_io"])
def test_genuine_repeated_seed_determinism_remains_valid_without_extra_decodes(tmp_path, monkeypatch, module_name):
    root, manifest = _write_batch(tmp_path / "batch", seeds=(42, 42))
    reads = _track_loader(monkeypatch)
    report = importlib.import_module(module_name).run_oracles(root, ["determinism"])
    assert report["results"]["determinism"]["status"] == "PASS"
    assert report["results"]["determinism"]["pairs_checked"] == 1
    assert report["batch_manifest"]["seeds"] == [42, 42]
    # Existing determinism reads each file for its index and its comparison.
    assert len(reads) == 4
    assert verify_batch_manifest(root, manifest, sorted(root.rglob("chronicle_bundle.json"))) == []


def test_legacy_standalone_loader_remains_unchecked(tmp_path):
    root, manifest = _write_batch(tmp_path / "batch")
    (root / "batch_manifest.json").unlink()
    assert check_batch_manifest(root, legacy_batch=True) == {
        "status": "unchecked", "reason": "no batch_manifest.json (--legacy-batch)"}


@pytest.mark.parametrize("module_name", ["chronicler.validate", "chronicler.validation_io"])
@pytest.mark.parametrize("content", ['{"metadata":', '{"metadata":{"seed":7,"seed":8,"total_turns":20}}'])
def test_invalid_json_cannot_escape_as_a_verified_oracle_report(tmp_path, module_name, content):
    root, manifest = _write_batch(tmp_path / "batch", seeds=(7,))
    path = root / manifest["runs"][0]["bundle"]
    path.write_text(content)
    manifest["runs"][0]["files"][manifest["runs"][0]["bundle"]] = file_sha256(path)
    _save(root, manifest)
    with pytest.raises(ValidationRequestError, match="Failed to load bundle"):
        importlib.import_module(module_name).run_oracles(root, ["arcs"])
    assert verify_batch_manifest(root, manifest, [path])


def test_version_six_bundle_uses_the_same_existing_decode(tmp_path, monkeypatch):
    from chronicler.bundle_codec import encode_bundle
    root, manifest = _write_batch(tmp_path / "batch", seeds=(7,))
    path = root / manifest["runs"][0]["bundle"]
    payload = json.loads(path.read_text())
    payload["history"] = [{"turn": 0, "civ_stats": {}}, {"turn": 20, "civ_stats": {}}]
    payload["metadata"]["bundle_version"] = 5
    path.write_text(json.dumps(encode_bundle(payload)))
    manifest["runs"][0]["files"][manifest["runs"][0]["bundle"]] = file_sha256(path)
    _save(root, manifest)
    reads = _track_loader(monkeypatch)
    report = importlib.import_module("chronicler.validate").run_oracles(root, ["arcs"])
    assert report["batch_manifest"]["status"] == "verified"
    assert reads == [path]
    assert verify_batch_manifest(root, manifest, [path]) == []


def test_custom_determinism_runner_keeps_standalone_signature(tmp_path, monkeypatch):
    root, _manifest = _write_batch(tmp_path / "batch", seeds=(42, 42))
    module = importlib.import_module("chronicler.validate")
    calls = []
    def custom(path):
        calls.append(path)
        return {"status": "PASS"}
    monkeypatch.setitem(module.ORACLE_RUNNERS, "determinism", custom)
    assert module.run_oracles(root, ["determinism"])["batch_manifest"]["status"] == "verified"
    assert calls == [root]
