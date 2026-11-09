"""Turn-speed changes that must keep every value: helpers against their originals."""
from __future__ import annotations

import importlib
import os

import pyarrow as pa
import pytest

import chronicler
import chronicler.politics  # noqa: F401  (politics_bridge imports politics first)
from chronicler.politics_bridge import _batch_to_dict


def _reference_batch_to_dict(batch) -> dict:
    """The conversion before the turn-speed work (``to_pylist`` per column)."""
    return {batch.schema.field(i).name: batch.column(i).to_pylist() for i in range(batch.num_columns)}


def _batches():
    columns = {
        "step": pa.array([3, 1, 2], pa.uint16()),
        "seq": pa.array([0, 7, 2**40], pa.uint64()),
        "civ": pa.array([0, 255, 4], pa.uint8()),
        "delta": pa.array([-1, 0, 5], pa.int32()),
        "value": pa.array([0.1, -2.5, 3.0e-8], pa.float32()),
        "flag": pa.array([True, False, True]),
        "name": pa.array(["a", "", "ç"]),
        "region_indices": pa.array([[1, 2], [], [65535]], pa.list_(pa.uint16())),
    }
    full = pa.record_batch(columns)
    yield full
    yield full.slice(0, 0)
    yield pa.record_batch({"nullable": pa.array([1, None, 3], pa.uint16())})
    import arro3.core as ac
    yield ac.RecordBatch.from_arrow(full)
    yield ac.RecordBatch.from_arrow(full.slice(0, 0))


@pytest.mark.parametrize("batch", list(_batches()))
def test_politics_batch_to_dict_matches_to_pylist(batch):
    got = _batch_to_dict(batch)
    expected = _reference_batch_to_dict(batch)
    assert list(got) == list(expected)
    for name in expected:
        assert got[name] == expected[name]
        assert [type(v) for v in got[name]] == [type(v) for v in expected[name]]


def test_openblas_spin_timeout_is_a_default(monkeypatch):
    monkeypatch.delenv("OPENBLAS_THREAD_TIMEOUT", raising=False)
    importlib.reload(chronicler)
    assert os.environ["OPENBLAS_THREAD_TIMEOUT"] == "16"
    monkeypatch.setenv("OPENBLAS_THREAD_TIMEOUT", "28")
    importlib.reload(chronicler)
    assert os.environ["OPENBLAS_THREAD_TIMEOUT"] == "28"


def _reference_people_and_farmers(snapshot, n_regions):
    workers = [0] * n_regions
    people = [0] * n_regions
    for rid, occupation in zip(snapshot.column("region").to_pylist(),
                               snapshot.column("occupation").to_pylist()):
        if 0 <= rid < n_regions:
            people[rid] += 1
            if occupation == 0:
                workers[rid] += 1
    return people, workers


@pytest.mark.parametrize("n_regions", [0, 1, 5, 9])
def test_fishery_region_counts_match_the_row_loop(n_regions):
    import arro3.core as ac
    import numpy as np

    from chronicler.experimental.fisheries import _region_people_and_farmers

    rng = np.random.default_rng(n_regions)
    batch = pa.record_batch({
        "region": pa.array(rng.integers(0, 12, 500), pa.uint16()),
        "occupation": pa.array(rng.integers(0, 5, 500), pa.uint8()),
    })
    for b in (batch, ac.RecordBatch.from_arrow(batch), batch.slice(0, 0)):
        people, farmers = _region_people_and_farmers(b, n_regions)
        assert (people, farmers) == _reference_people_and_farmers(b, n_regions)
        assert all(type(v) is int for v in people + farmers)
    nullable = pa.record_batch({
        "region": pa.array([0, None], pa.uint16()), "occupation": pa.array([0, 0], pa.uint8()),
    })
    assert _region_people_and_farmers(nullable, 3) is None


def test_schema_names_are_each_batchs_own():
    import arro3.core as ac

    from chronicler.columnar import schema_names

    batches = []
    for i in range(7):
        b = pa.record_batch({f"a{i}": pa.array([1]), f"b{i}": pa.array([2.0])})
        batches.append(b if i % 2 else ac.RecordBatch.from_arrow(b))
    for _ in range(2):  # more batches than the cache holds, twice over
        for b in batches:
            assert schema_names(b) == tuple(b.schema.names)
    b = batches[-1]
    assert schema_names(b) is schema_names(b)
    with pytest.raises(AttributeError):
        schema_names(object())


