"""PL6b: the checkpoint-1 natural example finder on small constructed bundles.

Offline: synthetic dated records (not simulation runs); nothing here runs the
simulation, a native import or a held seed. The finder's record keys are
checked against this checkout's models.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TURNS = 8


@pytest.fixture(scope="module")
def E():
    path = ROOT / "scripts" / "productive_recovery_examples.py"
    spec = importlib.util.spec_from_file_location("productive_recovery_examples_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Constructed bundles ------------------------------------------------------------

MODES = {"timber_supply": "supply", "repair_projects": "repair", "apprenticeship": "train",
         "recovery_crews": "paid", "maintenance_obligation": "reserve", "workshops": "operate"}


def _history(packages):
    hist = []
    for turn in range(1, TURNS + 1):
        liv = {"schema_version": 1}
        for name in packages:
            rec = {"schema_version": 1, "source_turn": turn - 1, "counters": {}}
            if name in MODES:
                rec["mode"] = MODES[name]
            if name == "apprenticeship":
                rec.update(schema_version=2, rules_version=2)
            if name == "workshops":
                rec["parameters"] = {"operate_condition": 0.5}
            liv[name] = rec
        hist.append({"turn": turn, "livelihoods": liv})
    return hist


def _put(hist, turn, name, **rows):
    rec = hist[turn - 1]["livelihoods"][name]
    for key, value in rows.items():
        if isinstance(value, list):
            rec.setdefault(key, []).extend(value)
        else:
            rec[key] = value


def _exp(eid, home, forest, status, ended, **kw):
    return {"eid": eid, "civ": 0, "home": home, "forest": forest, "hops": 1, "launched_turn": 0, "status": status,
            "ended_turn": ended, "launched_crew": [1, 2, 3, 4], "crew": [1], "cut": 5.0, "delivered": 0.0,
            "abandoned": 0.0, "end_reason": None, "drops": [], **kw}


def _project(pid, kind, asset, region, opened, closed=None, status="open", **kw):
    return {"pid": pid, "kind": kind, "asset": asset, "region": region, "cause": "wear", "opened_turn": opened,
            "closed_turn": closed, "opened_condition": 0.7, "scope": 2.4, "delivered": 2.4, "timber_used": 2.4,
            "status": status, "history": [], **kw}


def _wear(turn, site, before, after, offset=0.0, qualified=()):
    return {"turn": turn, "site": site, "region": site, "wear": round(before - after + offset, 6),
            "upkeep_offset": offset, "condition_before": before, "condition_after": after,
            "qualified_on_crew": list(qualified)}


def _bundle():
    hist = _history(["timber_supply", "repair_projects", "apprenticeship", "operating_wear", "workshops",
                     "recovery_crews", "maintenance_obligation"])
    # PL1. Expedition 0 delivers 5 to region 0 (ended turn 1, snapshot 2); RS2
    # holds 2 of it from the store at snapshot 5. Expedition 9 delivered to
    # region 5, whose store was released (snapshot 3) before a later hold there.
    _put(hist, 2, "timber_supply", closed=[_exp(9, 5, 6, "delivered", 0, delivered=1.0),
                                           _exp(0, 0, 1, "delivered", 1, delivered=5.0)],
         stores=[{"region": 0, "held": 0.0}, {"region": 5, "held": 0.0}], store={"0": 5.0, "5": 1.0},
         needs=[{"region": 2, "status": "refused", "reason": "no_crew"},
                {"region": 2, "status": "refused", "reason": "no_forest", "gap": 4.0}])
    _put(hist, 3, "timber_supply", stores=[{"region": 5, "held": 0.0}], store={"0": 5.0})
    _put(hist, 5, "timber_supply", stores=[{"region": 0, "held": 2.0}], store={"0": 3.0})
    _put(hist, 5, "repair_projects", receipts=[{"pid": 0, "kind": "granary", "asset": 0, "region": 0,
                                                "timber_used": 2.0, "credited": 2.0, "status": "progress",
                                                "reasons": []}])
    _put(hist, 4, "timber_supply", stores=[{"region": 5, "held": 1.0}], store={"0": 5.0, "5": 2.0},
         needs=[{"region": 3, "status": "refused", "reason": "too_far"},
                {"region": 4, "status": "refused", "reason": "forest_depleted"}],
         closed=[_exp(1, 1, 2, "abandoned", 3, abandoned=1.5, end_reason="crew_lost", drops=[[3, 4, "died"]]),
                 _exp(3, 1, 2, "abandoned", 3, abandoned=0.0, end_reason="crew_lost")],
         deposits=[[3, 1, 2, 1.5]],
         receipts=[{"eid": 2, "civ": 0, "home": 3, "forest": 4, "stage": "returning", "crew": [7],
                    "recalled": True, "unpaid": True, "cut_end": "recalled"}])
    # Granary project 0 completes at turn 4, after the delivery of turn 1.
    _put(hist, 5, "repair_projects", closed=[_project(0, "granary", 0, 0, 0, 4, "completed"),
                                             _project(4, "granary", 9, 9, 0, 4, "completed")])
    _put(hist, 6, "timber_supply", closed=[_exp(2, 3, 4, "delivered", 5, delivered=2.0, recalled_turn=3,
                                                unpaid_turns=1)])
    # PL2 RS1 rules version 2.
    _put(hist, 2, "apprenticeship", sites=[{"site": 1, "region": 4}, {"site": 0, "region": 0}],
         archive=[{"agent_id": 15, "ended_reason": "completed", "transfers": 0, "granted": True}],
         receipts=[{"site": 0, "region": 0, "operating": True, "crew": [5, 21], "qualified_on_crew": [5],
                    "seats": [{"agent_id": 21, "outcome": "missed", "reason": "no_mentor"}]}])
    _put(hist, 3, "apprenticeship", receipts=[{"site": 0, "region": 0, "operating": True, "crew": [10, 11],
                                               "graduates_on_crew": [11], "qualified_on_crew": [10, 11],
                                               "offset_by_graduates": 0.005, "upkeep_offset": 0.02, "seats": []}])
    _put(hist, 4, "apprenticeship", archive=[
        {"agent_id": 12, "ended_reason": "completed", "transfers": 1, "first_site": 1, "site": 0, "region": 0,
         "granted": True},
        {"agent_id": 13, "ended_reason": "long_absence"}, {"agent_id": 14, "ended_reason": "stalled"}],
         receipts=[{"site": 1, "region": 4, "operating": False, "crew": [], "qualified_on_crew": [],
                    "seats": [{"agent_id": 22, "outcome": "missed", "reason": "no_mentor"}]}])
    _put(hist, 5, "apprenticeship", receipts=[{"site": 1, "region": 4, "operating": True, "crew": [20],
                                               "qualified_on_crew": [],
                                               "seats": [{"agent_id": 22, "outcome": "missed",
                                                          "reason": "no_mentor"}]}])
    # Operating wear. Site 0 wears from full condition below the floor with no
    # qualified upkeep and is lump-repaired at snapshot 5; site 1 had qualified
    # upkeep and site 2 other wear between its operating turns (not counted).
    _put(hist, 2, "operating_wear", receipts=[_wear(1, 0, 1.0, 0.7), _wear(1, 1, 1.0, 0.75, 0.05, [8]),
                                              _wear(1, 2, 1.0, 0.7), _wear(1, 3, 1.0, 0.85)])
    _put(hist, 3, "operating_wear", receipts=[_wear(2, 0, 0.7, 0.4), _wear(2, 1, 0.75, 0.45),
                                              _wear(2, 2, 0.6, 0.3), _wear(2, 3, 0.85, 0.7)])
    _put(hist, 4, "workshops", receipts=[{"site": 1, "region": 1, "paid": {"repair": 20}},
                                         {"site": 2, "region": 2, "paid": {"repair": 20}}])
    _put(hist, 5, "workshops", receipts=[{"site": 0, "region": 0, "payer": 0, "paid": {"repair": 20},
                                          "condition_after": 0.98}])
    # Site 3 wore to an RS2 project (opened turn 2 at its condition then), rebuilt at turn 5.
    _put(hist, 6, "repair_projects", closed=[_project(7, "workshop", 3, 3, 2, 5, "completed",
                                                      opened_condition=0.7)])
    # PL3 recovery crews and the maintenance obligation.
    _put(hist, 2, "recovery_crews", receipts=[
        {"pid": 0, "kind": "granary", "region": 0, "payer": 0, "wages_milli": 0, "members": []},
        {"pid": 0, "kind": "granary", "region": 0, "payer": 0, "wages_milli": 2000, "delivered": 1.0,
         "members": [{"agent_id": 30, "origin": "rural_farmer", "worked": 1.0, "wage_milli": 2000,
                      "veteran": False}]}])
    _put(hist, 3, "recovery_crews", receipts=[
        {"pid": 1, "kind": "workshop", "region": 1, "payer": 0,
         "members": [{"agent_id": 31, "origin": "veteran", "veteran": True}]},
        {"pid": 2, "kind": "granary", "region": 2, "payer": 0, "short": True, "planned": 4.0, "capacity": 1.0,
         "members": [{"agent_id": 32, "origin": "rural_farmer", "veteran": False}]}])
    _put(hist, 3, "repair_projects", receipts=[{"pid": 2, "kind": "granary", "region": 2, "status": "progress",
                                                "reasons": ["no_labor"]}])
    _put(hist, 2, "maintenance_obligation", uses=[{"civ": 0, "reserved": 3, "used": 3, "returned": 0}])
    _put(hist, 4, "maintenance_obligation", uses=[{"civ": 1, "reserved": 2, "used": 0, "returned": 2}])
    # RS2 no_people: project 5 suspended at turn 2 (snapshot 3) and resumed at turn 5 (snapshot 6).
    suspended = _project(5, "granary", 6, 6, 1, history=[[1, "opened", 0, 0], [2, "suspended_no_people", 0, 0]])
    _put(hist, 3, "repair_projects", projects=[suspended])
    _put(hist, 6, "repair_projects", projects=[{**suspended, "history": [*suspended["history"],
                                                                      [5, "resumed", 0, 0]]}])
    _put(hist, 4, "repair_projects", unmet=[{"kind": "granary", "asset": 7, "region": 7, "condition": 0.6,
                                             "reason": "no_people"}])
    return {"metadata": {"seed": 1}, "history": hist, "world_state": {}}


# --- Tests ------------------------------------------------------------------------


def test_the_record_keys_read_are_the_sources_own(E):
    E.check_fields()


def test_every_kind_is_found_at_its_snapshot_with_its_ids(E):
    found = E.find(_bundle())
    assert set(found) == set(E.FINDERS)
    ts = found["PL1 timber_supply"]
    turn, row = ts["success: an expedition delivers timber that RS2 then holds from the store"]
    assert (turn, row["eid"], row["home"], row["delivered_snapshot"], row["store_held"]) == (5, 0, 0, 2, 2.0)
    assert [r["pid"] for r in row["rs2_projects"]] == [0]
    turn, row = ts["success: a granary project completes after a delivery to its region"]
    assert (turn, row["pid"], [d["eid"] for d in row["deliveries"]], row["store_held_while_open"]) == (5, 0, [0], 2.0)
    for reason, (snapshot, region) in {"no_forest": (2, 2), "too_far": (4, 3), "forest_depleted": (4, 4)}.items():
        turn, row = ts[f"failure: a need refused for want of forest ({reason})"]
        assert (turn, row["region"], row["reason"]) == (snapshot, region, reason)
    turn, row = ts["failure: a crew lost and its cargo abandoned to the forest commons"]
    assert (turn, row["eid"], row["abandoned"], row["deposits"]) == (4, 1, 1.5, [[3, 1, 2, 1.5]])
    turn, row = ts["failure: a crew recalled for want of coins"]
    assert (turn, row["eid"], row["ended"]["snapshot"], row["ended"]["status"]) == (4, 2, 6, "delivered")

    ap = found["PL2 apprenticeship (rules version 2)"]
    turn, row = ap["success: a graduate on an operating crew gives upkeep offset"]
    assert (turn, row["site"], row["graduates_on_crew"]) == (3, 0, [11])
    turn, row = ap["success: an apprentice who transferred regions completed"]
    assert (turn, row["agent_id"], row["first_site"], row["first_region"], row["region"]) == (4, 12, 1, 4, 0)
    assert ap["failure: an apprenticeship ends long_absence"][1]["agent_id"] == 13
    assert ap["failure: an apprenticeship ends stalled"][1]["agent_id"] == 14
    turn, row = ap["failure: an apprentice misses teaching with no mentor aboard (no_mentor)"]
    assert (turn, row["site"], row["missed"]) == (5, 1, [{"agent_id": 22, "reason": "no_mentor"}])
    assert ap["control: a completion that grants no qualification (no_qualification)"].startswith("not applicable")

    ow = found["PL2 operating_wear"]
    turn, row = ow["failure: a site worn below the operating floor for want of qualified upkeep, then an L1 lump repair"]
    assert (turn, row["site"], row["worn_turns"], row["condition_before"], row["condition_after"]) == (5, 0, 2, 1.0, 0.4)
    assert (row["upkeep_offset"], row["repair_paid"]) == (0, 20)
    turn, row = ow["failure: a site worn to an RS2 project for want of qualified upkeep, then rebuilt by it"]
    assert (turn, row["pid"], row["asset"], row["worn_turns"]) == (6, 7, 3, 2)

    rc = found["PL3 recovery_crews"]
    turn, row = rc["success: wages paid to a named granary crew"]
    assert (turn, row["pid"], row["members"]) == (2, 0, [{"agent_id": 30, "origin": "rural_farmer", "worked": 1.0,
                                                          "wage_milli": 2000}])
    turn, row = rc["success: a veteran placed on a repair crew"]
    assert (turn, row["kind"], row["members"][0]["agent_id"]) == (3, "workshop", 31)
    turn, row = rc["failure: a granary crew short of farmers (short / no_labor)"]
    assert (turn, row["pid"], row["members"], row["rs2"]) == (3, 2, [32], [{"status": "progress",
                                                                            "reasons": ["no_labor"]}])
    mo = found["PL3 maintenance_obligation"]
    assert mo["success: an obligation reservation used"] == (2, {"civ": 0, "reserved": 3, "used": 3, "returned": 0})
    assert mo["failure: a reservation returned unspent"][0] == 4
    rs2 = found["RS2 no_people correction (repair_projects)"]
    turn, row = rs2["failure: a granary project suspended no_people and later resumed"]
    assert (turn, row["pid"], row["suspended_turn"], row["resumed_turn"]) == (6, 5, 2, 5)
    turn, row = rs2["failure: a worn granary with no project for want of people (unmet no_people)"]
    assert (turn, row["asset"]) == (4, 7)


def test_only_dated_records_are_read_never_the_final_state(E):
    bundle = _bundle()
    bundle["world_state"] = {"livelihoods": {"maintenance_obligation": {"uses": [{"used": 5, "returned": 5}]}}}
    hist = bundle["history"]
    for snap in hist:
        snap["livelihoods"]["maintenance_obligation"]["uses"] = None        # no settled Phase 2
    found = E.find(bundle)["PL3 maintenance_obligation"]
    assert set(found.values()) == {None}


def test_absent_kinds_and_packages_say_so(E):
    hist = _history(["timber_supply", "repair_projects", "apprenticeship", "operating_wear", "workshops"])
    for snap in hist:
        snap["livelihoods"]["apprenticeship"]["mode"] = "no_qualification"
    found = E.find({"history": hist})
    assert set(found) == {"PL1 timber_supply", "PL2 apprenticeship (rules version 2)", "PL2 operating_wear",
                          "RS2 no_people correction (repair_projects)"}
    assert all(v is None for v in found["PL1 timber_supply"].values())
    assert all(v is None for v in found["PL2 apprenticeship (rules version 2)"].values())
    ow = found["PL2 operating_wear"]
    lump, rebuilt = ow.values()
    assert lump.startswith("none found (RS2 owns workshop repair") and rebuilt is None
    # Without RS2 the L1 lump is billed and the RS2 kind does not apply.
    hist = _history(["apprenticeship", "operating_wear", "workshops"])
    for snap in hist:
        snap["livelihoods"]["apprenticeship"].update(schema_version=1, rules_version=None)
    found = E.find({"history": hist})
    lump, rebuilt = found["PL2 operating_wear"].values()
    assert lump is None and rebuilt == "not applicable (no repair_projects record)"
    assert all(v.startswith("not applicable (the run's RS1 records are rules version 1)")
               for v in found["PL2 apprenticeship (rules version 2)"].values())


def test_a_control_completion_without_a_grant_is_found(E):
    hist = _history(["apprenticeship"])
    for snap in hist:
        snap["livelihoods"]["apprenticeship"]["mode"] = "no_qualification"
    _put(hist, 7, "apprenticeship", archive=[{"agent_id": 40, "ended_reason": "completed", "granted": False}])
    found = E.find({"history": hist})["PL2 apprenticeship (rules version 2)"]
    assert found["control: a completion that grants no qualification (no_qualification)"][0] == 7
    assert found["success: an apprentice who transferred regions completed"] is None


def test_main_prints_each_kind_from_a_written_bundle(E, tmp_path, capsys):
    from chronicler.bundle_codec import dumps_bundle
    path = tmp_path / "chronicle_bundle.json"
    path.write_text(dumps_bundle(_bundle()), encoding="utf-8")
    assert E.main([]) == 2
    capsys.readouterr()
    assert E.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "(seed 1, 8 snapshots; natural;" in out and "RS1 rules 2" in out
    assert "    success: an expedition delivers timber that RS2 then holds from the store: snapshot 5: {" in out
    assert "    failure: a granary project suspended no_people and later resumed: snapshot 6: {" in out
    assert "not recorded" not in out and "none found" not in out
    lone = tmp_path / "lone.json"
    lone.write_text(dumps_bundle({"metadata": {"seed": 2}, "history": _history(["recovery_crews"])}),
                    encoding="utf-8")
    assert E.main([str(lone)]) == 0
    out = capsys.readouterr().out
    assert "  PL1 timber_supply: not recorded in this run" in out
    assert "    success: wages paid to a named granary crew: none found" in out


# --- Checkpoint 3: the chain mode (PL6d, ``--chain``) -----------------------------------

CHAIN_TURNS = 10
DRAWDOWN = ("tradeoff: the forest stand drawn down by a cut (the largest one-turn harvest fall while cutting: "
            "the stand within capacity before minus after, i.e. extraction net of regrowth; L3's whole change, "
            "cover loss included, beside it)")


def _chain_bundle():
    """A constructed chain. Granary project 0 (region 1) stalls ``no_timber`` at
    snapshots 2-3; expedition 5 from region 1 (launched turn 2, crew 10 and 11) cuts at
    forest 2 and delivers 4.0 at turn 5; RS2 holds it from the store at snapshots 7-8
    (project 0 the only holder), PL3 pays crew 20 and 21 there; region 1 (a paid_work
    pilot from turn 6) buys food at snapshots 8-9; crew member 20 is fed in the sample at
    snapshot 9 and the household keyed by 21 is priced out there. Near misses: project 1
    (region 2) gets no expedition; project 2 (region 1) stalls after the launch; crew
    member 21 priced out in the very turn he was paid (snapshot 7) is not a hit."""
    hist = []
    for turn in range(1, CHAIN_TURNS + 1):
        liv = {"schema_version": 1}
        for name, mode in (("repair_projects", "repair"), ("timber_supply", "supply"), ("recovery_crews", "paid"),
                           ("household_retail", "retail"), ("timber_stock", None)):
            rec = {"schema_version": 1, "source_turn": turn - 1, "counters": {}}
            if mode:
                rec["mode"] = mode
            liv[name] = rec
        liv["household_retail"].update(boundary="paid_work", sample=[],
                                       sample_columns=["agent_id", "region", "household", "ration", "fair_share",
                                                       "status"])
        food = [{"region_id": i, "native": {"demand": 10.0}, "sufficiency_after_relief": 1.0} for i in range(4)]
        hist.append({"turn": turn, "livelihoods": liv, "food_accounting": {"source_turn": turn - 1, "regions": food}})

    def put(T, name, **rows):
        _put(hist, T, name, **rows)

    def rs2(T, pid, region, status, reasons, used=0.0, kind="granary"):
        return {"turn": T - 1, "pid": pid, "kind": kind, "asset": 3 + pid, "region": region, "status": status,
                "reasons": reasons, "condition_before": 0.6, "condition_after": 0.6 + 0.025 * used,
                "timber_held": used, "timber_used": used, "crew": [], "wages_milli": 0}

    for T in (2, 3):
        put(T, "repair_projects", receipts=[rs2(T, 0, 1, "stalled", ["no_timber"]),
                                            rs2(T, 1, 2, "stalled", ["no_timber", "no_coins"])])
    put(3, "repair_projects", projects=[{"pid": 0, "region": 1}, {"pid": 1, "region": 2}])
    put(3, "timber_supply", needs=[{"region": 1, "want": 4.0, "free": 0.0, "gap": 4.0, "status": "launched", "eid": 5}])
    stages = {3: "outbound", 4: "cutting", 5: "cutting", 6: "returning"}
    for T, stage in stages.items():
        rx = {"turn": T - 1, "eid": 5, "home": 1, "forest": 2, "slot": 0, "stage": stage, "crew": [10, 11],
              "wages_milli": 1000, "away_delivered": 2.0 if T == 4 else 0.0, "cut": 2.05 if stage == "cutting" else 0.0,
              "cut_end": None, "cargo_after": 0.0}
        if stage == "cutting":
            rx.update(stock_before=100.0 if T == 4 else 99.0, stock_after=99.5 if T == 4 else 97.5, capacity=100.0)
        put(T, "timber_supply", receipts=[rx])
    for T in (4, 5):
        put(T, "timber_stock", regions=[{"region_id": 2, "slot": 0, "opening": 100.0, "cleared": 0.0,
                                         "extraction": 2.05, "regrowth": 0.5, "stock": 98.45, "capacity": 100.0}])
    hist[3]["food_accounting"]["regions"][1]["sufficiency_after_relief"] = 0.8      # snapshot 4: region 1 short
    expedition = {"eid": 5, "civ": 0, "home": 1, "forest": 2, "hops": 1, "launched_turn": 2, "ended_turn": 5,
                  "status": "delivered", "launched_crew": [10, 11, 12], "crew": [10, 11], "cut": 4.1,
                  "delivered": 4.0, "wages_milli": 4000, "away_delivered": 2.0}
    for T in range(6, CHAIN_TURNS + 1):
        put(T, "timber_supply", closed=[expedition])
    put(6, "timber_supply", stores=[{"region": 1, "opening": 0.0, "held": 0.0, "delivered": 4.0, "released": 0.0,
                                     "closing": 4.0}])
    put(7, "timber_supply", stores=[{"region": 1, "opening": 4.0, "held": 2.0, "delivered": 0.0, "released": 0.0,
                                     "closing": 2.0}])
    put(8, "timber_supply", stores=[{"region": 1, "opening": 2.0, "held": 2.0, "delivered": 0.0, "released": 0.0,
                                     "closing": 0.0}])
    for T in (7, 8):
        put(T, "repair_projects", receipts=[rs2(T, 0, 1, "progress", [], used=2.0)])
        members = [{"agent_id": 20, "origin": "rural_farmer", "wage_milli": 2000},
                   {"agent_id": 21, "origin": "rural_farmer", "wage_milli": 1500}]
        put(T, "recovery_crews", receipts=[{"turn": T - 1, "pid": 0, "kind": "granary", "region": 1,
                                            "members": members}])
    put(9, "repair_projects", receipts=[rs2(9, 2, 1, "stalled", ["no_timber"])],
        closed=[{"pid": 0, "region": 1, "status": "completed", "closed_turn": 8}])
    put(10, "repair_projects", closed=[{"pid": 0, "region": 1, "status": "completed", "closed_turn": 8}])
    for T in (7, 8, 9):
        prov = {"persons": 20.0, "priced_out_persons": 1.0, "sold_milli": 3000.0,
                "paid_milli": 0.0 if T == 7 else 3000.0}
        put(T, "household_retail", regions=[{"region": 1, "price_milli": 400, "provisioning": prov}])
    put(7, "household_retail", sample=[[21, 1, 21, 0.5, 0.8, 1]])                  # paid that same turn: no hit
    put(9, "household_retail", sample=[[20, 1, 20, 1.0, 1.0, 0], [30, 1, 21, 0.5, 0.8, 1]])
    for T in range(7, CHAIN_TURNS + 1):
        put(T, "household_retail", log=[{"turn": 6, "region": 1, "kind": "pilot_opened", "note": "paid_work"}])
    return {"metadata": {"seed": 3}, "history": hist}


def test_the_chain_is_traced_link_by_link_with_ids_and_regions(E):
    found = E.find_chain(_chain_bundle())
    chain = found["chain"]
    inst = chain["instance"]
    assert (inst["pid"], inst["region"], inst["depth"], inst["id_to_food"], inst["id_to_food_in_region"]) == \
        (0, 1, 5, True, True)
    l1, l2, l3, l4, l5 = inst["links"]
    assert (l1["snapshot"], l1["pid"], l1["stalled_no_timber_snapshots"], l1["by"]) == (2, 0, 2, "id (pid)")
    assert (l2["snapshot"], l2["eid"], l2["launched_turn"], l2["delivered"]) == (6, 5, 2, 4.0)
    assert l2["need_at_launch"] == {"want": 4.0, "free": 0.0, "gap": 4.0, "status": "launched"}
    assert l2["open_projects_in_region_at_launch"] == [0] and l2["project_was_the_region_s_only_open_project"]
    assert l2["by"].startswith("id (eid, crew); region for the project")
    assert (l3["snapshots"], l3["store_held"], l3["project_timber_used"], l3["completed_snapshot"]) == \
        ([7, 8], 4.0, 4.0, 9)
    assert l3["by"].startswith("id (pid; the project was the only one")
    assert l4["snapshot"] == 7 and l4["expedition_crew_first_paid_snapshot"] == 3
    assert l4["repair_crew"] == {20: {"first_snapshot": 7, "wage_milli": 4000, "origin": "rural_farmer"},
                                 21: {"first_snapshot": 7, "wage_milli": 3000, "origin": "rural_farmer"}}
    assert l4["expedition_crew"][10] == {"first_snapshot": 3, "paid_turns": 4, "wage_milli": 2000}
    # Purchases after the repair crew's first wage (snapshot 7): snapshots 8 and 9.
    assert (l5["snapshot"], l5["region_purchase_snapshots"], l5["region_paid_milli"]) == (8, 2, 6000.0)
    assert l5["region_pilot_opened"] == {"turn": 6, "note": "paid_work"}
    assert l5["first_purchase"] == {"snapshot": 8, "price_milli": 400, "persons": 20.0, "priced_out_persons": 1.0,
                                    "sold_milli": 3000.0, "paid_milli": 3000.0}
    assert [(h["snapshot"], h["agent_id"], h["who"], h["status"]) for h in l5["sample"]] == \
        [(9, 20, "self", "fed"), (9, 30, "household", "priced_out")]
    assert l5["by"].startswith("region (purchases) and id (the person sample")
    assert chain["funnel"] == {"projects stalled no_timber": 3,
                               "an expedition from the region delivered after the stall": 1,
                               "the repair used the delivered timber": 1, "named workers paid": 1,
                               "the region's households bought food later": 1,
                               "a paid crew member or their household in the retail sample later": 1,
                               "... in the chain's region": 1, "... the repair crew there after its repair wage": 1,
                               "the store link joined by id (the project the region's only holder)": 1}
    # The repair crew (paid from snapshot 7) is in the sample at snapshot 9: 20 itself
    # and the household keyed by 21.
    assert l5["repair_crew_sample_hits_in_region"] == 2 and inst["repair_crew_to_food_in_region"]
    assert E._id_links(inst) == 3


def test_a_missing_link_is_named_and_a_shared_store_is_traced_by_region(E):
    bundle = _chain_bundle()
    hist = bundle["history"]
    # Another project in the region holds timber in the repair turn: the store link is regional.
    hist[6]["livelihoods"]["repair_projects"]["receipts"].append(
        {"turn": 6, "pid": 9, "kind": "workshop", "asset": 1, "region": 1, "status": "progress", "reasons": [],
         "condition_before": 0.4, "condition_after": 0.5, "timber_held": 1.0, "timber_used": 1.0, "crew": [],
         "wages_milli": 0})
    l3 = E.find_chain(bundle)["chain"]["instance"]["links"][2]
    assert l3["by"].startswith("region") and l3["other_projects_holding_timber"] == [9]
    # Without the store rows the chain stops at link 2, with the reason.
    for T in (7, 8):
        hist[T - 1]["livelihoods"]["timber_supply"]["stores"] = []
    inst = E.find_chain(bundle)["chain"]["instance"]
    assert inst["depth"] == 2
    assert inst["missing"] == "the delivered timber was not used by this project: no store row after the delivery"
    # Without the delivery it stops at link 1.
    for snap in hist:
        snap["livelihoods"]["timber_supply"]["closed"] = []
    inst = E.find_chain(bundle)["chain"]["instance"]
    assert inst["depth"] == 1 and inst["missing"].startswith("no expedition from the region delivered")


def _unused_delivery(bundle, stores):
    """Project 0 holds and uses no timber at snapshots 7-8 (stalled no_labor); the
    region's store rows from snapshot 7 on are ``stores`` (snapshot -> row)."""
    hist = bundle["history"]
    for T in (7, 8):
        rx = hist[T - 1]["livelihoods"]["repair_projects"]["receipts"][0]
        rx.update(status="stalled", reasons=["no_labor"], timber_held=0.0, timber_used=0.0)
    for T in range(7, CHAIN_TURNS + 1):
        hist[T - 1]["livelihoods"]["timber_supply"]["stores"] = [stores[T]] if T in stores else []
    return bundle


