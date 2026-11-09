"""Parallel batch workers pin the native rayon pool to one thread by default
and run with hash seed 0 unless the user chose one (ENV-4)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chronicler.batch import _init_parallel_worker


def test_parallel_worker_pins_rayon_threads_unless_user_set(monkeypatch):
    monkeypatch.delenv("RAYON_NUM_THREADS", raising=False)
    _init_parallel_worker()
    assert os.environ["RAYON_NUM_THREADS"] == "1"
    monkeypatch.setenv("RAYON_NUM_THREADS", "3")
    _init_parallel_worker()
    assert os.environ["RAYON_NUM_THREADS"] == "3"


def test_parallel_batch_uses_worker_initializer(monkeypatch, tmp_path):
    import chronicler.batch as batch_mod

    seen = {}

    class FakeAsync:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class FakePool:
        def __init__(self, workers, initializer=None):
            seen["initializer"] = initializer

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def apply_async(self, fn, args):
            from chronicler.types import RunResult
            return FakeAsync(RunResult(seed=args[0].seed, output_dir=tmp_path, war_count=0,
                                       collapse_count=0, named_event_count=0, distinct_action_count=0,
                                       reflection_count=0, tech_advancement_count=0, max_stat_swing=0.0,
                                       action_distribution={}, dominant_faction="", total_turns=0))

    monkeypatch.setattr(batch_mod.multiprocessing, "Pool", FakePool)
    args = argparse.Namespace(seed=1, batch=2, parallel=2, simulate_only=True,
                              output=str(tmp_path / "chronicle.md"), tuning=None)
    batch_mod.run_batch(args)
    assert seen["initializer"] is _init_parallel_worker


def _fake_result(seed, tmp_path):
    from chronicler.types import RunResult
    return RunResult(seed=seed, output_dir=tmp_path, war_count=0, collapse_count=0,
                     named_event_count=0, distinct_action_count=0, reflection_count=0,
                     tech_advancement_count=0, max_stat_swing=0.0, action_distribution={},
                     dominant_faction="", total_turns=0)


def _manifest_hash_seed(batch_dir):
    manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    return manifest["environment"]["thread_env"]["PYTHONHASHSEED"]


def test_worker_hash_seed_is_zero_for_the_batch_and_restored(monkeypatch):
    from chronicler.batch import _worker_hash_seed

    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    with _worker_hash_seed(True):
        assert os.environ["PYTHONHASHSEED"] == "0"
    assert "PYTHONHASHSEED" not in os.environ
    with _worker_hash_seed(False):
        assert "PYTHONHASHSEED" not in os.environ
    monkeypatch.setenv("PYTHONHASHSEED", "7")
    with _worker_hash_seed(True):
        assert os.environ["PYTHONHASHSEED"] == "7"
    assert os.environ["PYTHONHASHSEED"] == "7"


def test_unreplaced_pool_uses_the_spawn_context(monkeypatch):
    import chronicler.batch as batch_mod

    seen = {}

    class FakeContext:
        def Pool(self, workers, initializer=None):
            seen["pool"] = (workers, initializer)
            return "pool"

    def get_context(method):
        seen["method"] = method
        return FakeContext()

    monkeypatch.setattr(batch_mod.multiprocessing, "get_context", get_context)
    assert batch_mod._worker_pool(3) == "pool"
    assert seen == {"method": "spawn", "pool": (3, _init_parallel_worker)}


def test_parallel_manifest_records_hash_seed_zero(monkeypatch, tmp_path):
    """The manifest is built inside the scope; the parent's environment is restored."""
    import chronicler.batch as batch_mod

    seen = []

    class FakeAsync:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

    class FakePool:
        def __init__(self, workers, initializer=None):
            seen.append(os.environ.get("PYTHONHASHSEED"))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def apply_async(self, fn, args):
            return FakeAsync(_fake_result(args[0].seed, tmp_path))

    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    monkeypatch.setattr(batch_mod.multiprocessing, "Pool", FakePool)
    args = argparse.Namespace(seed=1, batch=2, parallel=2, simulate_only=True,
                              output=str(tmp_path / "p" / "chronicle.md"), tuning=None)
    assert _manifest_hash_seed(batch_mod.run_batch(args)) == "0"
    assert seen == ["0"]
    assert "PYTHONHASHSEED" not in os.environ


@pytest.mark.real_process
def test_spawned_parallel_batch_without_hash_seed_equals_sequential_seed_zero(tmp_path):
    """A real ``--parallel`` batch whose parent has no ``PYTHONHASHSEED`` writes
    the bundles of a sequential batch run with ``PYTHONHASHSEED=0``. It starts
    child processes, so it is outside the offline oracle lane."""
    root = Path(__file__).resolve().parents[1]

    def run(out, extra, hash_seed):
        env = dict(os.environ, PYTHONPATH=str(root / "src"))
        env.pop("PYTHONHASHSEED", None)
        if hash_seed is not None:
            env["PYTHONHASHSEED"] = hash_seed
        cmd = [sys.executable, "-m", "chronicler.main", "--seed", "42", "--batch", "3",
               "--turns", "15", "--agents", "off", "--simulate-only",
               "--output", str(out / "chronicle.md"), *extra]
        proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=900)
        assert proc.returncode == 0, proc.stderr[-4000:]
        return out / "batch_42"

    def bundles(batch_dir):
        out = {}
        for path in sorted(batch_dir.glob("seed_*/chronicle_bundle.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            data["metadata"].pop("generated_at", None)
            out[path.parent.name] = data
        return out

    parallel = run(tmp_path / "parallel", ["--parallel", "3"], None)
    sequential = run(tmp_path / "sequential", [], "0")
    assert _manifest_hash_seed(parallel) == "0"
    assert _manifest_hash_seed(sequential) == "0"
    parallel_bundles = bundles(parallel)
    assert sorted(parallel_bundles) == ["seed_42", "seed_43", "seed_44"]
    assert parallel_bundles == bundles(sequential)
