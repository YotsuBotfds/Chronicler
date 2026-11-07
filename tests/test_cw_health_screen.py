"""Strict health screen contract checks; constructed bundles, no held worlds."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture(scope="module")
def CW():
    path = Path(__file__).resolve().parents[1] / "scripts/cw_health_screen.py"
    spec = importlib.util.spec_from_file_location("cw_health_screen_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bundle(mode="active", policy="evidence"):
    ph = {"schema_version": 1, "enabled": True, "source_turn": 0, "mode": mode, "policy": policy,
          "report_delay": 0, "report_turn": 0, "reports": [], "decisions": [], "environment_turn": 0,
          "environment": [{"region": 0, "source_turn": -1, "residence_observed": False,
                           "sanitation_observed": False, "water_service": 0, "displaced_share": 0,
                           "crowding_factor": 1, "flux_factor": 1}], "supply_turn": 0, "supplies": [],
          "guard_turn": 0, "guards": [], "guard_capacity_turn": 0, "guard_capacity": [], "totals": {}}
    ph.update(funding_turn=0, funding=[{"turn": 0, "civ": 0, "envelope_milli": 4000,
        "care_paid_milli": 0, "care_cash_milli": 0, "care_carry_before": 0, "care_carry_after": 0,
        "supply_cash_milli": 0, "guard_paid_milli": 0, "guard_cash_milli": 0,
        "guard_carry_before": 0, "guard_carry_after": 0}])
    care = {"schema_version": 1, "source_turn": 0, "mode": "care" if mode == "active" else "cost_only",
            "tick": {"turn": 0, "refused": [], "regions": [{"region": 0, "deaths": 2,
                     "infectious_pt": 20, "pathogens": [[0, 2, 20]]}], "applied": []}, "frame": [],
            "ledger": [{"turn": 0, "civ": 0, "envelope_coins": 4, "paid_milli": 0}]}
    rules = {"schema_version": 1, "mode": "closure", "channels": ["trade", "migration"], "receipt": {"turn": 0, "migrants_blocked": 0,
             "migrants_blocked_flight": 0, "migrants_blocked_hunger": 0}, "totals": {
             "route_turns_removed": 0, "forgone_income": 0, "closed_pair_turns": 0}}
    snap = {"turn": 1, "regional_population": {"source_turn": 0, "counts": [100]},
            "epidemics": {"active": [], "deaths": 2, "deaths_total": 2, "quarantine_rules": rules},
            "livelihoods": {"public_health": ph, "epidemic_care": care},
            "food_accounting": {"source_turn": 0, "regions": [{"sufficiency_after_relief": .5}]}}
    return {"world_state": {"regions": [{"name": "A"}], "civilizations": [{"name": "A"}, {"name": "B"}]},
            "history": [snap], "events_timeline": [
            {"event_type": "epidemic_arrival", "actors": ["A", "B"], "turn": 0},
            {"event_type": "epidemic_arrival", "actors": ["A"], "turn": 0}]}


def _ph(b):
    return b["history"][0]["livelihoods"]["public_health"]


def _care(b):
    return b["history"][0]["livelihoods"]["epidemic_care"]


def test_three_fresh_arms_three_unconditioned_primaries(CW):
    s = CW.SCREEN
    assert s.held == {"template": tuple(range(3901, 3907)), "procedural": tuple(range(4001, 4007))}
    assert len(s.primaries()) == 3
    assert s.arms["PA"][1] == "PS" and s.arms["PS"][1] == "PC" and s.root == "PC"
    assert CW.SR.check_preregistration(s, held=False) == []
    assert "--simulate-only" in s.base and s.base[s.base.index("--turns") + 1] == "200"
    assert "--public-health-mode" not in s.base


def test_runtime_does_not_inherit_three_job_default(CW):
    assert CW.resource_args(["run", "out"])[-2:] == ["--jobs", "1"]
    assert CW.resource_args(["run", "out", "--jobs=2"])[-1] == "--jobs=2"
    for args in (["--jobs", "3"], ["--jobs", "1", "--jobs=2"]):
        with pytest.raises(ValueError, match="one or two"):
            CW.resource_args(["run", "out", *args])


def test_explicit_unobserved_paid_income_is_reported_without_invented_zero(CW):
    b = _bundle()
    _care(b)["frame"] = [{"turn": 0, "civ": 0, "wages_paid_milli": 0, "farm_time_removed": 1,
                          "paid": True, "carers": [{"income_withheld": None}]}]
    m, problems = CW.extract(b, ())
    assert problems == []
    assert m["care_income_unknown_person_turns"] == 1 and m["care_income_withheld"] == 0
    _care(b)["frame"][0]["paid"] = False
    assert CW.extract(b, ())[0]["care_income_unknown_person_turns"] == 0
    del _care(b)["frame"][0]["carers"][0]["income_withheld"]
    assert any("invalid income_withheld" in p for p in CW.extract(b, ())[1])
    b = _bundle()
    ph = _ph(b)
    ph["guards"] = [{"turn": 0, "civ": 0, "target": 1, "work": 1, "staffed": True, "payment": "paid",
                      "members": [{"wage_paid_milli": 500, "wage_due_milli": 500, "income_withheld": None}]}]
    ph["guard_capacity"] = [[0, 1]]
    ph["funding"][0].update(guard_paid_milli=500, guard_cash_milli=1000, guard_carry_after=500)
    ph["totals"].update(guard_farm_time=1, guard_wages_milli=500, guard_cash_milli=1000)
    m, problems = CW.extract(b, ())
    assert problems == []
    assert m["guard_income_unknown_person_turns"] == 1 and m["guard_income_withheld"] == 0


def test_quarantine_actual_channels_schema_and_receipt_dates_are_required(CW):
    b = _bundle()
    rules = b["history"][0]["epidemics"]["quarantine_rules"]
    rules["channels"] = "trade,migration"
    assert any("staffed closure/migration" in p for p in CW.extract(b, ())[1])
    rules["channels"] = ["trade", "migration"]
    rules["receipt"]["turn"] = 1
    assert any("quarantine receipt" in p for p in CW.extract(b, ())[1])


def test_all_enrolled_worlds_even_unactivated_have_outcomes(CW):
    b = _bundle()
    m, problems = CW.extract(b, ())
    assert problems == []
    assert m["world_deaths_per_1000_pt"] == 20 and m["world_deaths_per_ipt"] == .1
    assert m["arrivals_world"] == 1 and m["famine_region_turns"] == 1
    assert all(m[k] == 0 for k in ("care_covered_region_turns", "water_service_region_turns", "guard_staffed_pair_turns"))
    eligible, why = CW.activation(b, ())
    assert eligible is True and "regardless of activation" in why


def test_material_paid_guard_and_single_envelope_closure(CW):
    b = _bundle()
    ph, care = _ph(b), _care(b)
    ph["guards"] = [{"turn": 0, "civ": 0, "target": 1, "work": 1, "staffed": True, "payment": "paid",
                     "members": [{"agent_id": 10, "wage_due_milli": 500, "wage_paid_milli": 500, "income_withheld": .3}]}]
    ph["guard_capacity"] = [[0, 1]]
    ph["supplies"] = [{"turn": 0, "civ": 0, "region": 0, "source": 0, "seller": 0, "food_milli": 1000,
                       "need_milli": 1000, "charged_milli": 0, "internal_milli": 1000, "price_milli": 1000,
                       "reason": "supplied"}]
    care["frame"] = [{"turn": 0, "civ": 0, "wages_paid_milli": 500, "farm_time_removed": 1,
                      "carers": [{"income_withheld": .2}]}]
    ph["totals"] = {"food_consumed_milli": 1000, "gross_supplies_milli": 1000, "internal_supplies_milli": 1000,
                     "guard_farm_time": 1, "guard_wages_milli": 500, "guard_income_withheld": .3,
                     "care_cash_milli": 1000, "guard_cash_milli": 1000}
    ph["funding"][0].update(care_paid_milli=500, care_cash_milli=1000, care_carry_after=500,
                            guard_paid_milli=500, guard_cash_milli=1000, guard_carry_after=500)
    m, problems = CW.extract(b, ())
    assert problems == []
    assert m["guard_paid_milli"] == 500 and m["supplies_cash_milli"] == 0 and m["supplies_internal_milli"] == 1000
    assert m["care_income_withheld"] == .2 and m["guard_income_withheld"] == .3
    care["ledger"][0]["envelope_coins"] = 1
    assert any("exceeds" in x for x in CW.extract(b, ())[1])


@pytest.mark.parametrize("mutation,reason", [
    (lambda b: _ph(b).__setitem__("source_turn", 1), "source date"),
    (lambda b: _ph(b)["environment"][0].__setitem__("source_turn", 0), "T-1"),
    (lambda b: _care(b)["tick"]["regions"][0].__setitem__("deaths", 1), "death"),
    (lambda b: _care(b)["tick"].__setitem__("refused", [{}]), "refused"),
    (lambda b: _ph(b).__setitem__("guard_capacity", None), "guard capacity"),
    (lambda b: b["history"].append(deepcopy(b["history"][0])), "duplicate"),
    (lambda b: _ph(b)["environment"][0].__setitem__("crowding_factor", 1.5), "crowding"),
    (lambda b: _ph(b)["totals"].__setitem__("food_consumed_milli", 100), "receipt sum"),
    (lambda b: _ph(b)["funding"][0].__setitem__("care_carry_after", 500), "cash + carry"),
    (lambda b: _ph(b).__setitem__("funding_turn", -1), "cash funding"),
    (lambda b: _care(b)["ledger"][0].__setitem__("civ", {}), "missing payer"),
    (lambda b: _ph(b)["funding"][0].__setitem__("civ", {}), "invalid or duplicate payer"),
])
def test_invalid_records_fail_visibly(CW, mutation, reason):
    b = _bundle()
    mutation(b)
    _m, problems = CW.extract(b, ())
    assert any(reason in x for x in problems), problems
    assert CW.activation(b, ())[0] is None


def test_future_report_cannot_feed_decision(CW):
    b = _bundle()
    ph = _ph(b)
    ph["reports"] = [{"id": 0, "recipient": 0, "source": 0, "target": 1, "pathogen": 0,
                      "issued": 0, "delivery": 1, "expires": 6, "prevalence": .1}]
    ph["decisions"] = [{"civ": 0, "target": 1, "report_ids": [0], "expected_loss_units": 10,
                        "cost_units": 2, "goods_contact_cost_proxy": 0, "fatality_observed": True, "close": True}]
    assert any("future" in x for x in CW.extract(b, ())[1])
    ph["decisions"][0]["report_ids"] = [{}]
    assert CW.extract(b, ())[1]  # malformed IDs fail closed instead of raising TypeError


def test_cost_control_care_and_sanitation_benefits_are_neutral(CW):
    b = _bundle("cost_only")
    flags = ("--public-health-mode", "cost_only")
    _care(b)["tick"]["applied"] = [{"coverage": 1, "source_turn": -1, "care_factor": 1}]
    _ph(b)["environment"][0].update(water_service=1, sanitation_observed=True)
    assert CW.extract(b, flags)[1] == []
    _care(b)["tick"]["applied"][0]["care_factor"] = .7
    _ph(b)["environment"][0]["flux_factor"] = .8
    problems = CW.extract(b, flags)[1]
    assert any("care benefit" in x for x in problems) and any("flux factor" in x for x in problems)


def test_unpaid_team_never_dates_enforcement_capacity(CW):
    b = _bundle()
    ph = _ph(b)
    ph["guards"] = [{"turn": 0, "civ": 0, "target": 1, "work": 1, "staffed": True,
                     "payment": "refused:payer_short", "members": []}]
    ph["guard_capacity"] = [[0, 1]]
    ph["totals"]["guard_farm_time"] = 1
    assert any("full named paid work" in x for x in CW.extract(b, ())[1])


@pytest.mark.parametrize("mutation,reason", [
    (lambda b: b["events_timeline"][0].__setitem__("turn", 999), "outside observed"),
    (lambda b: b["events_timeline"][0].__setitem__("turn", -1), "outside observed"),
    (lambda b: b["events_timeline"][0].__setitem__("actors", ["A", "ghost"]), "stable controlled"),
    (lambda b: b["events_timeline"][0].__setitem__("actors", ["A", "A"]), "malformed"),
    (lambda b: b["events_timeline"][0].__setitem__("actors", [None, "B"]), "malformed"),
    (lambda b: b["events_timeline"][0].__setitem__("actors", "AB"), "malformed"),
])
def test_primary_arrivals_reject_future_ghost_or_malformed_provenance(CW, mutation, reason):
    b = _bundle()
    mutation(b)
    m, problems = CW.extract(b, ())
    assert m["arrivals_world"] == 0 and any(reason in p for p in problems)


def test_valid_uncontrolled_arrival_is_recorded_outside_primary(CW):
    b = _bundle()
    b["events_timeline"].append({"event_type": "epidemic_arrival", "turn": 0, "actors": []})
    m, problems = CW.extract(b, ())
    assert problems == [] and m["arrivals_world"] == 1


def test_one_coin_cannot_prefund_two_wages_despite_retained_value_fitting(CW):
    b = _bundle()
    ph, care = _ph(b), _care(b)
    care["ledger"][0]["envelope_coins"] = 1
    care["frame"] = [{"turn": 0, "civ": 0, "wages_paid_milli": 250, "farm_time_removed": .5,
                      "carers": [{"income_withheld": .1}]}]
    ph["guards"] = [{"turn": 0, "civ": 0, "target": 1, "work": 1, "staffed": True, "payment": "paid",
                     "members": [{"wage_due_milli": 500, "wage_paid_milli": 500, "income_withheld": .3}]}]
    ph["guard_capacity"] = [[0, 1]]
    ph["funding"][0].update(envelope_milli=1000, care_paid_milli=250, care_cash_milli=1000,
                            care_carry_after=750, guard_paid_milli=500, guard_cash_milli=1000, guard_carry_after=500)
    ph["totals"].update(care_cash_milli=1000, guard_cash_milli=1000, guard_farm_time=1,
                        guard_wages_milli=500, guard_income_withheld=.3)
    m, problems = CW.extract(b, ())
    assert m["care_paid_milli"] + m["guard_paid_milli"] == 750
    assert m["health_cash_milli"] == 2000
    assert any("fresh health cash funding exceeds" in p for p in problems)
    # Existing prepaid carries can fund these exact credits within the same
    # value envelope, with no fresh cash and no invented transfer between purposes.
    ph["funding"][0].update(care_cash_milli=0, care_carry_before=250, care_carry_after=0,
                            guard_cash_milli=0, guard_carry_before=500, guard_carry_after=0)
    ph["totals"].update(care_cash_milli=0, guard_cash_milli=0)
    assert CW.extract(b, ())[1] == []