def _store(opening, closing, held=0.0, released=0.0):
    return {"region": 1, "opening": opening, "held": held, "delivered": 0.0, "released": released,
            "returned": 0.0, "closing": closing}


def test_an_unused_delivery_states_what_became_of_it(E):
    # Still in the store at the end of the run.
    bundle = _unused_delivery(_chain_bundle(), {T: _store(4.0, 4.0) for T in range(7, CHAIN_TURNS + 1)})
    inst = E.find_chain(bundle)["chain"]["instance"]
    assert inst["depth"] == 2
    assert inst["missing"] == ("the delivered timber was not used by this project: 4 still in the store, unused, "
                               "when the run ended")
    window = inst["link3_window"]
    assert (window["snapshots"], window["ended_by"], window["left_in_store"]) == ([7, 10], "the run ended", 4.0)
    assert window["project_receipts"] == {"stalled: no_labor": 2}
    assert window["project_closed"] == {"status": "completed", "closed_turn": 8}
    # Released to the stockpile.
    bundle = _unused_delivery(_chain_bundle(), {7: _store(4.0, 0.0, released=4.0)})
    inst = E.find_chain(bundle)["chain"]["instance"]
    assert inst["missing"] == ("the delivered timber was not used by this project: 4 released to the region's "
                               "stockpile (no open project)")
    assert inst["link3_window"]["ended_by"] == "the store emptied"
    # Held while another project held timber.
    bundle = _unused_delivery(_chain_bundle(), {7: _store(4.0, 2.0, held=2.0), 8: _store(2.0, 0.0, held=2.0)})
    for T in (7, 8):
        bundle["history"][T - 1]["livelihoods"]["repair_projects"]["receipts"].append(
            {"turn": T - 1, "pid": 9, "kind": "workshop", "asset": 1, "region": 1, "status": "progress", "reasons": [],
             "condition_before": 0.4, "condition_after": 0.5, "timber_held": 2.0, "timber_used": 2.0, "crew": [],
             "wages_milli": 0})
    inst = E.find_chain(bundle)["chain"]["instance"]
    assert inst["missing"] == ("the delivered timber was not used by this project: 4 held from the store while other "
                               "projects [9] held timber and this one used none")
    assert inst["link3_window"]["other_holders"] == [9]