def _reference_memory_text(stream) -> str:
    """``MemoryStream.save``'s text before the turn-speed work."""
    import json

    data = {
        "civilization_name": stream.civilization_name,
        "entries": [
            {"turn": e.turn, "text": e.text, "importance": e.importance, "entry_type": e.entry_type}
            for e in stream.entries
        ],
        "reflections": [
            {"turn": r.turn, "text": r.text, "importance": r.importance, "entry_type": r.entry_type}
            for r in stream.reflections
        ],
    }
    return json.dumps(data, indent=2)


def test_memory_stream_text_matches_json_dumps(tmp_path):
    import copy
    import random

    from chronicler.memory import MemoryStream

    rng = random.Random(5)
    words = ["war", 'the "quoted" pact', "naïve\nline", "المدينة", "tab\there", ""]
    stream = MemoryStream(civilization_name="Kethani Émpire")
    assert stream.json_text() == _reference_memory_text(stream)
    for turn in range(1, 40):
        for _ in range(rng.randrange(4)):
            stream.add(text=rng.choice(words) + str(turn), turn=turn, importance=rng.randrange(1, 11))
        if turn % 7 == 0:
            stream.add_reflection(rng.choice(words), turn)
        if turn % 5 == 0 and stream.entries:
            # In-place changes after an entry was encoded are picked up.
            e = rng.choice(stream.entries)
            e.text = e.text + "!"
            e.importance = float(e.importance) if turn % 10 else 7
        if turn % 9 == 0:
            stream.entries = stream.entries[:-1]  # a shorter list
        assert stream.json_text() == _reference_memory_text(stream), turn
    clone = copy.deepcopy(stream)
    assert clone.json_text() == _reference_memory_text(stream)
    path = tmp_path / "m" / "memories.json"
    stream.save(path)
    assert path.read_text() == _reference_memory_text(stream)
    assert MemoryStream.load(path).json_text() == path.read_text()


# --- identity gate: scripts/turn_speed_identity.py digest / check -------------------

def _identity_script():
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import turn_speed_identity
    return turn_speed_identity


def _native_checkout(root, lib="pub fn f() {}\n"):
    crate = root / "chronicler-agents"
    (crate / "src" / "ffi").mkdir(parents=True)
    (crate / "Cargo.toml").write_text("[package]\nname = 'x'\n")
    (crate / "Cargo.lock").write_text("# lock\n")
    (crate / "src" / "lib.rs").write_text(lib)
    (crate / "src" / "ffi" / "mod.rs").write_text("// ffi\n")
    return root


def _identity_run(out, *, native=None, python="3.13.17", platform="linux-x86_64",
                  bundle_stamp="2026-01-01T00:00:00", memory=b"[]\n"):
    import hashlib
    import json
    out.mkdir(parents=True)
    which = [f"python {python} {platform}", "chronicler /src/chronicler/__init__.py"]
    if native is not None:
        which.append(f"native /site/chronicler_agents/ext.so {hashlib.sha256(native).hexdigest()}")
    (out / "which.txt").write_text("\n".join(which) + "\n")
    for case in ("g_a", "g_b"):
        d = out / case
        (d / "seed_1").mkdir(parents=True)
        bundle = {"metadata": {"generated_at": bundle_stamp, "seed": 1}, "history": [{"turn": 1}]}
        (d / "chronicle_bundle.json").write_text(json.dumps(bundle))
        (d / "memories_x.json").write_bytes(memory)
        (d / "seed_1" / "state.json").write_text('{"turn": 1}')
        (d / "run_manifest.json").write_text(json.dumps({"wall": bundle_stamp}))
        (out / f"{case}.log").write_text(f"{case}: {bundle_stamp}\n")
    return out


def _golden(tmp_path, out, receipt=None):
    M = _identity_script()
    path = tmp_path / f"golden-{out.name}.json"
    assert M.digest(out, path, receipt) == 0
    return path


def _receipt(tmp_path, root, extension_bytes, name="receipt.json"):
    M = _identity_script()
    ext = tmp_path / f"{name}.so"
    ext.write_bytes(extension_bytes)
    path = tmp_path / name
    M.write_receipt(path, ext, root, rustc="rustc 1.97.0 (2d8144b78 2026-07-07)")
    return path


