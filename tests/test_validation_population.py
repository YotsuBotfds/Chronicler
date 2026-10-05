"""Regression gate must measure living people separately from territorial polities."""
from copy import deepcopy

import pytest

from chronicler.validate import EVENT_NAME_TO_CODE, run_regression_summary
from chronicler.validation_gate import adjudicate_validation_report


def _run(population=100):
    counts = {"0": 40, "1": 20, "2": 20, "3": 10, "4": 10}
    return {
        "seed": 42,
        "bundle": {
            "metadata": {"seed": 42, "total_turns": 100},
            "world_state": {
                "turn": 100, "agent_mode": "hybrid",
                "regions": [{"name": "R", "population": population}],
            },
            "history": [
                {"civ_stats": {name: {"regions": [name], "gini": 0.5, "treasury": 10}
                               for name in ("A", "B", "C", "D")}},
                {"civ_stats": {name: {"regions": [name], "population": 1,
                                     "alive": True, "gini": 0.5, "treasury": 10}
                               for name in ("A", "B", "C")}},
            ],
        },
        "validation_summary": {
            "agent_aggregates_by_turn": {
                "100": {"A": {
                    "agent_count": 100, "satisfaction_mean": 0.405,
                    "satisfaction_std": 0.15, "gini": 0.5,
                    "controlled_agent_count": 100,
                    "occupation_counts": counts, "controlled_occupation_counts": counts,
                }},
            },
        },
        "events": ([{"event_type": EVENT_NAME_TO_CODE["migration"]}] * 450
                   + [{"event_type": EVENT_NAME_TO_CODE["rebellion"]}] * 250),
    }


def test_living_world_preserves_calibrated_pass_and_reports_actual_population():
    result = run_regression_summary([_run(1)])
    assert result["status"] == "PASS"
    assert result["regression_adjudication"] == "calibrated_floor"
    assert result["living_population_ok"] is True
    assert result["final_living_population_counts"] == [1]
    assert result["final_living_population_by_seed"][0] == {
        "seed": 42, "population": 1, "source": "world_state.regions", "turn": 100,
        "agent_mode": "hybrid", "reason": None,
    }
    assert result["extinct_world_count"] == 0
    assert result["extinct_world_fraction"] == 0.0
    assert result["population_evidence_run_fraction"] == 1.0


def test_extinct_world_fails_despite_territory_civ_floor_and_old_living_evidence():
    result = run_regression_summary([_run(0)])
    assert result["civ_survival_counts"] == [3]
    assert result["civ_zero_survival_fraction"] == 0.0
    assert result["final_living_population_counts"] == [0]
    assert result["extinct_world_count"] == 1
    assert result["extinct_world_fraction"] == 1.0
    assert result["living_population_ok"] is False
    assert result["reason"] == "terminal_population_extinction"
    assert result["status"] == "FAIL"
    assert result["calibrated_floor_failed_checks"] == ["living_population"]
    assert "living_population" in result["strict_regression_failed_checks"]


def test_terminal_empty_native_aggregate_is_zero_never_last_nonempty():
    run = _run()
    del run["bundle"]["world_state"]
    aggs = run["validation_summary"]["agent_aggregates_by_turn"]
    aggs["90"] = aggs["100"]
    aggs["100"] = {}
    result = run_regression_summary([run])
    assert result["final_living_population_counts"] == [0]
    assert result["final_living_population_by_seed"][0]["source"] == "terminal_agent_aggregate"
    assert result["extinct_world_count"] == 1
    assert result["calibrated_floor_failed_checks"] == ["living_population"]


def test_legacy_terminal_native_aggregate_can_supply_positive_evidence():
    run = _run()
    del run["bundle"]["world_state"]
    result = run_regression_summary([run])
    assert result["status"] == "PASS"
    assert result["final_living_population_counts"] == [100]
    assert result["final_living_population_by_seed"][0]["source"] == "terminal_agent_aggregate"


