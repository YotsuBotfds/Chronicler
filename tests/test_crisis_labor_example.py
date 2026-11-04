"""Real native outcomes for one constructed development case, not an efficacy study."""
import pytest

pytestmark = pytest.mark.native


def test_constructed_poor_production_and_care_share_native_runtime(tmp_path):
    pytest.importorskip("chronicler_agents")
    from scripts.crisis_labor_example import run
    result = run(tmp_path / "development-case")
    off = result["arms"]["care_off"]["timeline"]
    on = result["arms"]["care_on"]["timeline"]
    assert len(on) == len(off) == 8
    assert all(row["health_care"]["care_work"] == 0 for row in off)
    assert any(row["health_care"]["new_injuries"] > 0 for row in on)
    assert any(row["episodes"] for row in on)
    simultaneous = []
    for row in on:
        food = row["food_accounting"]
        assert food["mode"] == "hybrid" and food["source_turn"] == row["source_turn"]
        for health in row["health_care"]["regions"]:
            native = food["regions"][health["region"]]["native"]
            if health["care_work"] > 0 and native is not None and native["produced"] < native["demand"]:
                assert health["care_recipients"] > 0 and native["demand"] > 0
                simultaneous.append((row["source_turn"], health["region"]))
    assert simultaneous, "no region had both real caregiving work and below-demand production"
    # First observed care is a matched prehistory in this fixed development run.
    turn, region = simultaneous[0]
    assert turn > 0 and all(row["health_care"]["care_work"] == 0 for row in on[:turn])
    assert on[turn - 1]["episodes"] == off[turn - 1]["episodes"]
    on_health = next(r for r in on[turn]["health_care"]["regions"] if r["region"] == region)
    off_health = next(r for r in off[turn]["health_care"]["regions"] if r["region"] == region)
    on_food = on[turn]["food_accounting"]["regions"][region]["native"]
    off_food = off[turn]["food_accounting"]["regions"][region]["native"]
    assert on_health["recovery_progress"] > off_health["recovery_progress"]
    assert on_food["produced"] < off_food["produced"] < off_food["demand"]
    assert (tmp_path / "development-case" / "common.ckpt").is_file()