def test_the_chain_tradeoffs_are_found_with_their_ids(E):
    trade = E.find_chain(_chain_bundle())["tradeoffs"]
    turn, away = trade["tradeoff: crew farm labour away while the home region was short of food (first with home "
                       "pilot persons priced out that turn, else the first short)"]
    assert (turn, away["eid"], away["crew"], away["home_shortfall"]) == (4, 5, [10, 11], pytest.approx(2.0))
    turn, cut = trade[DRAWDOWN]
    # The receipt's fall (99.0 -> 97.5) is the harvest net of regrowth; L3's own change
    # that turn (opening 100 -> 98.45) has no cover loss, so extraction drives it.
    assert (turn, cut["eid"], cut["harvest_fall"], cut["l3_row"]["extraction"]) == (5, 5, 1.5, 2.05)
    assert (cut["l3_fall"], cut["l3_fall_driven_by"]) == (pytest.approx(1.55), "extraction net of regrowth")
    assert trade["tradeoff: the guard ended a cutting stage (forest_depleted)"] is None
    turn, family = trade["tradeoff: a family priced out after its crew member's wages ended"]
    assert (turn, family["crew_member"], family["who"], family["priced_out_person"]) == (9, 21, "household", 30)
    assert (family["wage_snapshots"], family["wage_sources"], family["wages_milli"]) == ([7, 8], ["pl3_granary"], 3000)
    assert family["wage_regions"] == [1]
    assert (family["last_wage_snapshot"], family["turns_since_last_wage"], family["paid_again_later"]) == (8, 1, False)
    assert trade["counts"] == {"away crew-turns": 1, "away crew-turns with the home region short": 1,
                               "cutting turns": 2, "cutting turns whose stand fell by harvest net of regrowth": 2,
                               "cutting turns whose L3 stock fell in all (cover loss included)": 2,
                               "priced-out sample rows after a crew member's wages ended": 1}


