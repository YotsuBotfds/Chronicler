"""Multi-turn native adversarial evidence; no injected cargo or stock credits."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _run(enabled, treasury):
    pytest.importorskip("chronicler_agents")
    script = Path(__file__).resolve().parents[1] / "scripts/mutual_aid_adversarial.py"
    spec = importlib.util.spec_from_file_location("aid_adversarial", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_adversarial(enabled, treasury)


@pytest.mark.native
def test_multiturn_native_stress_cargo_reserve_funding_and_recovery():
    result = _run(True, 2)
    rows = result["history"]
    assert [r["memory_after"]["Mine"]["stress_streak"] for r in rows[:3]] == [1, 2, 3]
    assert all(not r["transfers"] for r in rows[:4])
    assert [r["turn"] for r in rows if r["transfers"]] == [4, 5]
    # First eligible dispatch is blocked by uncommitted donor reserve.
    assert rows[3]["prior_memory"]["Mine"]["stress_streak"] == 3
    assert rows[3]["treasury_after"] == 2
    pending = sum(c["reserved"] + c["pending_departure"] for c in rows[3]["native_commitments"]
                  if c["region_id"] == 0 and c["good_slot"] == 0)
    assert rows[3]["stocks_before"]["Granary"]["grain"] - pending < 2 * rows[3]["food_demand"]["Granary"]
    # Actual native cargo encumbers aid: exact reserve-bound send at turn4.
    row = rows[4]
    cargo = [c for c in row["native_commitments"] if c["region_id"] == 0 and c["good_slot"] == 0][0]
    assert cargo["reserved"] > 0
    assert cargo["pending_departure"] > 0
    remaining = row["stocks_after_aid"]["Granary"]["grain"] - cargo["reserved"] - cargo["pending_departure"]
    assert remaining == pytest.approx(2 * row["food_demand"]["Granary"])
    assert row["transfers"][0]["treasury_cost"] == 1
    assert row["aid_transit_loss"] > 0
    assert rows[5]["treasury_after"] == 0
    assert rows[5]["sufficiency"]["Mine"] >= .8
    assert rows[5]["memory_after"]["Mine"]["stress_streak"] == 0
    assert all(not r["transfers"] for r in rows[6:])
    # The streak resets at recovery and must be reacquired from fresh stress.
    assert rows[10]["memory_after"]["Mine"]["stress_streak"] == 0
    assert [r["memory_after"]["Mine"]["stress_streak"] for r in rows[11:14]] == [1, 2, 3]
    assert rows[14]["prior_memory"]["Mine"]["stress_streak"] == 3
    assert rows[14]["treasury_before"] == 0
    assert all(r["economy_conservation"]["clamp_floor_loss"] == 0 for r in rows)
    assert max(abs(r["conservation_residual"]) for r in rows) < 5e-5
    assert result["full_hybrid_continuation_tested"] is False


@pytest.mark.native
def test_multiturn_recovery_blocks_funded_aid_then_reactivation():
    rows = _run(True, 20)["history"]
    exhausted = _run(True, 2)["history"]
    for funded, limited in zip(rows[:14], exhausted[:14], strict=True):
        for key in ("stocks_before", "stocks_after_aid", "native_commitments",
                    "sufficiency", "agent_snapshot", "delivery_diagnostics"):
            assert funded[key] == limited[key]
    assert [r["turn"] for r in rows if r["transfers"]] == [4, 5, 14]
    assert all(r["treasury_before"] > 0 and not r["transfers"] for r in rows[6:14])
    assert rows[5]["memory_after"]["Mine"]["stress_streak"] == 0
    assert rows[14]["prior_memory"]["Mine"]["stress_streak"] == 3


@pytest.mark.native
def test_multiturn_disabled_aid_is_noop():
    result = _run(False, 2)
    for row in result["history"]:
        assert row["stocks_before"] == row["stocks_after_aid"]
        assert row["treasury_before"] == row["treasury_after"] == 2
        assert not row["transfers"] and not row["aid_events"]
        assert not row["prior_memory"] and not row["memory_after"]
        assert abs(row["conservation_residual"]) < 5e-5


@pytest.mark.native
def test_multiturn_disabled_matches_untouched_public_source_and_native():
    """Requires an explicit pristine edf7299 export and its original native build."""
    baseline_root = os.environ.get("CHRONICLER_UNTOUCHED_SOURCE")
    baseline_native = os.environ.get("CHRONICLER_UNTOUCHED_NATIVE")
    if not baseline_root or not baseline_native:
        pytest.skip("Provide CHRONICLER_UNTOUCHED_SOURCE and CHRONICLER_UNTOUCHED_NATIVE for the untouched control")
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts/mutual_aid_adversarial.py"
    def run(source, native):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(Path(source) / "src"), str(native)]))
        output = subprocess.run([sys.executable, str(script), "--disabled", "--treasury", "2"],
                                env=env, check=True, capture_output=True, text=True)
        return json.loads(output.stdout)
    baseline = run(baseline_root, baseline_native)
    feature = _run(False, 2)
    assert Path(baseline["source"]).resolve() == (Path(baseline_root) / "src/chronicler/__init__.py").resolve()
    assert Path(baseline["native"]).resolve().is_relative_to(Path(baseline_native).resolve())
    assert baseline["native_has_stockpile_commitments"] is False
    assert feature["native_has_stockpile_commitments"] is True
    for b, f in zip(baseline["history"], feature["history"], strict=True):
        # The old native build cannot expose this newly added read-only diagnostic.
        b = {k: v for k, v in b.items() if k != "native_commitments"}
        f = {k: v for k, v in f.items() if k != "native_commitments"}
        assert b == f


@pytest.mark.native
def test_multiturn_physical_state_unchanged_before_eligible_surplus():
    treatment = _run(True, 2)["history"]
    disabled = _run(False, 2)["history"]
    for t, d in zip(treatment[:4], disabled[:4], strict=True):
        for key in ("stocks_before", "stocks_after_aid", "economy_conservation",
                    "sufficiency", "native_commitments", "delivery_diagnostics",
                    "world_after_behavior", "agent_snapshot", "treasury_after"):
            assert t[key] == d[key]