@pytest.mark.parametrize("mode", ["shadow", "demographics-only", "off", None])
def test_nonhybrid_region_population_is_not_native_agent_evidence(mode):
    run = _run(0)
    run["bundle"]["world_state"]["agent_mode"] = mode
    result = run_regression_summary([run])
    assert result["final_living_population_counts"] == [100]
    assert result["final_living_population_by_seed"][0]["source"] == "terminal_agent_aggregate"


@pytest.mark.parametrize("sample_turn", ["90", "110"])
def test_missing_terminal_native_aggregate_fails_closed(sample_turn):
    run = _run()
    del run["bundle"]["world_state"]
    aggs = run["validation_summary"]["agent_aggregates_by_turn"]
    aggs[sample_turn] = aggs.pop("100")
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["final_living_population_counts"] == [None]
    assert result["population_unknown_run_count"] == 1
    assert result["extinct_world_count"] == 0
    assert result["extinct_world_fraction"] is None
    assert result["reason"] == "missing_or_invalid_terminal_population_evidence"
    assert result["final_living_population_by_seed"][0]["reason"] == "missing_terminal_agent_aggregate"


@pytest.mark.parametrize("population", [None, -1, 1.5, True, "10", float("nan")])
def test_invalid_hybrid_region_counts_fail_closed_without_native_fallback(population):
    result = run_regression_summary([_run(population)])
    assert result["status"] == "FAIL"
    assert result["population_unknown_run_count"] == 1
    assert result["final_living_population_counts"] == [None]
    assert result["final_living_population_by_seed"][0]["reason"] == "invalid_final_region_population"


@pytest.mark.parametrize("count", [None, -1, 1.5, True, "10", float("nan")])
def test_invalid_terminal_aggregate_counts_fail_closed_without_crashing(count):
    run = _run()
    del run["bundle"]["world_state"]
    aggs = run["validation_summary"]["agent_aggregates_by_turn"]
    aggs["90"] = deepcopy(aggs["100"])
    aggs["100"]["A"]["agent_count"] = count
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["population_unknown_run_count"] == 1
    assert result["final_living_population_by_seed"][0]["reason"] == "invalid_terminal_agent_count"


def test_mismatched_world_state_terminal_turn_is_not_final_evidence():
    run = _run()
    run["bundle"]["world_state"]["turn"] = 90
    result = run_regression_summary([run])
    assert result["living_population_ok"] is False
    assert result["final_living_population_by_seed"][0]["reason"] == "world_state_turn_does_not_match_terminal_turn"


def test_batch_reports_extinction_fraction_and_unknown_evidence_separately():
    unknown = _run()
    del unknown["bundle"]["world_state"]
    aggs = unknown["validation_summary"]["agent_aggregates_by_turn"]
    aggs["90"] = aggs.pop("100")
    result = run_regression_summary([_run(10), _run(0), unknown])
    assert result["final_living_population_counts"] == [10, 0, None]
    assert result["extinct_world_count"] == 1
    assert result["extinct_world_fraction"] == 0.5
    assert result["population_unknown_run_count"] == 1
    assert result["population_evidence_run_fraction"] == 0.6667
    assert result["living_population_ok"] is False


def test_full_profile_rejects_extinction_while_subset_keeps_regression_informational():
    regression = run_regression_summary([_run(0)])
    report = {"results": {name: {"status": "PASS"} for name in
                          ("community", "needs", "cohort", "era", "artifacts", "arcs")}}
    report["results"]["regression"] = regression
    full = adjudicate_validation_report("full", report)
    assert full["ok"] is False
    assert full["required_failures"] == [{
        "oracle": "regression", "status": "FAIL", "adjudication": "fail",
        "reason": "terminal_population_extinction",
    }]
    subset = adjudicate_validation_report("subset", report)
    assert subset["ok"] is True
    assert subset["informational_non_pass"] == full["required_failures"]