def test_a_drawdown_under_cover_loss_names_what_drove_l3s_change(E):
    bundle = _chain_bundle()
    # Snapshot 5: the stand loses 5.5 of cover as well; the receipt's harvest fall is
    # unchanged (1.5) but L3's whole change is 7.0, driven by the cover loss.
    bundle["history"][4]["livelihoods"]["timber_stock"]["regions"] = [
        {"region_id": 2, "slot": 0, "opening": 104.5, "cleared": 5.5, "extraction": 2.05, "regrowth": 0.55,
         "stock": 97.5, "capacity": 100.0}]
    turn, cut = E.find_chain(bundle)["tradeoffs"][DRAWDOWN]
    assert (turn, cut["harvest_fall"], cut["l3_fall"], cut["l3_fall_driven_by"]) == \
        (5, 1.5, pytest.approx(7.0), "cover loss (cleared)")


def _with_workshop_crew(bundle):
    """Snapshot 9: RS2 workshop project 7 (region 1) pays its PL3-widened crew 21 and 40
    (400 milli on the RS2 receipt); PL3's receipt of the same project lists them with
    wage 0, as recovery_crews does for every workshop crew. Snapshot 10: 40 is priced out."""
    hist = bundle["history"]
    hist[8]["livelihoods"]["repair_projects"]["receipts"].append(
        {"turn": 8, "pid": 7, "kind": "workshop", "asset": 2, "region": 1, "status": "progress", "reasons": [],
         "condition_before": 0.4, "condition_after": 0.45, "timber_held": 0.2, "timber_used": 0.2,
         "crew": [21, 40], "wages_milli": 400})
    _put(hist, 9, "recovery_crews", receipts=[
        {"turn": 8, "pid": 7, "kind": "workshop", "region": 1,
         "members": [{"agent_id": 21, "origin": "rural_farmer", "wage_milli": 0},
                     {"agent_id": 40, "origin": "veteran", "wage_milli": 0}]}])
    _put(hist, 10, "household_retail", sample=[[40, 1, 40, 0.4, 0.7, 1]])
    return bundle


