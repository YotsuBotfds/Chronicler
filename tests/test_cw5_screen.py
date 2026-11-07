"""The CW5 screen (slice A4-1: titled trade): arms, the pre-treatment region sets,
activation and the extractor.

Offline: constructed bundles only (no simulation, no child process); the
extractor was also checked on the shared timing pilot's bundles (the
preregistration names the checks). Oracle chunk ``connected-world-e``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
T = ("--titled-trade",)


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw5_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Region 0 produces less than its demand at turn 0 (deficit), 1 at least its demand
#: (surplus), 2 has no demand at turn 0 (in neither set).
PRODUCED0, DEMAND0 = (2.0, 12.0, 0.0), (10.0, 10.0, 0.0)


def _fa(w, suff=(0.5, 1.0, 1.0), net=(0.0, 0.0, 0.0)):
    rows = []
    for i in range(3):
        d = DEMAND0[i] if w == 0 else 10.0
        p = PRODUCED0[i] if w == 0 else 5.0
        rows.append({"region_id": i, "native": {"demand": d, "produced": p, "transport_net": net[i]},
                     "sufficiency_after_relief": suff[i]})
    return {"source_turn": w, "regions": rows}


def _ship(sid, *, origin=1, dest=0, cargo=(0, 0, 0, 0, 0), cargo_open=(1000, 0, 0, 0, 0), delivered=0, losses=None,
          cursor=0, path=(1, 0)):
    return {"id": sid, "origin": origin, "dest": dest, "path": list(path), "cursor": cursor, "cargo": list(cargo),
            "cargo_open": list(cargo_open), "losses": losses or {}, "delivered": delivered, "returned": 0,
            "deposited": 0}


def _bundle(titled=True, *, receipt_rows=2, broken=False, closes=True):
    """World turns 0-3: shipment 1 bought in surplus region 1 at turn 1 (1000 milli),
    moving at turn 2, delivered into deficit region 0 at turn 3 (950 milli, 50 decayed)."""
    frames = {
        0: {"dispatched": [], "events": []},
        1: {"dispatched": [{"shipment": 1, "origin": 1, "dest": 0, "milli": 1000}], "events": []},
        2: {"dispatched": [], "events": [{"shipment": 1, "event": "moved", "region": 0}]},
        3: {"dispatched": [], "events": [{"shipment": 1, "event": "delivered", "region": 0, "delivered": 950,
                                          "returned": 0, "deposited": 0}]},
    }
    history = []
    for s in range(1, 5):
        w = s - 1
        lv = {"schema_version": 1,
              "household_retail": {"source_turn": w, "mode": "retail", "counters": {"credited_milli": 3000},
                                   "regions": [{"region": i, "price_milli": 300 + 100 * i,
                                                "provisioning": {"priced_out_persons": 2 if i == 0 else 0}}
                                               for i in range(3)]},
              "wealth_accounting": {"source_turn": w, "frame": {"closures": [{"closes": closes}]}}}
        if titled:
            live = [_ship(1, cargo=(1000, 0, 0, 0, 0), cursor=1 if w == 2 else 0)] if w in (1, 2) else []
            closed = [_ship(1, delivered=950, losses={"transit_decay": 50}, cursor=1)] if w == 3 else []
            if broken and closed:
                closed[0]["delivered"] = 900
            counters = {"dispatched": 1, "delivered": 1 if w == 3 else 0, "paid_milli": 600,
                        "cargo_sales_credited_milli": 900 if w == 3 else 0, "income_withheld_micro": 100000,
                        "carrier_turns": 2, "receipt_rows": receipt_rows, "consigned_milli": 950,
                        "transit_decay_milli": 50}
            lv["titled_trade"] = {"source_turn": w, "frame": {"turn": w, **frames[w]}, "shipments": live,
                                  "closed": closed, "counters": counters}
        history.append({"turn": s, "livelihoods": lv, "food_accounting": _fa(w, net=(0.5, -0.5, 0.0)),
                        "civ_stats": {"A": {"population": 10, "treasury": 5, "stability": 50}}})
    regions = [{"name": f"R{i}", "stockpile": {"goods": {"grain": 1.0, "ore": 9.0}}} for i in range(3)]
    return {"history": history, "world_state": {"regions": regions}}


def test_the_screen_declares_two_arms_three_primaries_and_both_cohorts(CW):
    s = CW.SCREENS["CW5"]
    assert s.ready and s.root == "R" and s.arms == {"R": ((), None), "T": (("--titled-trade",), "R")}
    assert s.held == {"template": tuple(range(771, 777)), "procedural": tuple(range(871, 877))}
    assert [(o.id, o.arm, o.control) for o in s.primaries()] == [
        ("cw5_food_in_deficit", "T", "R"), ("cw5_shortfall_deficit", "T", "R"), ("cw5_margin_vs_withheld", "T", None)]
    assert {"--household-retail-boundary", "all", "--wealth-accounting"} <= set(s.base)


def test_the_region_sets_come_from_world_turn_zero(CW):
    assert CW.cw5_sets(_bundle()) == ([0], [1], [])
    b = _bundle()
    b["history"][0]["food_accounting"]["source_turn"] = 1
    assert CW.cw5_sets(b)[2] == ["no food account of world turn 0 in snapshot 1"]


def test_titled_food_into_the_deficit_regions_and_the_merchants_margin(CW):
    m, problems = CW.cw5_extract(_bundle(), T)
    assert problems == []
    assert m["titled_delivered_deficit"] == pytest.approx(0.95) and m["titled_net_deficit"] == pytest.approx(0.95)
    assert m["titled_net_surplus"] == pytest.approx(-1.0)                    # bought there, never returned
    assert m["native_net_deficit"] == pytest.approx(2.0)                     # 0.5 a turn, 4 snapshots
    assert m["food_in_deficit"] == pytest.approx(2.95)
    assert m["holder_net"] == pytest.approx(0.3) and m["tt_withheld"] == pytest.approx(0.1)
    assert m["holder_net_vs_withheld"] == pytest.approx(0.2) and m["owner_receipts"] == pytest.approx(0.6)
    assert m["shortfall_deficit"] == pytest.approx(0.5) and m["shortfall_surplus"] == pytest.approx(0.0)
    assert m["price_deficit"] == 300 and m["price_surplus"] == 400 and m["priced_out_deficit"] == 8
    assert m["commons_end"] == pytest.approx(3.0) and m["dest_regions"] == 1 and m["origin_regions"] == 1
    # Region-turns touched: turn 1 the origin, turn 2 the region moved into (and standing), turn 3 the destination.
    assert m["titled_region_turns"] == 3


def test_without_titled_trade_the_titled_flows_are_zero_by_construction(CW):
    m, problems = CW.cw5_extract(_bundle(titled=False), ())
    assert problems == [] and m["titled_net_deficit"] == 0.0 and m["food_in_deficit"] == pytest.approx(2.0)
    assert m["holder_net_vs_withheld"] is None and m["tt_dispatched"] is None
    assert any("without the switch" in p for p in CW.cw5_extract(_bundle(), ())[1])
    assert any("enabled but not recorded" in p for p in CW.cw5_extract(_bundle(titled=False), T)[1])


@pytest.mark.parametrize("kw, needle", [
    ({"broken": True}, "does not close"),
    ({"receipt_rows": 1}, "receipt rows"),
    ({"closes": False}, "ledger closures failed"),
])
def test_the_validity_checks_are_problems(CW, kw, needle):
    assert any(needle in p for p in CW.cw5_extract(_bundle(**kw), T)[1])


def test_activation_names_shipments_and_region_turns(CW):
    assert CW.cw5_activation(_bundle(titled=False), ())[0] is None
    acted, text = CW.cw5_activation(_bundle(), T)
    assert acted is True and "1 delivered" in text and "3 of 12 region-turns" in text
    idle = _bundle()
    for s in idle["history"]:
        s["livelihoods"]["titled_trade"]["counters"]["delivered"] = 0
    assert CW.cw5_activation(idle, T)[0] is False
