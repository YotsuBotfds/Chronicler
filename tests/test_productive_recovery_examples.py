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
        {"agent_id": 13, "ended_reason": "long_absence"}, {"agent_id": 14, "ended_reason": "stalled"}])
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