def test_undated_hybrid_regions_cannot_override_terminal_native_extinction():
    run = _run(100)
    del run["bundle"]["world_state"]["turn"]
    aggs = run["validation_summary"]["agent_aggregates_by_turn"]
    aggs["90"] = aggs["100"]
    aggs["100"] = {}
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["living_population_ok"] is False
    assert result["final_living_population_counts"] == [0]
    assert result["final_living_population_by_seed"][0]["source"] == "terminal_agent_aggregate"
    assert result["calibrated_floor_failed_checks"] == ["living_population"]


def test_undated_hybrid_regions_can_use_verified_terminal_native_aggregate():
    run = _run(1)
    del run["bundle"]["world_state"]["turn"]
    result = run_regression_summary([run])
    assert result["status"] == "PASS"
    assert result["final_living_population_counts"] == [100]
    assert result["final_living_population_by_seed"][0]["source"] == "terminal_agent_aggregate"


def test_undated_hybrid_regions_without_terminal_native_evidence_fail_closed():
    run = _run(100)
    del run["bundle"]["world_state"]["turn"]
    aggs = run["validation_summary"]["agent_aggregates_by_turn"]
    aggs["90"] = aggs.pop("100")
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["living_population_ok"] is False
    assert result["final_living_population_counts"] == [None]
    assert result["final_living_population_by_seed"][0]["reason"] == "missing_terminal_agent_aggregate"


@pytest.mark.parametrize("terminal", [None, [], [{}], 0, 1, "", "invalid"])
def test_malformed_terminal_aggregate_returns_unknown_instead_of_crashing(terminal):
    run = _run()
    del run["bundle"]["world_state"]
    aggs = run["validation_summary"]["agent_aggregates_by_turn"]
    aggs["90"] = aggs["100"]
    aggs["100"] = terminal
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["living_population_ok"] is False
    assert result["population_unknown_run_count"] == 1
    assert result["extinct_world_count"] == 0
    assert result["final_living_population_counts"] == [None]
    assert result["final_living_population_by_seed"][0]["reason"] == "invalid_terminal_agent_aggregate"


@pytest.mark.parametrize("aggregates", [None, [], [{}], 0, 1, "", "invalid"])
def test_malformed_aggregate_container_returns_structured_unknown(aggregates):
    run = _run()
    del run["bundle"]["world_state"]
    run["validation_summary"]["agent_aggregates_by_turn"] = aggregates
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["living_population_ok"] is False
    assert result["population_unknown_run_count"] == 1
    assert result["final_living_population_by_seed"][0]["reason"] == "invalid_terminal_agent_aggregate"


@pytest.mark.parametrize("turn", [None, -1, 1.5, True, "100", "invalid", [], {}, float("nan")])
def test_invalid_terminal_turn_returns_structured_unknown(turn):
    run = _run()
    run["bundle"]["metadata"]["total_turns"] = turn
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["final_living_population_counts"] == [None]
    assert result["population_unknown_run_count"] == 1
    assert result["extinct_world_count"] == 0
    assert result["final_living_population_by_seed"][0]["reason"] == "missing_or_invalid_terminal_turn"


@pytest.mark.parametrize("key", ["invalid", "100.0", "-1", "0100", ""])
def test_invalid_aggregate_turn_key_cannot_substitute_for_terminal_evidence(key):
    run = _run()
    del run["bundle"]["world_state"]
    aggregates = run["validation_summary"]["agent_aggregates_by_turn"]
    aggregates[key] = aggregates.pop("100")
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["final_living_population_counts"] == [None]
    assert result["population_unknown_run_count"] == 1
    assert result["extinct_world_count"] == 0


def test_population_measurement_counts_uncontrolled_regions_without_mutating_input():
    run = _run()
    run["bundle"]["world_state"]["regions"] = [
        {"name": "Empty owned", "controller": "A", "population": 0},
        {"name": "Living unowned", "controller": None, "population": 7},
        {"name": "Living owned", "controller": "B", "population": 3},
    ]
    before = deepcopy(run)
    result = run_regression_summary([run])
    assert result["final_living_population_counts"] == [10]
    assert result["living_population_ok"] is True
    assert run == before


def _report(regression):
    report = {"results": {name: {"status": "PASS"} for name in
                          ("community", "needs", "cohort", "era", "artifacts", "arcs")}}
    report["results"]["regression"] = regression
    return report


