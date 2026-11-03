"""Real receiving-region supply/service chain and same-boundary alternatives."""
import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def test_receiving_trade_permission_gate_and_actual_recovery(tmp_path):
    from scripts.crisis_receiving_service_example import ROOT
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT)
    for name in ("RAYON_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        env[name] = "1"
    output = tmp_path / "receiving"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/crisis_receiving_service_example.py"),
        str(output), "--simulate-only"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=110)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    case = json.loads((output / "case.json").read_text())
    assert case["state"] == "validated"
    graph = case["graph_diagnosis"]
    assert [1, 2] not in graph["original"] and [0, 2] not in graph["original"]
    assert [1, 2] in graph["declared_variant"] and [0, 2] in graph["declared_variant"]
    starts = [v["common_before_control"] for v in case["arms"].values()]
    assert starts[0] == starts[1] == starts[2]
    for key in ("native_sha256", "python_rng_sha256", "numpy_rng_sha256"):
        assert len({v["start"][key] for v in case["arms"].values()}) == 1
    assert all(case["exact_resume"].values())
    admission = case["admission"]
    assert admission["distress_associated_arrivals"] and admission["service_interruption"]
    assert admission["real_open_resupply_and_teaching"] and admission["reopened_resupply_and_teaching"]
    assert all(e["driver_name"] in {"famine_memory", "material_need", "low_satisfaction", "opp_food"}
               for e in admission["distress_associated_arrivals"])
    for chain in admission["closed_recovery_chains"]:
        assert chain["arrival_source"] >= 6
        assert chain["arrival_source"] + 1 == chain["purchase_source"]
        assert chain["purchase_source"] + 1 == chain["teaching_source"]
        assert chain["teaching_source"] > 7
        assert chain["purchase"]["purchased"] > 0 and chain["purchase"]["paid"] > 0
        assert chain["purchase"]["upkeep_satisfied"] is True
        assert all(r["crafts_used"] > 0 and r["work_delivered"] > 0 for r in chain["teaching"])
    gap = admission["closed_source7_unknown_work"]
    assert gap["work_requested"] == 0 and gap["work_delivered"] is None
    # The chosen closure cancels a reservation, not an already loaded voyage.
    assert case["analysis"]["closed"]["craft_cancellations"]
    assert case["analysis"]["closed"]["craft_returns"] == []
    assert case["analysis"]["paused"]["native_delivery_rows"] == 0
    assert case["analysis"]["paused"]["work_requested_sum"] == 0
    assert not case["analysis"]["paused"]["positive_teaching"]
    assert admission["receiving_pressure"]["admitted"]
    assert case["analysis"]["paused"]["paid"] == 0
    assert (output / "WALKTHROUGH.txt").is_file()
    # Fresh output is mandatory; a repeat must preserve every prior artifact.
    digest = (output / "case.json").read_bytes()
    repeat = subprocess.run([sys.executable, str(ROOT / "scripts/crisis_receiving_service_example.py"),
        str(output), "--simulate-only"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
    assert repeat.returncode != 0
    assert (output / "case.json").read_bytes() == digest
