"""CW6 extractor and resume-selection contracts; no held-world execution."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def CW():
    path = Path(__file__).resolve().parents[1] / "scripts/cw_integrated_screen.py"
    spec = importlib.util.spec_from_file_location("cw_integrated_screen_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle():
    from chronicler.reform_services_state import ReliefFrame
    from chronicler.guild_leagues_state import LeagueFrame
    def record(**fields):
        return {"schema_version": 1, "source_turn": 0, **fields}
    wealth = {"turn": 0, "continuity": {}, "typed_complete": True, "world": {"open": 100, "delta": 2, "deaths": 1, "close": 102},
              "regions": [], "typed": [{"channel": "care_wage", "in_milli": 100}], "closures": [], "withheld": {},
              "treasury": {}, "native": {"source_turn": 0, "observed_complete": True, "balance_closure": 0,
                                         "totals": {"income_gross": 3, "income_applied": 1, "withheld_paid_work": 2}}}
    a6 = {"turn": 0, "rows_installed": 0, "rows_dropped": 0, "information_gate_installed": True,
          "receipt": [0, [], 0, 0], "refusals_total": 0, "refusals": [], "work": [], "work_dropped": 0, "offers": []}
    d4 = {"turn": 0, "events_dropped": 0, "events": [
        {"source_turn": 0, "kind": "refill", "army": "a", "removed_milli": 1000, "credited_rations": 2},
        {"source_turn": 0, "kind": "consumption", "army": "a", "consumed_rations": 2, "demanded_rations": 3,
         "adequacy": 2 / 3}], "claims_due_milli": 0}
    lv = {"wealth_accounting": record(stage="A1", frame=wealth),
          "adaptive_livelihoods": record(mode="adapt", frame=a6),
          "war_consequences": record(mode="active", frame={"turn": 0, "events": [], "events_dropped": 0, "separation": None}, counters={}),
          "war_requisition": record(mode="transfer", frame=d4, counters={}),
          "infrastructure_condition": record(mode="repair", assets=[{"status": "serving", "service": .5}], receipts=[]),
          "harvest_cover": record(mode="loss", rows=[]),
          "timber_orders": record(frame={"turn": 0}, orders=[], closed=[], counters={}),
          "reform_services": record(stage="D1a", mode="service", frame=ReliefFrame(turn=0).model_dump()),
          "guild_leagues": record(stage="D1b", mode="mutual", frame=LeagueFrame(turn=0).model_dump()),
          "residence_ledger": record(frame={"turn": 0, "totals": {"moves": 1, "moves_other": 1, "opened": 0, "displaced": 0}})}
    snap = {"turn": 1, "regional_population": {"source_turn": 0, "counts": [100, 0]}, "livelihoods": lv,
            "health_care": {"source_turn": 0, "episodes": 2, "new_injuries": 1}, "campaign": {"battles": []},
            "migration": [[0, 1, 1]]}
    return {"world_state": {"regions": [{"name": "A"}, {"name": "B"}]}, "history": [snap],
            "_cw6_events": {"present": True, "migration": 1, "unknown": 1, "deaths": 1, "bytes": 1, "sha256": "a" * 64,
                            "turn_min": 0, "turn_max": 0}}


def test_five_arms_three_unconditioned_primaries_and_fixed_enrollment(CW):
    assert len(CW.SCREEN.arms) == 5 and len(CW.SCREEN.primaries()) == 3
    assert CW.SCREEN.held == {"template": tuple(range(781, 787)), "procedural": tuple(range(881, 887))}
    assert CW.BASE[CW.BASE.index("--household-retail-boundary") + 1] == "all"
    assert CW.SR.check_screen(CW.SCREEN) == []
    assert CW.activation({}, ()) == (True, "Every enrolled world, including zero mechanism activation; validation is separate")


def test_world_outcomes_and_unknown_cause_are_not_conditioned_on_activation(CW):
    m, problems = CW.extract(bundle(), CW.ARMS["FULL"][0])
    assert problems == []
    assert m["balance_change_per_1000_pt"] == 20 and m["deaths_per_1000_pt"] == 10
    assert m["service_per_region_turn"] == .25 and m["army_hunger_ration_turns"] == 1
    assert m["unknown_migration_share"] == 1 and m["x1_opened_spells"] == 0
    assert m["a6_input_rows"] == 0


@pytest.mark.parametrize("breakage,fragment", [
    ("date", "misdated"), ("closure", "incomplete"), ("duplicate_meal", "duplicate"),
    ("food_mint", "source does not close"), ("drop", "dropped events"),
    ("sidecar", "sidecar count"), ("control", "control mode"), ("a1_date", "wealth frame/source misdated"),
    ("a1_typed", "typed coverage incomplete"), ("a1_delta", "balances do not close")])
def test_strict_schema_dates_controls_and_physical_failures_are_visible(CW, breakage, fragment):
    b = bundle()
    lv = b["history"][0]["livelihoods"]
    if breakage == "date":
        lv["war_requisition"]["source_turn"] = 1
    elif breakage == "closure":
        lv["wealth_accounting"]["frame"]["native"]["observed_complete"] = False
    elif breakage == "duplicate_meal":
        lv["war_requisition"]["frame"]["events"].append(deepcopy(lv["war_requisition"]["frame"]["events"][1]))
    elif breakage == "food_mint":
        lv["war_requisition"]["frame"]["events"][0]["credited_rations"] = 3
    elif breakage == "drop":
        lv["war_requisition"]["frame"]["events_dropped"] = 1
    elif breakage == "sidecar":
        b["_cw6_events"]["migration"] = 0
    elif breakage == "a1_date":
        lv["wealth_accounting"]["source_turn"] = lv["wealth_accounting"]["frame"]["turn"] = 1
    elif breakage == "a1_typed":
        lv["wealth_accounting"]["frame"]["typed_complete"] = False
    elif breakage == "a1_delta":
        lv["wealth_accounting"]["frame"]["world"]["delta"] = 1
    else:
        lv["adaptive_livelihoods"]["mode"] = "record_only"
    _, problems = CW.extract(b, CW.ARMS["FULL"][0])
    assert any(fragment in p for p in problems), problems


def test_generic_control_tree_still_reports_labeled_full_minus_control(CW):
    o = CW.SCREEN.primaries()[0]
    full = {"m": {"balance_change_per_1000_pt": 7}}
    control = {"m": {"balance_change_per_1000_pt": 4}}
    assert o.arm == "A6R" and o.control == "FULL"
    assert o.read(control) - o.read(full) == 3


def test_preregistered_serial_runtime_does_not_inherit_three_job_default(CW):
    assert CW.serial_run_args(["run", "out"])[-2:] == ["--jobs", "1"]
    assert CW.serial_run_args(["run", "out", "--jobs=1"])[-1] == "--jobs=1"
    with pytest.raises(ValueError, match="exactly one"):
        CW.serial_run_args(["run", "out", "--jobs", "2"])


def test_sidecar_counts_untruncated_migrations_and_unknown_provenance(CW, tmp_path):
    import pyarrow as pa
    import pyarrow.ipc as ipc
    path = tmp_path / "agent_events.arrow"
    batch = pa.record_batch({"turn": [0, 0, 1], "event_type": ["migration", "death", "migration"],
                             "migration_driver": [255, 255, 3]})
    with ipc.new_file(path, batch.schema) as writer:
        writer.write_batch(batch)
    result = CW.event_sidecar(path)
    assert result["migration"] == 2 and result["unknown"] == 1 and result["deaths"] == 1
    assert result["bytes"] > 0 and len(result["sha256"]) == 64


def test_resume_selects_actual_live_state_and_keeps_missing_coverage_explicit(CW):
    path = Path(__file__).resolve().parents[1] / "scripts/cw_integrated_resume.py"
    spec = importlib.util.spec_from_file_location("cw_integrated_resume_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    b = bundle()
    b["history"].extend({"turn": turn, "livelihoods": {}} for turn in range(2, 8))
    b["history"][3]["livelihoods"]["timber_orders"] = {"orders": [
        {"status": "moving", "cargo_milli": 500, "cash": 10}]}
    b["history"][6]["livelihoods"]["war_consequences"] = {"frame": {"events": [{"kind": "wounded"}]}}
    selection = module.transition_points(b)
    assert selection["categories"]["army_meal_or_requisition"] == 1
    assert selection["categories"]["moving_timber_escrow"] == 4
    assert selection["ks"] == [1, 3, 4]
    assert selection["not_resumable"] == ["war_injury_or_release"]
    assert "dated_health_report_or_guard" in selection["missing"]
    cli = module.cli_for("procedural", 19)
    assert "--watershed" in cli and cli[cli.index("--seed") + 1] == "19"
    assert "--turns" not in cli and "--simulate-only" not in cli
    b["history"][4]["livelihoods"]["public_health"] = {"guards": [{"members": [{"wage_paid_milli": 250}]}]}
    assert module.transition_points(b)["categories"]["dated_health_report_or_guard"] == 5
    b["history"][4]["livelihoods"]["infrastructure_condition"] = {"receipts": [{"delivered": 1, "coin_cost_milli": 10}]}
    assert "paid_infrastructure_work" in module.transition_points(b)["missing"]
    b["history"][4]["livelihoods"]["infrastructure_condition"]["receipts"][0]["members"] = [{"worked": .5, "wages_milli": 100}]
    assert module.transition_points(b)["categories"]["paid_infrastructure_work"] == 5
    pilot = {"metadata": {"seed": 5}, "world_state": {"seed": 5, "regions": [{}] * 8}}
    module.validate_pilot_world(pilot, "template", 5)
    with pytest.raises(ValueError, match="seed differs"):
        module.validate_pilot_world(pilot, "procedural", 19)
    pilot["world_state"]["geography"] = {"generator": "procedural"}
    with pytest.raises(ValueError, match="geography"):
        module.validate_pilot_world(pilot, "template", 5)


def test_absent_sidecar_is_unknown_evidence_even_without_migration(CW):
    b = bundle()
    b["history"][0]["migration"] = []
    b["_cw6_events"] = {"present": False, "migration": 0, "deaths": 1, "unknown": 0, "bytes": 0, "sha256": None}
    _, problems = CW.extract(b, CW.ARMS["FULL"][0])
    assert any("absent or missing valid identity" in reason for reason in problems)


@pytest.mark.parametrize("changed", ["cli", "turns", "transitions", "sidecar"])
def test_resume_rejects_modified_plan_configuration(CW, changed):
    path = Path(__file__).resolve().parents[1] / "scripts/cw_integrated_resume.py"
    spec = importlib.util.spec_from_file_location("cw_integrated_resume_plan_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    b = {"metadata": {"seed": 5, "total_turns": 200}, "world_state": {"seed": 5, "regions": [{}] * 8},
         "history": [{"turn": t, "livelihoods": {}} for t in range(1, 201)], "_cw6_events": {"present": True, "sha256": "a" * 64}}
    plan = {"stratum": "template", "seed": 5, "turns": 200, "cli": module.cli_for("template", 5),
            "transitions": module.transition_points(b), "event_sidecar": deepcopy(b["_cw6_events"])}
    module.validate_plan_configuration(plan, b)
    if changed == "cli":
        plan["cli"].append("--no-adaptive-livelihoods")
    elif changed == "turns":
        plan["turns"] = 100
    elif changed == "transitions":
        plan["transitions"]["ks"] = [2]
    else:
        b["_cw6_events"]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="resume plan"):
        module.validate_plan_configuration(plan, b)
