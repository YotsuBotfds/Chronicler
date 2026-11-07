"""The CW5 screen (slice A4-1: titled trade): arms, the pre-treatment region sets
and their validity, activation and the extractor.

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
T = ("--titled-trade",)
TURNS = 24                      # world turns 0-23: the window is 0-19, the first purchase at 20


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw5_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Regions over the window (demand 10 each turn): 0 produces 2 (ratio 0.2), 1 produces 12 (1.2),
# 2 produces 7 on average (0.7: 0 at turn 0, 14 at turn 1, 7 after), 3 has no demand. World
# ratio (2 + 12 + 7) / 30 = 0.7: deficit {0}, surplus {1, 2} (2 sits at the world ratio). At
# turn 0, region 2 produced nothing against 10: a turn-0 deficit region.
WINDOW_PRODUCED = (2.0, 12.0, 7.0, 0.0)
DEMAND = (10.0, 10.0, 10.0, 0.0)


def _fa(w, suff=(0.5, 1.0, 0.9, 1.0), net=(0.5, -0.5, 0.0, 0.0)):
    produced = list(WINDOW_PRODUCED)
    if w == 0:
        produced[2] = 0.0
    if w == 1:
        produced[2] = 14.0
    rows = [{"region_id": i, "native": {"demand": DEMAND[i], "produced": produced[i], "transport_net": net[i]},
             "sufficiency_after_relief": suff[i]} for i in range(4)]
    return {"source_turn": w, "regions": rows}


def _ship(sid, *, origin=1, dest=0, cargo=(0, 0, 0, 0, 0), cargo_open=(1000, 0, 0, 0, 0), delivered=0, returned=0,
          losses=None, cursor=0, path=(1, 0), cost=600):
    return {"id": sid, "origin": origin, "dest": dest, "path": list(path), "cursor": cursor, "cargo": list(cargo),
            "cargo_open": list(cargo_open), "losses": losses or {}, "delivered": delivered, "returned": returned,
            "deposited": 0, "cost_milli": cost}


def _bundle(titled=True, *, receipt_rows=2, broken=False, closes=True, first=20):
    """Shipment 1 bought in surplus region 1 at world turn ``first`` (1000 milli for 600),
    moving at ``first + 1``, delivered into deficit region 0 at ``first + 2`` (950 milli,
    50 decayed); shipment 2 bought at ``first + 1`` in region 1 (500 milli for 300) and
    aboard at the end; a lot of 400 milli unsold at the end."""
    history = []
    for s in range(1, TURNS + 1):
        w = s - 1
        lv = {"schema_version": 1,
              "household_retail": {"source_turn": w, "mode": "retail", "counters": {"credited_milli": 3000},
                                   "regions": [{"region": i, "price_milli": 300 + 100 * i,
                                                "provisioning": {"priced_out_persons": 2 if i == 0 else 0},
                                                "cohorts": {"groups": {"nonfarm_adults": {"persons": 3}}}}
                                               for i in range(4)]},
              "wealth_accounting": {"source_turn": w, "frame": {"closures": [{"closes": closes}]}}}
        if titled:
            dispatched, events, live, closed = [], [], [], []
            if w == first:
                dispatched = [{"shipment": 1, "origin": 1, "dest": 0, "milli": 1000}]
            if w == first + 1:
                dispatched = [{"shipment": 2, "origin": 1, "dest": 0, "milli": 500}]
                events = [{"shipment": 1, "event": "moved", "region": 0}]
            if w == first + 2:
                events = [{"shipment": 1, "event": "delivered", "region": 0, "delivered": 950, "returned": 0,
                           "deposited": 0}]
            if w in (first, first + 1):
                live.append(_ship(1, cargo=(1000, 0, 0, 0, 0), cursor=1 if w == first + 1 else 0))
            if w >= first + 1:
                live.append(_ship(2, cargo=(500, 0, 0, 0, 0), cargo_open=(500, 0, 0, 0, 0), cost=300))
            if w >= first + 2:
                closed.append(_ship(1, delivered=950, losses={"transit_decay": 50}, cursor=1))
                if broken:
                    closed[0]["delivered"] = 900
            counters = {"dispatched": 2 if w > first else (1 if w == first else 0),
                        "delivered": 1 if w >= first + 2 else 0, "returned": 0, "bought_milli": 1500,
                        "paid_milli": 900, "cargo_sales_credited_milli": 1200 if w >= first + 2 else 0,
                        "income_withheld_micro": 100000, "carrier_turns": 2, "receipt_rows": receipt_rows,
                        "consigned_milli": 950, "returned_milli": 0, "transit_decay_milli": 50}
            lv["titled_trade"] = {"source_turn": w, "frame": {"turn": w, "dispatched": dispatched, "events": events},
                                  "shipments": live, "closed": closed, "counters": counters,
                                  "lots": [{"holder": 9, "region": 0, "milli": 400}] if w >= first + 2 else []}
        history.append({"turn": s, "livelihoods": lv, "food_accounting": _fa(w),
                        "civ_stats": {"A": {"population": 10, "treasury": 5, "stability": 50}}})
    regions = [{"name": f"R{i}", "stockpile": {"goods": {"grain": 1.0, "ore": 9.0}}} for i in range(4)]
    return {"history": history, "world_state": {"regions": regions}}


def test_the_screen_declares_two_arms_two_primaries_and_both_cohorts(CW):
    s = CW.SCREENS["CW5"]
    assert s.ready and s.root == "R" and s.arms == {"R": ((), None), "T": (("--titled-trade",), "R")}
    assert s.held == {"template": tuple(range(771, 777)), "procedural": tuple(range(871, 877))}
    assert [(o.id, o.arm, o.control) for o in s.primaries()] == [
        ("cw5_food_in_deficit", "T", "R"), ("cw5_shortfall_deficit", "T", "R")]
    assert {o.id for o in s.outcomes} >= {"cw5_holder_balance", "cw5_margin_vs_withheld", "cw5_t0_food_in_deficit",
                                          "cw5_rr_food_in_deficit"}
    assert s.report is not None and {"--household-retail-boundary", "all", "--wealth-accounting"} <= set(s.base)


def _paired(CW, r_bundle=None, t_bundle=None):
    def row(arm, m):
        return {"arm": arm, "stratum": "t", "seed": 5, "rc": 0, "m": m}
    r = row("R", CW.cw5_extract(r_bundle or _bundle(titled=False), ())[0])
    t = row("T", CW.cw5_extract(t_bundle or _bundle(), T)[0])
    return r, t


def test_the_window_sets_are_relative_and_the_turn_zero_sets_are_a_sensitivity_line(CW):
    m, problems = CW.cw5_extract(_bundle(), T)
    assert problems == [] and m["first_purchase_turn"] == 20
    deficit, surplus, ratio = CW.cw5_window_sets(m, 19)
    assert (deficit, surplus) == ([0], [1, 2]) and ratio == pytest.approx(0.7)   # 2 sits at the world ratio
    assert CW.cw5_sets(_bundle()) == ([0, 2], [1], [])               # region 2 produced nothing at turn 0
    assert m["t0_sets_digest"] == "D:0,2|S:1"
    short = _bundle()
    short["history"] = short["history"][:10]
    assert any("incomplete" in p for p in CW.cw5_extract(short, T)[1])


def test_the_pairing_computes_r_s_sets_over_t_s_window_for_both_arms(CW):
    r, t = _paired(CW)
    lines = CW._cw5_report([r, t], {"t": [5]})
    assert any("| t | 5 | 20 | 20 | 1 / 2 | yes | valid |" in line for line in lines)
    status, info, rm, tm = CW.cw5_world(r["m"], t["m"])
    assert status == "valid" and info["digest"] == "D:0|S:1,2" and info["window_end"] == 19
    assert tm["titled_delivered_deficit"] == pytest.approx(0.95) and tm["titled_net_deficit"] == pytest.approx(0.95)
    assert tm["titled_net_surplus"] == pytest.approx(-1.5) and rm["titled_net_deficit"] == 0.0
    assert tm["native_net_deficit"] == pytest.approx(12.0)                   # 0.5 a turn, 24 snapshots
    assert tm["food_in_deficit"] == pytest.approx(12.95) and rm["food_in_deficit"] == pytest.approx(12.0)
    assert tm["shortfall_deficit"] == pytest.approx(0.5) and tm["shortfall_surplus"] == pytest.approx(0.05)
    assert tm["price_deficit"] == 300 and tm["priced_out_deficit"] == 48
    assert rm["rr_food_in_deficit"] == pytest.approx(12.0) and tm["rr_food_in_deficit"] == pytest.approx(12.95)
    assert t["m"]["t0_food_in_deficit"] == pytest.approx(12.95)              # region 2 adds no trade
    assert "food_in_deficit" not in t["m"]                                   # the rows are not changed


def test_the_runner_reads_the_paired_outcomes_from_both_rows(CW):
    import screen_runner as SR
    r, t = _paired(CW)
    for row in (r, t):
        row["activation"] = {"activated": True}
    screen = CW.SCREENS["CW5"]
    primary = screen.primaries()[0]
    assert primary.pair is not None and primary.control == "R"
    cells, values = SR.paired_values([r, t], screen, primary.arm, primary.control, primary.read, "t", [5],
                                     pair=primary.pair)
    assert values == [pytest.approx(0.95)] and cells == ["5: +0.95"]
    short = _paired(CW, t_bundle=_bundle(first=3))
    for row in short:
        row["activation"] = {"activated": True}
    cells, values = SR.paired_values(list(short), screen, "T", "R", primary.read, "t", [5], pair=primary.pair)
    assert values == [] and cells == ["5: excluded by the window"]


def test_the_window_ends_before_t_s_first_purchase(CW):
    r, t = _paired(CW, t_bundle=_bundle(first=12))
    lines = CW._cw5_report([r, t], {"t": [5]})
    assert any("| t | 5 | 12 | 12 | 1 / 2 | yes | valid |" in line for line in lines)
    status, info, _rm, tm = CW.cw5_world(r["m"], t["m"])
    assert info["window_end"] == 11 and tm["food_in_deficit"] is not None


def test_a_window_shorter_than_five_turns_or_differing_records_exclude_the_world(CW):
    r, t = _paired(CW, t_bundle=_bundle(first=3))
    lines = CW._cw5_report([r, t], {"t": [5]})
    assert any("excluded: first purchase in world turn 3, a window of 3 turns" in line for line in lines)
    _status, _info, rm, tm = CW.cw5_world(r["m"], t["m"])
    assert tm["food_in_deficit"] is None and rm["shortfall_deficit"] is None
    assert tm["rr_food_in_deficit"] is not None and t["m"]["t0_food_in_deficit"] is not None   # sensitivity stays
    r, t = _paired(CW)
    t["m"]["v_window_produced"][4][1] += 1.0
    lines = CW._cw5_report([r, t], {"t": [5]})
    assert any("| NO | excluded: R's and T's window records differ |" in line for line in lines)
    assert CW.cw5_world(r["m"], t["m"])[3]["food_in_deficit"] is None


def test_the_merchants_balance_and_the_counts_kept_apart(CW):
    m, problems = CW.cw5_extract(_bundle(), T)
    assert problems == []
    assert m["tt_returned"] == 0 and m["tt_returned_food"] == 0.0            # a count and food, apart
    assert m["holder_net"] == pytest.approx(0.3) and m["tt_withheld"] == pytest.approx(0.1)
    assert m["held_aboard_value"] == pytest.approx(0.3) and m["held_returned_value"] == 0.0
    assert m["held_unsold_value"] == pytest.approx(0.4 * 0.6)                # 400 milli at 900 / 1500 per milli
    assert m["holder_balance"] == pytest.approx(0.2 + 0.3 + 0.24)
    assert m["commons_end"] == pytest.approx(4.0) and m["dest_regions"] == 1 and m["origin_regions"] == 1


def test_without_titled_trade_the_titled_flows_are_zero_by_construction(CW):
    m, problems = CW.cw5_extract(_bundle(titled=False), ())
    assert problems == [] and sum(m["v_titled_in"]) == sum(m["v_titled_out"]) == 0
    assert m["holder_balance"] is None and m["tt_dispatched"] is None and m["first_purchase_turn"] is None
    assert any("without the switch" in p for p in CW.cw5_extract(_bundle(), ())[1])
    assert any("enabled but not recorded" in p for p in CW.cw5_extract(_bundle(titled=False), T)[1])


def test_a_missing_food_account_is_a_problem_never_a_zero(CW):
    b = _bundle()
    del b["history"][22]["food_accounting"]
    assert any("food account missing" in p for p in CW.cw5_extract(b, T)[1])
    b = _bundle()
    b["history"][21]["food_accounting"]["regions"][0]["native"]["transport_net"] = None
    assert any("food account missing" in p for p in CW.cw5_extract(b, T)[1])


@pytest.mark.parametrize("kw, needle", [
    ({"broken": True}, "does not close"),
    ({"receipt_rows": 1}, "receipt rows"),
    ({"closes": False}, "ledger closures failed"),
])
def test_the_validity_checks_are_problems(CW, kw, needle):
    assert any(needle in p for p in CW.cw5_extract(_bundle(**kw), T)[1])


def test_activation_names_shipments_region_turns_and_the_first_purchase(CW):
    assert CW.cw5_activation(_bundle(titled=False), ())[0] is None
    acted, text = CW.cw5_activation(_bundle(), T)
    assert acted is True and "1 delivered" in text and "first purchase in world turn 20" in text
    assert f"of {4 * TURNS} region-turns" in text
    idle = _bundle()
    for s in idle["history"]:
        s["livelihoods"]["titled_trade"]["counters"]["delivered"] = 0
    assert CW.cw5_activation(idle, T)[0] is False
