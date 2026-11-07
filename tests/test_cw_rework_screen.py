"""Constructed CWR1 extraction/control contracts; no held execution."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import random

import pytest


@pytest.fixture(scope="module")
def RW():
    path = Path(__file__).resolve().parents[1] / "scripts/cw_rework_screen.py"
    spec = importlib.util.spec_from_file_location("cw_rework_screen_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle(RW, arm="AD"):
    """A small interface fixture, not a naturally simulated story world."""
    from chronicler.reform_services_state import ReliefFrame
    from chronicler.guild_leagues_state import LeagueFrame
    from chronicler.movement_branches_state import BranchFrame

    flags = RW.ARMS[arm][0]
    mode = RW.option(flags, "--adaptive-livelihoods-mode", "adapt")
    channels = RW.option(flags, "--adaptive-livelihoods-decision-channels", "all")
    crowding = RW.option(flags, "--public-health-crowding", "density_only")
    health_mode = RW.option(flags, "--public-health-mode", "active")
    retail_mode = RW.option(flags, "--household-retail-mode", "retail")

    def record(**fields):
        return {"schema_version": 1, "source_turn": 0, **fields}

    wealth = {"turn": 0, "continuity": {}, "typed_complete": True,
        "world": {"open": 100, "delta": 0, "deaths": 2, "close": 100},
        "regions": [], "typed": [], "closures": [], "withheld": {}, "treasury": {},
        "native": {"source_turn": 0, "observed_complete": True, "balance_closure": 0,
                   "totals": {"income_gross": 3, "income_applied": 1, "withheld_paid_work": 2, "decay": -1}}}
    personal = [] if mode == "record_only" or channels == "no_migration_experience" else [[7, 1, -.1]]
    d3 = [[7, 1, .2]]
    a6 = {"turn": 0, "decision_channels": channels, "rows": [[7, 1, .1 if personal else .2]],
        "rows_total": 1, "rows_installed": 1, "rows_dropped": 0,
        "a6_rows": personal, "a6_rows_total": len(personal), "d3_rows": d3, "d3_rows_total": 1,
        "migration_rows_would": [[7, 1, -.1]], "migration_rows_would_total": 1,
        "known_destinations": [[7, 1, 1]], "known_destinations_total": 1, "known_destinations_dropped": 0,
        "information_gate_installed": mode != "record_only" and channels != "no_information",
        "receipt": [0, [], 1, 1], "refusals_total": 0, "refusals": [], "work": [], "work_dropped": 0,
        "offers": [{"turn": 0, "id": 7, "kind": "academy_training", "would_decline": True,
                    "accepted": mode == "record_only" or channels == "no_work"}]}
    d4 = {"turn": 0, "events_dropped": 0, "events": [
        {"source_turn": 0, "kind": "refill", "army": "a", "removed_milli": 1000, "credited_rations": 2},
        {"source_turn": 0, "kind": "consumption", "army": "a", "consumed_rations": 2,
         "demanded_rations": 3, "adequacy": 2 / 3}], "claims_due_milli": 0}
    arrivals = {"window_turns": 20, "coverage_complete": True, "window_complete": False, "complete": False}
    x1_totals = {"moves": 0, "moves_other": 0, "opened": 0, "displaced": 0,
                 "recent_residence_arrivals": 0, "recent_residence_arrivals_unknown_reason": 0}
    x1_regions = [{"region": 0, "residents": 100, "displaced": 0,
                   "recent_residence_arrivals": 0, "recent_residence_arrivals_unknown_reason": 0}]
    ph = record(enabled=True, mode=health_mode, policy="evidence", crowding=crowding, report_delay=0,
        report_turn=0, reports=[], decisions=[], environment_turn=0,
        environment=[{"region": rid, "source_turn": -1, "residence_observed": False,
            "sanitation_observed": False, "water_service": 0, "displaced_share": 0, "crowding_factor": 1,
            "crowding_basis": crowding, "crowding_source_turn": 0 if crowding == "density_only" else -1,
            "flux_factor": 1, "recent_arrival_share": None,
            "arrival_diagnostics_complete": None} for rid in range(2)],
        supply_turn=0, supplies=[], guard_turn=0, guards=[], guard_capacity_turn=0, guard_capacity=[],
        funding_turn=0, funding=[{"turn": 0, "civ": 0, "envelope_milli": 4000,
            "care_paid_milli": 0, "care_cash_milli": 0, "care_carry_before": 0, "care_carry_after": 0,
            "guard_paid_milli": 0, "guard_cash_milli": 0, "guard_carry_before": 0, "guard_carry_after": 0,
            "supply_cash_milli": 0}], totals={})
    care = record(mode="care" if health_mode == "active" else "cost_only", tick={"turn": 0,
        "refused": [], "regions": [{"region": 0, "deaths": 2, "infectious_pt": 20,
                                    "pathogens": [[0, 2, 20]]}], "applied": []}, frame=[],
        ledger=[{"turn": 0, "civ": 0, "envelope_coins": 4, "paid_milli": 0}])
    provisioning = {"region": 0, "persons": 100, "deficit": 50 if retail_mode == "retail" else 100,
        "priced_out_deficit": 20 if retail_mode == "retail" else 0,
        "offer_short_deficit": 30 if retail_mode == "retail" else 100,
        "free_given": 50 if retail_mode == "retail" else 0, "rations": 50 if retail_mode == "retail" else 0}
    retail = record(mode=retail_mode, boundary="all", rules_version=2,
        parameters={"theta": .9 if retail_mode == "retail" else 1},
        regions=[{"region": 0, "open_milli": 0, "close_milli": 0, "flows": {}, "provisioning": provisioning}],
        money={"paid_milli": 0}, income={"replaced": 0})
    lv = {"wealth_accounting": record(stage="A1", frame=wealth),
        "adaptive_livelihoods": record(mode=mode, rules="3", decision_channels=channels, frame=a6, counters={}),
        "war_consequences": record(mode="active", frame={"turn": 0, "events": [], "events_dropped": 0,
                                                       "separation": None}, counters={}),
        "war_requisition": record(mode="transfer", frame=d4, counters={}),
        "infrastructure_condition": record(mode="repair", assets=[{"status": "serving", "service": .5}], receipts=[]),
        "harvest_cover": record(mode="loss", rows=[]),
        "timber_orders": record(frame={"turn": 0}, orders=[], closed=[], counters={}),
        "reform_services": record(stage="D1a", mode="service", frame=ReliefFrame(turn=0).model_dump()),
        "guild_leagues": record(stage="D1b", mode="mutual", frame=LeagueFrame(turn=0).model_dump()),
        "movement_branches": record(stage="D1c", mode="funded", frame=BranchFrame(turn=0).model_dump()),
        "residence_ledger": record(frame={"turn": 0, "observed_from": 0, "totals": x1_totals,
                                         "regions": x1_regions, "arrival_diagnostics": arrivals}),
        "public_health": ph, "epidemic_care": care, "household_retail": retail}
    food_rows = []
    for rid in range(2):
        consumed = 25 if rid == 0 and retail_mode == "retail" else 0
        opening = 25 if rid == 0 else 0
        native = {"opening": opening, "produced": 0, "transport_net": 0, "craft_input": 0,
            "clamp_correction": 0, "pre_consumption": opening, "consumed": consumed, "storage_loss": 0,
            "cap_overflow": 0, "closing": opening - consumed, "demand": 50 if rid == 0 else 0,
            "sufficiency": .5 if rid == 0 else 1, "balance_residual": 0,
            "balance_tolerance": 1e-5 * max(1, opening + consumed)}
        food_rows.append({"region_id": rid, "native_count": 100 if rid == 0 else 0,
            "native": native, "sufficiency_after_relief": .5 if rid == 0 else 1, "public": {"released": 0}})
    rules = {"schema_version": 1, "mode": "closure", "channels": ["trade", "migration"],
        "receipt": {"turn": 0, "migrants_blocked": 0, "migrants_blocked_flight": 0, "migrants_blocked_hunger": 0},
        "totals": {"route_turns_removed": 0, "forgone_income": 0, "closed_pair_turns": 0}}
    snap = {"turn": 1, "regional_population": {"source_turn": 0, "counts": [100, 0]}, "livelihoods": lv,
        "health_care": {"source_turn": 0, "episodes": 2, "new_injuries": 1}, "campaign": {"battles": []},
        "migration": [], "food_accounting": {"source_turn": 0, "regions": food_rows},
        "epidemics": {"active": [], "deaths": 2, "deaths_total": 2, "quarantine_rules": rules}}
    return {"metadata": {"seed": 7, "total_turns": 1},
        "world_state": {"seed": 7, "regions": [{"name": "A"}, {"name": "B"}],
                        "civilizations": [{"name": "A"}, {"name": "B"}]},
        "history": [snap], "events_timeline": [],
        "_cw6_events": {"present": True, "migration": 0, "unknown": 0, "deaths": 2,
                        "bytes": 1, "sha256": "a" * 64, "turn_min": 0, "turn_max": 0}}


def test_twelve_matched_arms_preserve_d3_and_enrollment(RW):
    assert len(RW.ARMS) == 12 and len(RW.SCREEN.primaries()) == 3
    assert RW.SCREEN.root == "RD"
    assert RW.SCREEN.held == {"template": tuple(range(4101, 4107)), "procedural": tuple(range(4201, 4207))}
    assert RW.SR.check_preregistration(RW.SCREEN, held=False) == []
    assert RW.BASE[RW.BASE.index("--adaptive-livelihoods-rules") + 1] == "3"
    assert RW.BASE[RW.BASE.index("--household-retail-boundary") + 1] == "all"
    for name, (flags, _control) in RW.ARMS.items():
        assert "--no-adaptive-livelihoods" not in flags
        assert RW.option(flags, "--war-consequences-mode", "active") == "active", name


@pytest.mark.parametrize("arm", ["RD", "AD", "RL", "AL", "MX", "IX", "WX", "TX", "RPC", "APC", "RNR", "ANR"])
def test_each_control_accepts_nonzero_d3_and_retains_requested_schema(RW, arm):
    m, problems = RW.extract(bundle(RW, arm), RW.ARMS[arm][0])
    assert problems == []
    assert m["food_shortfall"] == 25 and m["epidemic_deaths"] == 2
    assert m["d3_input_rows"] == 1 and m["combined_native_choice_changes"] == 1
    assert m["army_hunger_ration_turns"] == 1
    assert m["retail_access_deficit"] == (100 if arm in ("RNR", "ANR") else 50)


def test_record_only_does_not_mean_no_combined_native_effect(RW):
    b = bundle(RW, "RD")
    m, problems = RW.extract(b, RW.ARMS["RD"][0])
    assert problems == [] and m["a6_personal_rows"] == 0 and m["d3_input_rows"] == 1
    b["history"][0]["livelihoods"]["adaptive_livelihoods"]["frame"]["rows"] = []
    assert any("sample/count" in p or "contributions" in p for p in RW.extract(b, RW.ARMS["RD"][0])[1])


@pytest.mark.parametrize("mutation,fragment", [
    ("rules2", "rules-3"), ("source", "rules-3"), ("channel", "channel"),
    ("merged", "contributions"), ("d3_missing", "sample/count"), ("personal_disabled", "disabled personal"),
    ("information", "migration-information"), ("work_disabled", "disabled work"), ("trade_disabled", "disabled trade"),
    ("unknown_cost", "unknown personal cost"), ("food_mint", "stock-flow"), ("food_negative", "negative"),
    ("retail_mode", "food-access regime"), ("retail_mint", "owned-food"), ("metadata", "total_turns"),
    ("native_mint", "source does not close"), ("duplicate_meal", "duplicate"), ("clock", "misdated"),
])
def test_failed_controls_and_closures_are_visible(RW, mutation, fragment):
    arm = {"channel": "MX", "personal_disabled": "MX", "information": "IX", "work_disabled": "WX", "trade_disabled": "TX"}.get(mutation, "AD")
    b = bundle(RW, arm)
    lv = b["history"][0]["livelihoods"]
    a = lv["adaptive_livelihoods"]
    f = a["frame"]
    if mutation == "rules2": a["rules"] = "2"
    elif mutation == "source": a["source_turn"] = 1
    elif mutation == "channel": f["decision_channels"] = "all"
    elif mutation == "merged": f["rows"][0][2] = .25
    elif mutation == "d3_missing": del f["d3_rows"]
    elif mutation == "personal_disabled": f.update(a6_rows=[[7, 1, -.1]], a6_rows_total=1)
    elif mutation == "information": f["information_gate_installed"] = True
    elif mutation == "work_disabled": f["offers"][0]["accepted"] = False
    elif mutation == "trade_disabled": a["counters"]["trade_unknown_destination"] = 1
    elif mutation == "unknown_cost": f["work"] = [{"turn": 0, "id": 7, "kind": "repair", "paid_milli": 2000,
            "withheld_milli": None, "title_forgone_milli": 0, "net_milli": 2000, "progress": None, "source": "individual"}]
    elif mutation == "food_mint": b["history"][0]["food_accounting"]["regions"][0]["native"]["closing"] += 1
    elif mutation == "food_negative": b["history"][0]["food_accounting"]["regions"][0]["native"]["opening"] = -25
    elif mutation == "retail_mode": lv["household_retail"]["mode"] = "free_exchange"
    elif mutation == "retail_mint": lv["household_retail"]["regions"][0]["close_milli"] = 1
    elif mutation == "metadata": b["metadata"]["total_turns"] = 2
    elif mutation == "native_mint": lv["war_requisition"]["frame"]["events"][0]["credited_rations"] = 3
    elif mutation == "duplicate_meal": lv["war_requisition"]["frame"]["events"].append(deepcopy(lv["war_requisition"]["frame"]["events"][1]))
    else: lv["war_requisition"]["source_turn"] = 1
    assert any(fragment in p for p in RW.extract(b, RW.ARMS[arm][0])[1])


def test_incomplete_arrival_observation_never_becomes_a_ratio(RW):
    b = bundle(RW)
    row = b["history"][0]["livelihoods"]["public_health"]["environment"][0]
    row["recent_arrival_share"] = 0
    assert any("incomplete factual" in p for p in RW.extract(b, RW.ARMS["AD"][0])[1])


def two_turns(RW, arm="AD"):
    b = bundle(RW, arm)
    first = b["history"][0]
    first["livelihoods"]["residence_ledger"]["frame"]["totals"]["displaced"] = 20
    first["livelihoods"]["residence_ledger"]["frame"]["regions"][0]["displaced"] = 20
    second = deepcopy(first)
    second["turn"] = 2
    for key in ("regional_population", "health_care", "food_accounting"):
        second[key]["source_turn"] = 1
    second["epidemics"]["deaths_total"] = 4
    second["epidemics"]["quarantine_rules"]["receipt"]["turn"] = 1
    for name, record in second["livelihoods"].items():
        record["source_turn"] = 1
        if isinstance(record.get("frame"), dict):
            record["frame"]["turn"] = 1
    lv = second["livelihoods"]
    lv["wealth_accounting"]["frame"]["native"]["source_turn"] = 1
    lv["wealth_accounting"]["frame"]["continuity"] = {"status": "exact"}
    af = lv["adaptive_livelihoods"]["frame"]
    af["receipt"][0] = 1
    for row in af["offers"]:
        row["turn"] = 1
    for event in lv["war_requisition"]["frame"]["events"]:
        event["source_turn"] = 1
    care = lv["epidemic_care"]
    care["tick"]["turn"] = 1
    care["ledger"][0]["turn"] = 1
    ph = lv["public_health"]
    for key in ("report_turn", "environment_turn", "supply_turn", "guard_turn", "guard_capacity_turn", "funding_turn"):
        ph[key] = 1
    ph["funding"][0]["turn"] = 1
    for row in ph["environment"]:
        row.update(source_turn=0, residence_observed=True, arrival_diagnostics_complete=False)
        row["crowding_source_turn"] = 1 if row["crowding_basis"] == "density_only" else 0
        row["displaced_share"] = .2 if row["region"] == 0 else 0
        if row["crowding_basis"] == "legacy_displacement":
            row["crowding_factor"] = 1 + .25 * row["displaced_share"]
    b["history"].append(second)
    b["metadata"]["total_turns"] = 2
    b["_cw6_events"].update(deaths=4, turn_max=1)
    return b


def test_environment_is_bound_to_prior_frame_and_density_ignores_classification(RW):
    fixed, p1 = RW.extract(two_turns(RW, "AD"), RW.ARMS["AD"][0])
    legacy, p2 = RW.extract(two_turns(RW, "AL"), RW.ARMS["AL"][0])
    assert p1 == p2 == []
    assert fixed["added_crowding_factor_sum"] == 0
    assert legacy["added_crowding_factor_sum"] == pytest.approx(.05)
    b = two_turns(RW)
    b["history"][1]["livelihoods"]["public_health"]["environment"][0]["displaced_share"] = 0
    assert any("preceding X1 frame" in p for p in RW.extract(b, RW.ARMS["AD"][0])[1])
    b = two_turns(RW)
    b["history"][1]["livelihoods"]["public_health"]["environment"][0]["source_turn"] = 1
    assert any("T-1" in p or "preceding X1 frame" in p for p in RW.extract(b, RW.ARMS["AD"][0])[1])


def test_factual_window_requires_twenty_fully_observed_writes(RW):
    b = bundle(RW)
    b["history"][0]["livelihoods"]["residence_ledger"]["frame"]["arrival_diagnostics"].update(
        window_complete=True, complete=True)
    assert any("20-write" in p for p in RW.extract(b, RW.ARMS["AD"][0])[1])


def test_food_availability_and_individual_access_are_separate(RW):
    normal, p1 = RW.extract(bundle(RW), RW.ARMS["AD"][0])
    changed, p2 = RW.extract(bundle(RW, "ANR"), RW.ARMS["ANR"][0])
    assert not p1 and not p2
    assert normal["food_shortfall"] == changed["food_shortfall"]
    assert normal["retail_access_deficit"] != changed["retail_access_deficit"]
    b = bundle(RW)
    b["history"][0]["livelihoods"]["household_retail"]["regions"][0]["provisioning"] = None
    m, problems = RW.extract(b, RW.ARMS["AD"][0])
    assert not problems and m["retail_access_deficit"] is None
    assert m["retail_access_unknown_region_turns"] == 1


def test_horizon_and_world_identity_cannot_be_blessed_by_metadata(RW):
    b = bundle(RW)
    assert any("requested screen horizon" in p for p in RW.extract(b, RW.ARMS["AD"][0], expected_turns=120)[1])
    b["_cwr_expected_world"] = {"seed": 9, "stratum": "t", "arm": "AD"}
    assert any("requested screen seed/stratum" in p for p in RW.extract(b, RW.ARMS["AD"][0])[1])


def test_primary_and_interaction_signs_use_whole_matched_worlds(RW):
    full = {"m": {"food_shortfall": 9, "epidemic_deaths": 8}}
    control = {"m": {"food_shortfall": 4, "epidemic_deaths": 3}}
    first = RW.SCREEN.primaries()[0]
    assert first.arm == "AD" and first.control == "RD" and first.read(full) - first.read(control) == 5
    interaction = RW.SCREEN.primaries()[2]
    assert interaction.arm == "AL" and interaction.control == "RL" and interaction.minus == ("AD", "RD")
    assert RW.activation({}, ()) == (True, "Every enrolled world enters; actual mechanism activation is reported separately")


def test_serial_budget_and_all_arm_evidence_cannot_be_silently_narrowed(RW):
    assert RW.resource_args(["run", "out"])[-2:] == ["--jobs", "1"]
    with pytest.raises(ValueError, match="exactly one"):
        RW.resource_args(["run", "out", "--jobs=2"])
    with pytest.raises(ValueError, match="every preregistered arm"):
        RW.resource_args(["run", "out", "--cohort", "held", "--arms", "AD,RD"])
    assert RW.resource_args(["run", "out", "--cohort", "dev", "--arms", "AD"])[-2:] == ["--jobs", "1"]


def test_paired_bootstrap_is_deterministic_analysis_not_simulation_rng(RW):
    before = random.getstate()
    assert RW.paired_bootstrap([0, 0, 0]) == (0, 0)
    assert RW.paired_bootstrap([1, 2, 3]) == RW.paired_bootstrap([1, 2, 3])
    assert RW.paired_bootstrap([]) is None
    assert random.getstate() == before


def test_generic_reader_is_restored_and_dev_horizon_is_explicit(RW, monkeypatch):
    old = RW.SR.load_bundle_file
    captured = {}
    def fake(argv, screens, **_kwargs):
        captured["screen"] = screens["CWR1"]
        assert RW.SR.load_bundle_file is RW.load_bundle_file
        return 0
    monkeypatch.setattr(RW.SR, "main", fake)
    assert RW.main(["run", "out", "--cohort", "dev", "--turns=1"]) == 0
    assert RW.SR.load_bundle_file is old
    assert captured["screen"].extract(bundle(RW), RW.ARMS["AD"][0])[1] == []
    assert any("requested screen horizon" in p for p in RW.SCREEN.extract(bundle(RW), RW.ARMS["AD"][0])[1])