@pytest.mark.parametrize("profile,exit_code", [("full", 2), ("subset", 0)])
def test_population_failure_propagates_through_gate_cli_and_decision_artifact(
    tmp_path, capsys, profile, exit_code,
):
    import json
    from chronicler.validation_gate import main

    report_path = tmp_path / "report.json"
    decision_path = tmp_path / "decision.json"
    report_path.write_text(json.dumps(_report(run_regression_summary([_run(0)]))))
    assert main(["--profile", profile, "--report", str(report_path),
                 "--decision-output", str(decision_path)]) == exit_code
    decision = json.loads(decision_path.read_text())
    assert json.loads(capsys.readouterr().out) == decision
    assert decision["ok"] is (profile == "subset")
    failure_key = "required_failures" if profile == "full" else "informational_non_pass"
    assert decision[failure_key][0]["reason"] == "terminal_population_extinction"


@pytest.mark.parametrize("profile,exit_code", [("full", 2), ("subset", 0)])
def test_population_failure_propagates_through_report_comparison(profile, exit_code):
    from chronicler.validation_compare import compare_validation_reports

    baseline = _report(run_regression_summary([_run(10)]))
    current = _report(run_regression_summary([_run(0)]))
    comparison = compare_validation_reports(
        profile, baseline, current, fail_on_regression=True,
    )
    assert comparison["exit_code"] == exit_code
    assert comparison["strict_regression_failed_checks_added"] == ["living_population"]
    assert comparison["regression_detected"] is (profile == "full")


@pytest.mark.parametrize("key", ["invalid", "0100", "100.0", "-1", " 100", 100])
def test_malformed_turn_cannot_rescue_failed_satisfaction_average(key):
    run = _run()
    aggregates = run["validation_summary"]["agent_aggregates_by_turn"]
    aggregates["90"] = deepcopy(aggregates["100"])
    aggregates["90"]["A"]["satisfaction_mean"] = 0.38
    before = run_regression_summary([run])
    assert before["status"] == "FAIL"
    aggregates[key] = deepcopy(aggregates["100"])
    aggregates[key]["A"]["satisfaction_mean"] = 0.43
    assert run_regression_summary([run]) == before


@pytest.mark.parametrize("world", [None, [], [{}], 0, 1, False, "", "invalid"])
def test_malformed_world_state_is_unknown_without_aggregate_fallback(world):
    run = _run()
    run["bundle"]["world_state"] = world
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["living_population_ok"] is False
    assert result["final_living_population_counts"] == [None]
    assert result["population_unknown_run_count"] == 1
    assert result["extinct_world_count"] == 0
    assert result["final_living_population_by_seed"][0]["reason"] == "invalid_world_state"


@pytest.mark.parametrize("summary", [None, [], [{}], 0, 1, False, "", "invalid"])
def test_malformed_validation_sidecar_is_unknown_without_terminal_regions(summary):
    run = _run()
    del run["bundle"]["world_state"]
    run["validation_summary"] = summary
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["final_living_population_counts"] == [None]
    assert result["population_unknown_run_count"] == 1
    assert result["extinct_world_count"] == 0


def test_malformed_sidecar_does_not_erase_valid_dated_hybrid_population():
    run = _run(7)
    run["validation_summary"] = ["invalid"]
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"  # Other regression evidence remains absent.
    assert result["living_population_ok"] is True
    assert result["final_living_population_counts"] == [7]


@pytest.mark.parametrize("metadata", [None, [], [{}], 0, 1, False, "", "invalid"])
def test_malformed_terminal_metadata_is_unknown_for_direct_summary_calls(metadata):
    run = _run()
    run["bundle"]["metadata"] = metadata
    result = run_regression_summary([run])
    assert result["status"] == "FAIL"
    assert result["final_living_population_counts"] == [None]
    assert result["extinct_world_count"] == 0
    assert result["final_living_population_by_seed"][0]["reason"] == "missing_or_invalid_terminal_turn"