def test_identity_digest_is_stable_and_ignores_the_wall_clock(tmp_path):
    import json
    M = _identity_script()
    a = _golden(tmp_path, _identity_run(tmp_path / "a"))
    b = _golden(tmp_path, _identity_run(tmp_path / "b", bundle_stamp="2031-05-05T12:00:00"))
    assert a.read_bytes() == b.read_bytes()
    data = json.loads(a.read_text())
    assert sorted(data["cases"]) == ["g_a", "g_b"]
    assert sorted(data["cases"]["g_a"]) == ["chronicle_bundle.json", "memories_x.json", "seed_1/state.json"]
    assert data["environment"] == {
        "compat": {"python_minor": "3.13", "platform": "linux-x86_64", "rust_channel": None},
        "provenance": {"python_full": "3.13.17", "rustc": None, "native_sha256": None,
                       "native_source_digest": None}}
    assert M.check(tmp_path / "b", a) == 0


def test_identity_check_detects_a_one_byte_output_change(tmp_path, capsys):
    M = _identity_script()
    golden = _golden(tmp_path, _identity_run(tmp_path / "a"))
    _identity_run(tmp_path / "b", memory=b"[1\n")
    assert M.check(tmp_path / "b", golden) == 1
    out = capsys.readouterr().out
    assert "differs: g_a/memories_x.json" in out and "differs: g_b/memories_x.json" in out
    (tmp_path / "b" / "g_b" / "memories_x.json").unlink()
    (tmp_path / "b" / "g_b" / "extra.json").write_text("{}")
    assert M.check(tmp_path / "b", golden) == 1
    out = capsys.readouterr().out
    assert "only in golden: g_b/memories_x.json" in out and "only in run: g_b/extra.json" in out


def test_identity_check_accepts_a_rebuilt_extension_with_identical_outputs(tmp_path, capsys):
    import hashlib
    M = _identity_script()
    root = _native_checkout(tmp_path / "repo")
    golden = _golden(tmp_path, _identity_run(tmp_path / "a", native=b"old build"),
                     _receipt(tmp_path, root, b"old build", "old.json"))
    receipt = _receipt(tmp_path, root, b"new build", "new.json")
    _identity_run(tmp_path / "b", native=b"new build")
    assert M.check(tmp_path / "b", golden, "native", receipt, root) == 0
    old, new = (hashlib.sha256(b).hexdigest() for b in (b"old build", b"new build"))
    assert f"native rebuilt: {old} -> {new}" in capsys.readouterr().out


def test_identity_check_rejects_the_same_extension_with_changed_outputs(tmp_path, capsys):
    M = _identity_script()
    root = _native_checkout(tmp_path / "repo")
    receipt = _receipt(tmp_path, root, b"build")
    golden = _golden(tmp_path, _identity_run(tmp_path / "a", native=b"build"), receipt)
    _identity_run(tmp_path / "b", native=b"build", memory=b"[2]\n")
    assert M.check(tmp_path / "b", golden, "native", receipt, root) == 1
    out = capsys.readouterr().out
    assert "differs: g_a/memories_x.json" in out and "native rebuilt" not in out


@pytest.mark.parametrize("change", [{"python": "3.14.0"}, {"platform": "darwin-arm64"}])
def test_identity_check_refuses_an_incompatible_runtime(tmp_path, capsys, change):
    M = _identity_script()
    golden = _golden(tmp_path, _identity_run(tmp_path / "a"))
    _identity_run(tmp_path / "b", **change)
    assert M.check(tmp_path / "b", golden) == 1
    assert M.INCOMPATIBLE in capsys.readouterr().out


def test_identity_check_refuses_a_build_that_is_not_the_checkouts(tmp_path, capsys):
    M = _identity_script()
    root = _native_checkout(tmp_path / "repo")
    receipt = _receipt(tmp_path, root, b"build")
    golden = _golden(tmp_path, _identity_run(tmp_path / "a", native=b"build"), receipt)
    _identity_run(tmp_path / "b", native=b"build")
    assert M.check(tmp_path / "b", golden, "native", receipt, root) == 0
    capsys.readouterr()
    # The checkout's native source moved on since the receipt's build.
    other = _native_checkout(tmp_path / "other", lib="pub fn g() {}\n")
    assert M.check(tmp_path / "b", golden, "native", receipt, other) == 1
    assert "receipt built from native source" in capsys.readouterr().out
    # The runs loaded an extension other than the receipt's.
    _identity_run(tmp_path / "c", native=b"another build")
    assert M.check(tmp_path / "c", golden, "native", receipt, root) == 1
    assert "is not the receipt's" in capsys.readouterr().out
    # No receipt, or a python lane that loaded the extension.
    assert M.check(tmp_path / "b", golden, "native", None, root) == 1
    assert M.check(tmp_path / "b", golden, "python") == 1
    assert "python lane loaded a native extension" in capsys.readouterr().out