def test_rs2_workshop_wages_of_a_pl3_widened_crew_are_counted_once(E):
    bundle = _with_workshop_crew(_chain_bundle())
    paid = E._wage_snapshots(E._chain_index(bundle["history"]))
    assert paid[21] == {7: [1500, ["pl3_granary"], [1]], 8: [1500, ["pl3_granary"], [1]],
                        9: [200, ["rs2_workshop"], [1]]}
    assert paid[40] == {9: [200, ["rs2_workshop"], [1]]}
    # 21 was still paid (as a workshop repairer) at snapshot 9, so the household keyed by
    # 21 priced out there is not "after the wages ended"; 40 priced out at 10 is.
    trade = E.find_chain(bundle)["tradeoffs"]
    turn, family = trade["tradeoff: a family priced out after its crew member's wages ended"]
    assert (turn, family["crew_member"], family["who"], family["wage_sources"]) == (10, 40, "self", ["rs2_workshop"])
    assert (family["wage_snapshots"], family["wages_milli"], family["paid_again_later"]) == ([9], 200, False)
    # A PL3 receipt that does carry wages is counted, and its RS2 receipt then is not.
    bundle["history"][8]["livelihoods"]["recovery_crews"]["receipts"][-1]["members"][1]["wage_milli"] = 200
    paid = E._wage_snapshots(E._chain_index(bundle["history"]))
    assert paid[40] == {9: [200, ["pl3_workshop"], [1]]} and 9 not in paid[21]


