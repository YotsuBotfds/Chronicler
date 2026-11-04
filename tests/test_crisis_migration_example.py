"""A fixed native development scenario; migration is not forced eviction."""
import pytest

pytestmark = pytest.mark.native


def test_recorded_distress_move_and_constrained_receiving_food(tmp_path):
    pytest.importorskip("chronicler_agents")
    from scripts.crisis_migration_example import run
    result = run(tmp_path / "migration")
    assert result["exact_resume"]
    first, second = result["timeline"][2:4]
    samples = {row["group_id"]: row for row in first["mobility"]["samples"]}
    matched = []
    for event in first["migration_events"]:
        sample = samples.get(event["agent_id"])
        if (event["region"] == 1 and event["target_region"] == 2 and
                event["driver_name"] == "famine_memory" and sample is not None and
                sample["local_food_sufficiency"] < 1 and sample["reason"] == "sufficient"):
            assert event["pre_region"] == 1 and event["post_region"] == 2
            matched.append(event)
    assert matched, "no observed distress-associated household arrival"
    receiving_before = first["food"]["regions"][2]
    receiving_after = second["food"]["regions"][2]
    assert receiving_after["native_count"] > receiving_before["native_count"]
    assert receiving_after["native_count"] == first["after_native_counts"][2]
    a, b = receiving_before["native"], receiving_after["native"]
    assert a["demand"] < b["demand"] and a["sufficiency"] < 1 and b["sufficiency"] < 1
    assert a["closing"] == pytest.approx(0) and b["opening"] == pytest.approx(0)
    for row in (a, b):
        assert abs(row["balance_residual"]) <= row["balance_tolerance"]
    assert (tmp_path / "migration" / "arrival.ckpt").exists()
