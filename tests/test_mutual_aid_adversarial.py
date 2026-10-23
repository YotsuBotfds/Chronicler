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
    # Actual native cargo encumbers aid. Integrated goods trade leaves the
    # donor more grain than the pre-integration trajectory, so these sends are
    # need-bound rather than reserve-bound; every send must still be funded
    # only from stock net of live merchant commitments and the donor reserve
    # (deterministic reserve-binding coverage is in test_mutual_aid.py).
    for row in (r for r in rows if r["transfers"]):
        cargo = [c for c in row["native_commitments"] if c["region_id"] == 0 and c["good_slot"] == 0][0]
        committed = cargo["reserved"] + cargo["pending_departure"]
        assert committed > 0
        demand = row["food_demand"]["Granary"]
        free = row["stocks_before"]["Granary"]["grain"] - committed
        sent = sum(sum(t["sent"].values()) for t in row["transfers"])
        assert sent <= min(max(0.0, free - 2 * demand), 0.25 * demand) + 1e-9
        remaining = row["stocks_after_aid"]["Granary"]["grain"] - committed
        assert remaining >= 2 * demand - 1e-9
        assert row["transfers"][0]["treasury_cost"] == 1
        assert row["aid_transit_loss"] > 0
    assert any(c["pending_departure"] > 0 for r in rows if r["transfers"]
               for c in r["native_commitments"] if c["region_id"] == 0 and c["good_slot"] == 0)
    assert rows[5]["treasury_after"] == 0
    assert rows[5]["sufficiency"]["Mine"] >= .8
    assert rows[5]["memory_after"]["Mine"]["stress_streak"] == 0
    assert all(not r["transfers"] for r in rows[6:])
    # The streak resets at recovery and must be reacquired from fresh stress.
    streaks = [r["memory_after"]["Mine"]["stress_streak"] for r in rows]
    restart = streaks.index(1, 6)
    assert all(streak == 0 for streak in streaks[5:restart])
    assert streaks[restart:restart + 3] == [1, 2, 3]
    assert rows[14]["prior_memory"]["Mine"]["stress_streak"] == 3
    assert rows[14]["treasury_before"] == 0
    assert all(r["economy_conservation"]["clamp_floor_loss"] == 0 for r in rows)
    assert max(abs(r["conservation_residual"]) for r in rows) < 5e-5
    assert result["full_hybrid_continuation_tested"] is False


@pytest.mark.native
def test_multiturn_recovery_blocks_funded_aid_then_reactivation():
    rows = _run(True, 20)["history"]
    exhausted = _run(True, 2)["history"]
    reactivated = 14  # fresh three-turn stress after recovery (see streak test)
    for funded, limited in zip(rows[:reactivated], exhausted[:reactivated], strict=True):
        for key in ("stocks_before", "stocks_after_aid", "native_commitments",
                    "sufficiency", "agent_snapshot", "delivery_diagnostics"):
            assert funded[key] == limited[key]
    assert [r["turn"] for r in rows if r["transfers"]] == [4, 5, reactivated]
    assert all(r["treasury_before"] > 0 and not r["transfers"] for r in rows[6:reactivated])
    assert rows[5]["memory_after"]["Mine"]["stress_streak"] == 0
    assert rows[reactivated]["prior_memory"]["Mine"]["stress_streak"] == 3
    # Funding, not stress, separates the runs: only the funded run pays.
    assert rows[reactivated]["treasury_after"] < rows[reactivated]["treasury_before"]
    assert not exhausted[reactivated]["transfers"]


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
def test_multiturn_disabled_matches_untouched_public_source_with_same_repaired_native():
    """Isolate default-off Python aid changes from intentional native repairs.

    Original-native byte-for-byte equivalence is no longer expected after cargo
    lifecycle repairs. Both Python sources use the exact same compiled package.
    """
    baseline_root = os.environ.get("CHRONICLER_UNTOUCHED_SOURCE")
    if not baseline_root:
        pytest.skip("Provide CHRONICLER_UNTOUCHED_SOURCE for the untouched Python control")
    native = pytest.importorskip("chronicler_agents")
    baseline_native = Path(native.__file__).resolve().parent.parent
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
    assert baseline["native"] == feature["native"]
    assert baseline["native_has_stockpile_commitments"] is True
    assert feature["native_has_stockpile_commitments"] is True
    for b, f in zip(baseline["history"], feature["history"], strict=True):
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
