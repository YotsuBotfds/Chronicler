"""Parallel batch workers pin the native rayon pool to one thread by default."""
from __future__ import annotations

import argparse
import os

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