def test_a_sample_row_of_two_paid_workers_counts_once(E):
    bundle = _chain_bundle()
    # Snapshot 10: person 21, whose household is keyed by 20, both of the repair crew.
    _put(bundle["history"], 10, "household_retail", sample=[[21, 1, 20, 1.0, 1.0, 0]])
    l5 = E.find_chain(bundle)["chain"]["instance"]["links"][4]
    rows = [(h["snapshot"], h["agent_id"], h["who"], h["crew_members"]) for h in l5["sample"]]
    assert rows == [(9, 20, "self", [20]), (10, 21, "self", [21, 20]), (9, 30, "household", [21])]
    assert l5["sample_hits"] == 3 and l5["repair_crew_sample_hits_in_region"] == 3
    # A priced-out row of two former workers is one tradeoff row too.
    _put(bundle["history"], 10, "household_retail", sample=[[20, 1, 21, 0.5, 0.8, 1]])
    counts = E.find_chain(bundle)["tradeoffs"]["counts"]
    assert counts["priced-out sample rows after a crew member's wages ended"] == 2      # snapshots 9 and 10


def test_the_chain_mode_says_what_a_run_does_not_record(E):
    hist = _history(["timber_supply", "repair_projects"])
    found = E.find_chain({"history": hist})
    assert found["chain"] == "not recorded in this run (no household_retail record)"
    assert found["tradeoffs"]["tradeoff: a family priced out after its crew member's wages ended"] \
        == "not applicable (no household_retail person sample)"
    found = E.find_chain({"history": _history(["recovery_crews"])})
    assert found["tradeoffs"] == "not recorded in this run (no timber_supply record)"
    # Only dated records are read. A final state shaped like a snapshot that holds a
    # delivery, its store and another stall would change the result if it were read.
    bundle = _chain_bundle()
    hist = bundle["history"]
    delivery = hist[-1]["livelihoods"]["timber_supply"]["closed"]
    for snap in hist:
        snap["livelihoods"]["timber_supply"]["closed"] = []
    bundle["world_state"] = {"turn": CHAIN_TURNS + 1, "livelihoods": {
        "timber_supply": {"closed": delivery, "stores": [{"region": 1, "opening": 4.0, "held": 4.0, "delivered": 0.0,
                                                          "released": 0.0, "closing": 0.0}]},
        "repair_projects": {"receipts": [{"turn": CHAIN_TURNS, "pid": 50, "kind": "granary", "asset": 9,
                                          "region": 3, "status": "stalled", "reasons": ["no_timber"],
                                          "condition_before": 0.5, "condition_after": 0.5, "timber_held": 0.0,
                                          "timber_used": 0.0, "crew": [], "wages_milli": 0}]}}}
    chain = E.find_chain(bundle)["chain"]
    assert chain["instance"]["depth"] == 1 and chain["funnel"]["projects stalled no_timber"] == 3


def test_main_prints_the_chain_from_a_written_bundle(E, tmp_path, capsys):
    from chronicler.bundle_codec import dumps_bundle
    path = tmp_path / "chronicle_bundle.json"
    path.write_text(dumps_bundle(_chain_bundle()), encoding="utf-8")
    assert E.main(["--chain"]) == 2
    capsys.readouterr()
    assert E.main(["--chain", str(path)]) == 0
    out = capsys.readouterr().out
    assert "(seed 3, 10 snapshots; natural;" in out and '"household_retail_boundary": "paid_work"' in out
    assert "  chain: project 0 (region 1), 5 of 5 links" in out
    assert "    link 3 (id (pid; the project was the only one in the region holding timber)): snapshot 7: {" in out
    assert "    tradeoff: a family priced out after its crew member's wages ended: snapshot 9: {" in out
    assert "    tradeoff: the guard ended a cutting stage (forest_depleted): none found" in out