def test_identity_gate_cases_and_native_source_digest():
    from pathlib import Path
    M = _identity_script()
    assert M.SPEED_CASES == ("off_s42", "off_s7", "hybrid_s42", "hybrid_s7", "hybrid_s1234",
                             "proc48_hybrid_s42", "proc48_off_s7", "scaled22k_s42", "scaled52k_s7")
    gate = {name for name in M.CASES if name.startswith("g_")}
    assert set(M.GATE_PYTHON) | set(M.GATE_NATIVE) == gate and len(gate) == 8
    assert "g_off_s42" in M.GATE_PYTHON and "g_off_s42" in M.GATE_NATIVE
    assert M._rust_channel("rustc 1.97.0 (2d8144b78 2026-07-07)") == "stable"
    assert M._rust_channel("rustc 1.99.0-nightly (abc 2026-08-01)") == "nightly"
    repo = Path(__file__).resolve().parents[1]
    assert len(M.native_source_digest(repo)) == 64
    # The workflow runs exactly each lane's cases against that lane's golden.
    import json
    import re
    text = (repo / ".github" / "workflows" / "identity-gate.yml").read_text(encoding="utf-8")
    python_job, native_job = text.split("\n  native-lane:\n")
    assert tuple(re.findall(r"--case (\S+)", python_job)) == M.GATE_PYTHON
    assert tuple(re.findall(r"--case (\S+)", native_job)) == M.GATE_NATIVE
    for lane, cases in (("python", M.GATE_PYTHON), ("native", M.GATE_NATIVE)):
        golden = json.loads((repo / "tests" / "fixtures" / "identity" / f"{lane}_goldens.json").read_text())
        assert sorted(golden["cases"]) == sorted(cases)


def test_identity_coverage_map_names_every_witnessed_path():
    import json
    from pathlib import Path
    M = _identity_script()
    repo = Path(__file__).resolve().parents[1]
    witnessed = set()

    def walk(node):
        if isinstance(node, dict):
            for key in ("files", "new_files"):
                if isinstance(node.get(key), dict):
                    witnessed.update(node[key])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for fixture in sorted((repo / "tests" / "fixtures").glob("*inverse*.json")):
        walk(json.loads(fixture.read_text(encoding="utf-8")))
    witnessed |= {"chronicler-agents/src/health_care.rs", "chronicler-agents/src/health_care_observation.rs",
                  "src/chronicler/health_care.py", "src/chronicler/health_care_state.py"}
    paths = json.loads((repo / "tests" / "fixtures" / "identity" / "coverage.json").read_text())["paths"]
    assert set(paths) == witnessed and len(paths) == 91
    lanes = {f"python:{c}" for c in M.GATE_PYTHON} | {f"native:{c}" for c in M.GATE_NATIVE}
    for path, entry in paths.items():
        assert (repo / path).is_file(), path
        if isinstance(entry["identity"], list):
            assert entry["identity"] and set(entry["identity"]) <= lanes, path
        else:
            assert entry["identity"] in ("tests", "none"), path
            for test in entry.get("tests", []):
                name = test.split(" ")[0]
                assert name in ("npm", "cargo") or (repo / name).is_file(), (path, test)


def test_identity_batch_manifest_drops_clock_machine_and_commit(tmp_path):
    import hashlib
    import json
    M = _identity_script()

    def batch(root, stamp, sha):
        d = root / "batch_1"
        (d / "seed_1").mkdir(parents=True)
        (d / "seed_1" / "chronicle_bundle.json").write_text(json.dumps({"metadata": {"generated_at": stamp}}))
        digest = hashlib.sha256((d / "seed_1" / "chronicle_bundle.json").read_bytes()).hexdigest()
        (d / "batch_manifest.json").write_text(json.dumps({
            "created_at": stamp, "completed_at": stamp, "environment": {"executable": str(root)},
            "source": {"git_sha": sha, "package_dir": str(root)}, "native": {"status": "absent"},
            "seeds": [1], "runs": [{"seed": 1, "files": {"seed_1/chronicle_bundle.json": digest}}],
            "where": str(d / "seed_1")}))
        return M.output_digests(root)

    a = batch(tmp_path / "a", "2026-01-01", "abc")
    b = batch(tmp_path / "b", "2027-02-02", "def")
    assert a == b
    # The recorded digest is still checked: a wrong one is not a label.
    d = tmp_path / "b" / "batch_1"
    data = json.loads((d / "batch_manifest.json").read_text())
    data["runs"][0]["files"]["seed_1/chronicle_bundle.json"] = "0" * 64
    (d / "batch_manifest.json").write_text(json.dumps(data))
    assert M.output_digests(tmp_path / "b") != a
