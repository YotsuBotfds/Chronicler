"""A real multiprocessing batch: ``--parallel 2`` through ``multiprocessing.Pool``.

Every other batch test replaces the pool or runs sequentially; this one starts
the CLI in child processes, so it is marked ``real_process`` and is not in the
bounded offline lane (its guard blocks child processes). CI runs it with
``pytest -m real_process`` (``.github/workflows/hashseed-sweep.yml``).

The same 2-seed, 5-turn aggregate batch runs under ``PYTHONHASHSEED`` 0 and 1:
the batch summary and the order of the recorded runs must not depend on the
hash seed or on which worker finishes first.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.real_process


def _run_batch(out: Path, hash_seed: str) -> Path:
    env = dict(os.environ, PYTHONHASHSEED=hash_seed, PYTHONPATH=str(ROOT / "src"))
    cmd = [sys.executable, "-m", "chronicler.main", "--seed", "42", "--batch", "2", "--parallel", "2",
           "--turns", "5", "--agents", "off", "--simulate-only", "--output", str(out / "chronicle.md")]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-4000:]
    return out / "batch_42"


def _order(batch_dir: Path) -> list[tuple]:
    manifest = json.loads((batch_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    return [(run["seed"], run["dir"], run["total_turns"]) for run in manifest["runs"]]


def test_parallel_batch_summary_and_order_do_not_depend_on_hash_seed(tmp_path):
    first = _run_batch(tmp_path / "h0", "0")
    second = _run_batch(tmp_path / "h1", "1")
    summary = (first / "summary.md").read_text(encoding="utf-8")
    assert summary == (second / "summary.md").read_text(encoding="utf-8")
    assert summary.count("\n| ") == 3          # the header row and one row per seed
    assert _order(first) == _order(second) == [(42, "seed_42", 5), (43, "seed_43", 5)]
