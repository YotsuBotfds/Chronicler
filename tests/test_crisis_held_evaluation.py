"""Integrity checks for frozen evaluation extraction, without native execution."""
from copy import deepcopy

import pytest

from scripts.crisis_held_evaluation import differences, normalized_world, summarize_history


def frame(turn, *, demand=2.0, sufficiency=0.5):
    return {"turn": turn + 1, "food_accounting": {"mode": "hybrid", "timing": "phase2", "source_turn": turn, "completed_turn": turn + 1,
        "regions": [{"region_id": 0, "native_count": 4,
            "native": {"demand": demand, "sufficiency": sufficiency,
                "balance_residual": 1e-8, "balance_tolerance": 1e-5}, "public": None}]}}


def test_repeated_forecast_outcomes_count_once_but_turn_flows_sum():
    outcome = {"id": "report:1", "probability": 0.7, "outcome_shortfall": True,
               "brier": 0.09, "resolved_turn": 0}
    history = [frame(0), frame(1, sufficiency=1.2)]
    for row in history:
        row["harvest_forecasts"] = {"outcomes": [outcome], "counters": {"resolved": 1, "unscored": 2},
            "procurement_decisions": {"rows": [{"paid": 3}]}}
        row["grain_reserves"] = {"flows": [{"kind": "spoiled", "amount": 2}]}
    result = summarize_history(history)
    assert result["coverage"]["known_scored_report_ids"] == 1
    assert result["metrics"]["forecast_resolved"] == 1
    assert result["metrics"]["forecast_unscored"] == 2
    assert result["metrics"]["forecast_mean_brier"] == 0.09
    assert result["metrics"]["procurement_coins"] == 6
    assert result["metrics"]["public_spoiled"] == 4
    assert result["metrics"]["deficit_region_turns"] == 1
    assert result["metrics"]["care_worker_turns"] is None


def test_zero_demand_does_not_supply_weight_or_invent_a_measurement():
    result = summarize_history([frame(0, demand=0)])
    assert result["metrics"]["final_weighted_sufficiency"] is None
    assert result["metrics"]["mean_turn_weighted_sufficiency"] is None
    assert result["coverage"]["known_mean_turns"] == 0
    assert result["distribution"]["timeline"][0]["region_coverage"] == 0
    assert result["metrics"]["deficit_region_turns"] == 0
    assert result["metrics"]["forecast_resolved"] is None


def test_balance_violation_refuses_a_completed_evaluation():
    row = frame(0)
    row["food_accounting"]["regions"][0]["native"]["balance_residual"] = 1.0
    with pytest.raises(ValueError, match="recorded tolerance"):
        summarize_history([row])


def test_changed_repeated_forecast_identity_refuses_silent_overwrite():
    history = [frame(0), frame(1)]
    for i, row in enumerate(history):
        row["harvest_forecasts"] = {"outcomes": [{"id": "same", "brier": i / 2}]}
    with pytest.raises(ValueError, match="changed between snapshots"):
        summarize_history(history)


def test_opening_normalization_ignores_only_the_declared_policy():
    before = {"health_care": {"care_enabled": False, "injury_rate": 0.25}, "seed": 202}
    after = deepcopy(before)
    after["health_care"]["care_enabled"] = True
    assert normalized_world(before, "care") == normalized_world(after, "care")
    assert after["health_care"]["care_enabled"] is True
    after["health_care"]["injury_rate"] = 0.1
    assert normalized_world(before, "care") != normalized_world(after, "care")
    assert differences({"known": 1, "unknown": None}, {"known": 3, "unknown": 0}) == {"known": 2, "unknown": None}


def test_empty_history_refuses_success():
    with pytest.raises(ValueError, match="empty trajectory"):
        summarize_history([])


def test_observation_clock_must_match_its_snapshot():
    row = frame(0)
    row["food_accounting"]["completed_turn"] = 2
    with pytest.raises(ValueError, match="clock differs"):
        summarize_history([row])
