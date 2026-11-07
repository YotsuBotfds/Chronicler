"""The CW3 screen (slice B2: the watershed in flow mode under upstream forest
protection): arms, activation and the extractor.

Offline: constructed bundles only (no simulation, no child process); the
extractor was also checked on development-world bundles (the preregistration
names the checks). Oracle chunk ``connected-world-b``.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["Up1", "Up2", "Conf", "Coast"]
DOWN = [2, 2, -1, -1]                 # Up1 and Up2 drain into Conf; Conf and Coast to the sea


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw3_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ws(turn, mode, *, used=(0.5, 0.6, 0.7, 0.8), derived=None, caps=(), residual=0.0, floods=(), declared=()):
    derived = list(used) if derived is None else list(derived)
    counters = {"floods_started": len(floods), "flood_region_turns": len(floods), "droughts_declared": len(declared),
                "drought_region_turns": 0, "terrain_cap_changes": len(caps)}
    if mode == "flow":
        counters.update({"flood_consequences": len(floods), "flood_consequences_withheld": 0,
                         "superseded_river_floods": 0})
    rec = {"schema_version": 1, "stage": "B2", "mode": mode, "source_turn": turn - 1, "observed": True,
           "graph": {"down": DOWN, "sea": -1, "sink": -2, "lake": -3, "river_steps": 0},
           "regions": {"index_observed": list(used), "index_derived": derived},
           "cap_changes": list(caps), "floods": [{"region": r, "excess": 0.1} for r in floods],
           "droughts": {"declared": [{"region": r} for r in declared], "open": [], "ended": []},
           "cumulative": {"closure_residual": residual, "opening_storage": 30.0, "precipitation": 10.0},
           "counters": counters}
    return rec


def _fa(turn, suff):
    return {"schema_version": 1, "source_turn": turn - 1,
            "regions": [{"region_id": i, "native": {"demand": 10.0}, "sufficiency_after_relief": s}
                        for i, s in enumerate(suff)]}


def _cp(turn, protected=(0,), kept=0.02, charged=2, mode="enforced"):
    first = turn == 1
    return {"schema_version": 1, "mode": mode, "source_turn": turn - 1, "observed": True,
            "receipts": [{"region_id": r} for r in protected],
            "decisions": [{"turn": 0, "region_id": r, "civ": 0, "kind": "adopted", "reason": "clearing_pressure"}
                          for r in protected] if first else [],
            "unprotected": [{"region_id": 1, "reason": "over_limit"}, {"region_id": 3, "reason": "not_forested"}]
            if first else [],
            "counters": {"adopted": len(protected), "protected_region_turns": turn * len(protected),
                         "cover_not_cleared": (0.0 if mode == "cost_only" else kept * turn),
                         "cover_would_keep": kept * turn, "charged": charged * turn}}


def _bundle(mode="record_only", cp=False, turns=3, cp_mode="enforced", **ws_kw):
    history = []
    for t in range(1, turns + 1):
        liv = {"schema_version": 1, "watershed": _ws(t, mode, **ws_kw)}
        if cp:
            liv["clearing_protection"] = _cp(t, mode=cp_mode)
        history.append({"turn": t, "livelihoods": liv, "food_accounting": _fa(t, (1.0, 0.5, 0.8, 1.2)),
                        "ecology": {n: {"forest_cover": 0.5, "water": 0.6} for n in NAMES}})
    return {"history": history, "world_state": {"regions": [{"name": n} for n in NAMES]},
            "events_timeline": [{"event_type": "flood", "description": "Flooding devastates Coast"}]}


R = ("--watershed", "--watershed-mode", "record_only")
F = ("--watershed", "--watershed-mode", "flow")
CP = ("--clearing-protection",)
CPC = ("--clearing-protection", "--clearing-protection-mode", "cost_only")


def test_the_screen_is_declared_on_the_procedural_stratum_with_three_primaries(CW):
    s = CW.SCREENS["CW3"]
    assert s.ready and s.root == "R" and set(s.arms) == {"R", "F", "R_CP", "F_CPc", "F_CP"}
    assert s.arms["F_CP"][1] == "F_CPc" and s.arms["F_CPc"][1] == "F" and s.arms["F"][1] == "R"
    assert s.arms["R_CP"][1] == "R" and s.arms["F_CPc"][0][-2:] == ("--clearing-protection-mode", "cost_only")
    assert {o.id for o in s.outcomes if o.control == "F_CPc"} >= {"cw3_cpc_ds_water", "cw3_cpc_cand_water"}
    assert not any(o.primary for o in s.outcomes if o.control == "F_CPc")
    assert s.held == {"procedural": tuple(range(851, 857))} and s.pilot == {"procedural": (19,)}
    primaries = s.primaries()
    assert [o.id for o in primaries] == ["cw3_ds_water_flow", "cw3_ds_food_flow", "cw3_ds_water_interaction"]
    assert primaries[2].minus == ("R_CP", "R") and all(o.arm == "F_CP" and o.control == "F" for o in primaries)


def test_the_extractor_reads_downstream_and_upstream_food_and_water(CW):
    m, problems = CW.cw3_extract(_bundle(), R)
    assert problems == []
    assert (m["downstream_regions"], m["upstream_regions"]) == (1, 2)     # Conf receives; Up1, Up2 feed it
    assert m["water_downstream"] == pytest.approx(0.7) and m["water_upstream"] == pytest.approx(0.55)
    assert m["food_shortfall_downstream"] == pytest.approx(0.2)            # sufficiency 0.8 -> 20% unmet
    assert m["food_shortfall_upstream"] == pytest.approx(0.25)             # (0 + 0.5) / 2
    assert m["food_met_all"] == pytest.approx((1.0 + 0.5 + 0.8 + 1.0) / 4)
    assert m["coastal_floods"] == 1 and m["flood_consequences"] is None and m["cp_adopted"] is None
    assert m["closure_worst_relative"] == 0.0 and m["index_gap_worst"] is None


def test_flow_activation_and_the_validity_checks(CW):
    ok = _bundle("flow", used=(0.5, 0.6, 0.7, 0.8), derived=(0.5, 0.6, 0.70002, 0.8))
    assert CW.cw3_activation(ok, F)[0] is True
    m, problems = CW.cw3_extract(ok, F)
    assert problems == [] and m["index_gap_worst"] == pytest.approx(2e-5)
    capped = _bundle("flow", used=(0.5, 0.6, 0.7, 0.8), derived=(0.5, 0.6, 0.75, 0.8),
                     caps=[{"region": 2, "cap_after": 0.7}])
    assert CW.cw3_activation(capped, F)[0] is True                         # min(derived, new cap) is the index used
    gap = _bundle("flow", derived=(0.5, 0.6, 0.75, 0.8))
    assert CW.cw3_activation(gap, F)[0] is False
    assert any("not the derived index" in p for p in CW.cw3_extract(gap, F)[1])
    leak = _bundle("flow", residual=1e-6)
    assert any("does not close" in p for p in CW.cw3_extract(leak, F)[1])
    wrong = _bundle("record_only")
    assert any("not in mode flow" in p for p in CW.cw3_extract(wrong, F)[1])


def test_protection_activation_counts_and_the_regions_below_it(CW):
    b = _bundle("flow", cp=True)
    acted, text = CW.cw3_activation(b, F + CP)
    assert acted is True and "protected region-turns" in text
    m, problems = CW.cw3_extract(b, F + CP)
    assert problems == []
    assert (m["cp_protected_regions"], m["cp_downstream_of_protected"], m["cp_protected_with_downstream"]) == (1, 1, 1)
    assert m["sel_food_shortfall_below_protected"] == pytest.approx(0.2)
    # The candidate set at enable time: adopted at turn 0 (Up1) and eligible over the limit (Up2);
    # not_forested is no candidate. Both drain into Conf.
    assert (m["cand_regions"], m["cand_below"], m["cand_digest"]) == (2, 1, "0,1")
    assert m["cand_water_below"] == pytest.approx(0.7) and m["cand_food_shortfall_below"] == pytest.approx(0.2)
    cost = _bundle("flow", cp=True, cp_mode="cost_only")
    acted, text = CW.cw3_activation(cost, F + CPC)
    assert acted is True and "cost_only" in text
    mc, problems = CW.cw3_extract(cost, F + CPC)
    assert problems == [] and mc["cp_cover_not_cleared"] == 0.0 and mc["cand_digest"] == m["cand_digest"]
    leaky = _bundle("flow", cp=True, cp_mode="cost_only")
    leaky["history"][-1]["livelihoods"]["clearing_protection"]["counters"]["cover_not_cleared"] = 0.01
    assert CW.cw3_activation(leaky, F + CPC)[0] is False
    assert any("kept cover" in p for p in CW.cw3_extract(leaky, F + CPC)[1])
    assert any("not in mode cost_only" in p for p in CW.cw3_extract(b, F + CPC)[1])
    idle = _bundle("record_only", cp=True)
    for s in idle["history"]:
        s["livelihoods"]["clearing_protection"]["counters"]["cover_not_cleared"] = 0.0
    assert CW.cw3_activation(idle, R + CP)[0] is False
    assert CW.cw3_activation(_bundle(), R)[0] is None                      # the root is not judged
    stray = _bundle(cp=True)
    assert any("without the switch" in p for p in CW.cw3_extract(stray, R)[1])


def test_missing_records_are_problems_never_zeros(CW):
    b = _bundle()
    for s in b["history"]:
        del s["food_accounting"]
    m, problems = CW.cw3_extract(b, R)
    assert m["food_shortfall_downstream"] is None and any("could not be measured" in p for p in problems)
    none = copy.deepcopy(b)
    for s in none["history"]:
        del s["livelihoods"]["watershed"]
    assert CW.cw3_extract(none, R)[1] == ["no watershed record"]
    assert CW.cw3_activation(none, F)[0] is None
