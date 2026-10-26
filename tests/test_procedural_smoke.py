"""Procedural worlds through the whole gate path: a few seeds x a few dozen turns.

Runs ``scripts/m53b_run_validation.py --worldgen procedural`` (simulation,
validation sidecars, every oracle, the gate decision) on a small batch, so a
procedural world cannot break the gate silently. Needs the native extension.
See docs/integration/procedural-gates.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "m53b_run_validation.py"


@pytest.mark.slow
@pytest.mark.native
def test_procedural_subset_runs_end_to_end(tmp_path):
    pytest.importorskip("chronicler_agents")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--profile", "subset", "--worldgen", "procedural",
         "--seeds", "2", "--turns", "40", "--parallel", "2", "--output-root", str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=900,
    )
    batch = tmp_path / "oracle_subset" / "batch_42"
    report_path = batch / "validate_report_subset.json"
    assert report_path.exists(), proc.stdout[-4000:] + proc.stderr[-4000:]
    # A 40-turn batch is too short for every oracle to pass; it must not error.
    assert proc.returncode in (0, 2), proc.stderr[-4000:]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report.get("status") != "ERROR"
    for name, result in report["results"].items():
        assert result.get("status") != "ERROR", (name, result.get("reason"))
    assert report["worlds"] == [{"generator": "procedural", "regions": 32, "civs": 10, "seeds": 2}]
    manifest = json.loads((batch / "run_manifest.json").read_text(encoding="utf-8"))
    assert (manifest["worldgen"], manifest["regions"], manifest["civs"]) == ("procedural", 32, 10)
    for seed in (42, 43):
        state = json.loads((batch / f"seed_{seed}" / "state.json").read_text(encoding="utf-8"))
        assert state["geography"]["generator"] == "procedural"
        assert len(state["regions"]) == 32
        alive = [c for c in state["civilizations"] if c["regions"]]
        assert alive, "a procedural world went extinct in 40 turns"
        assert sum(r["population"] for r in state["regions"]) > 0
