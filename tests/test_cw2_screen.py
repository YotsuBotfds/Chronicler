"""The CW2 screen (slices A3-1 and A3-2: workshop economics and the owned-output
rule): arms, activation and the extractor.

Offline: constructed bundles only (no simulation, no child process); the
extractor was also checked on the shared timing pilot's bundles (the
preregistration names the checks). Oracle chunk ``connected-world-e``.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
E1 = ("--workshop-economics",)
E2 = ("--workshop-economics", "--workshop-economics-rules", "2")
E2F = E2 + ("--workshop-economics-mode", "free_inputs")
E2A = E2 + ("--workshop-economics-mode", "academy_only")


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw2_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _receipt(turn, *, operating, sold=0, household=0, inventory=1000):
    """Payroll adds ``sold`` and ``household_sold`` only when nonzero (``_add``)."""
    r = {"turn": turn, "site": 0, "operating": operating, "inventory_close": inventory}
    if sold:
        r["sold"] = sold
    if household:
        r["household_sold"] = household
    return r


def _bundle(econ=True, *, rules=2, mode="market", turns=6, close_at=4, household=(200, 0, 300, 0),
            unpaid=0, charged=900, free_use=0, closes=True):
    """One firm at site 0 opened at world turn 1, closed idle at world turn ``close_at``
    (receipts on turns 1..close_at), over ``turns`` snapshots (world turns 0..turns-1)."""
    history = []
    hh_total = 0
    for s in range(1, turns + 1):
        w = s - 1
        open_now = 1 <= w <= close_at
        receipts = []
        if open_now:
            k = w - 1
            hh = household[k] if econ and k < len(household) else 0
            hh_total += hh
            receipts = [_receipt(w, operating=k in (0, 2), sold=(5 if k == 1 else 0), household=hh)]
        firms = [{"site": 0, "opened_turn": 1, "status": "open", "inventory": 1500}] if 1 <= w < close_at else []
        closed = ([{"site": 0, "opened_turn": 1, "status": "closed", "closed_turn": close_at, "closed_reason": "idle"}]
                  if w >= close_at else [])
        payroll = {"source_turn": w, "mode": "paid", "firms": firms, "closed": closed, "receipts": receipts,
                   "counters": {"firms_opened": 1 if w >= 1 else 0, "wages_due": 600, "wages_paid": 500, "worn": 30}}
        lv = {"schema_version": 1, "workshop_payroll": payroll,
              "workshops": {"source_turn": w, "counters": {"work_realized": 1.5},
                            "receipts": [{"site": 0, "arrears_after": 2}]},
              "wealth_accounting": {"source_turn": w, "frame": {"closures": [{"closes": closes}]},
                                    "lifetime": {"workshop_wage_in_milli": 500, "withheld_workshop_payroll": 0.2}}}
        if econ:
            ec = {"firms_opened": 1, "operating_firm_turns": 2, "inputs_used": 1000, "inputs_charged": charged,
                  "priced_out_households": 3,
                  "household_delivered": hh_total, "household_sales": hh_total // 4, "free_use_upper_bound": free_use,
                  "owned_output": 800 if rules == 2 else 0, "academy_sales": 50}
            econ_receipts = [{"operating": r["operating"], "produced": 400, "titled": 400,
                              "inputs": {"converted_unpaid_milli": unpaid}} for r in receipts]
            lv["workshop_economics"] = {"source_turn": w, "mode": mode, "rules_version": rules, "counters": ec,
                                        "receipts": econ_receipts}
        history.append({"turn": s, "livelihoods": lv,
                        "civ_stats": {"A": {"population": 10, "treasury": 5, "stability": 40, "alive": True}}})
    return {"history": history, "world_state": {"regions": [{"name": "R0"}]}}


def test_the_screen_declares_five_arms_three_primaries_and_both_cohorts(CW):
    s = CW.SCREENS["CW2"]
    assert s.ready and s.root == "P" and set(s.arms) == {"P", "E1", "E2", "E2f", "E2a"}
    assert s.arms["E1"][1] == "P" and s.arms["E2"][1] == "E1"
    assert s.arms["E2f"][1] == "E2" and s.arms["E2a"][1] == "E2"
    assert s.arms["E2f"][0][-1] == "free_inputs" and s.arms["E2a"][0][-1] == "academy_only"
    assert s.held == {"template": tuple(range(741, 747)), "procedural": tuple(range(841, 847))}
    primaries = s.primaries()
    assert [(o.id, o.arm, o.control) for o in primaries] == [
        ("cw2_active_share", "E2", "E1"), ("cw2_wages", "E2", "P"), ("cw2_wares_sold", "E2", "E1")]
    assert "--wealth-accounting" in s.base and "--workshop-payroll" in s.base


def test_firm_turns_by_state_count_closed_turns_against_the_firm(CW):
    m, problems = CW.cw2_extract(_bundle(), E2)
    assert problems == []
    # Opened at world turn 1, horizon to world turn 5: 5 turns; receipts on turns 1-4.
    assert (m["firms_opened"], m["firm_turns_horizon"], m["open_firm_turns"], m["closed_firm_turns"]) == (1, 5, 4, 1)
    # Turn 1 produced and sold to households, 2 sold to an academy, 3 produced and sold, 4 idle.
    assert m["active_share"] == pytest.approx(3 / 5) and m["producing_share"] == pytest.approx(2 / 5)
    assert m["active_firm_turns"] == 3
    assert m["selling_share"] == pytest.approx(3 / 5) and m["idle_share"] == pytest.approx(1 / 5)
    assert m["closed_share"] == pytest.approx(1 / 5) and m["closed_idle"] == 1 and m["open_at_end"] == 0
    assert m["household_delivered"] == pytest.approx(0.5) and m["wages_credited"] == pytest.approx(0.5)
    assert m["household_net_income"] == pytest.approx(0.3) and m["wage_arrears"] == pytest.approx(0.1)
    assert m["farm_time_diverted"] == 1.5 and m["asset_arrears_end"] == 2 and m["stability_end"] == 40
    assert m["priced_out_households"] == 3 and m["free_use_upper_bound"] == 0.0


def test_the_status_quo_has_no_household_customers(CW):
    m, problems = CW.cw2_extract(_bundle(econ=False, household=()), ())
    assert problems == [] and m["household_delivered"] is None and m["inputs_charged"] is None
    assert m["priced_out_households"] is None
    assert m["active_share"] == pytest.approx(3 / 5)        # the same firm-turn states without economics
    stray = _bundle(econ=True)
    assert any("without the switch" in p for p in CW.cw2_extract(stray, ())[1])


def test_a_receipt_without_operating_or_with_a_text_sale_is_a_problem(CW):
    b = _bundle()
    del b["history"][2]["livelihoods"]["workshop_payroll"]["receipts"][0]["operating"]
    assert any("lacks operating" in p for p in CW.cw2_extract(b, E2)[1])
    b = _bundle()
    b["history"][2]["livelihoods"]["workshop_payroll"]["receipts"][0]["sold"] = "5"
    assert any("non-numeric" in p for p in CW.cw2_extract(b, E2)[1])


@pytest.mark.parametrize("bundle_kw, flags, needle", [
    ({"free_use": 10}, E2, "free use"),
    ({"unpaid": 5}, E2, "converted unpaid"),
    ({"mode": "free_inputs"}, E2F, "inputs charged with free inputs"),
    ({"mode": "academy_only"}, E2A, "academy_only"),
    ({"closes": False}, E2, "ledger closures failed"),
    ({"rules": 1}, E2, "not rules 2"),
])
def test_the_validity_checks_are_problems(CW, bundle_kw, flags, needle):
    assert any(needle in p for p in CW.cw2_extract(_bundle(**bundle_kw), flags)[1])


def test_wages_and_deliveries_are_checked_against_payroll(CW):
    b = _bundle()
    b["history"][-1]["livelihoods"]["wealth_accounting"]["lifetime"]["workshop_wage_in_milli"] = 400
    assert any("workshop wages" in p for p in CW.cw2_extract(b, E2)[1])
    b = _bundle()
    b["history"][-1]["livelihoods"]["workshop_economics"]["counters"]["household_delivered"] = 1
    assert any("deliver" in p for p in CW.cw2_extract(b, E2)[1])
    none = copy.deepcopy(_bundle())
    for s in none["history"]:
        del s["livelihoods"]["workshop_payroll"]
    assert CW.cw2_extract(none, E2) == ({}, ["no workshop payroll record"])


def test_activation_by_mode(CW):
    assert CW.cw2_activation(_bundle(), ())[0] is None                     # the root is not judged
    acted, text = CW.cw2_activation(_bundle(), E2)
    assert acted is True and "1 firms opened" in text and "households bought 0.50 loads" in text
    assert CW.cw2_activation(_bundle(household=(0, 0, 0, 0)), E2)[0] is False
    assert CW.cw2_activation(_bundle(household=(0, 0, 0, 0), mode="academy_only"), E2A)[0] is True
    assert CW.cw2_activation(_bundle(charged=0, mode="free_inputs"), E2F)[0] is True
    assert CW.cw2_activation(_bundle(charged=0), E2)[0] is False
