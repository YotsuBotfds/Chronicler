"""RS1 rules version 2 and operating wear (PL2) on the real compiled extension.

Template seed 7 (8 regions, 4 civs). Natural activation with ``--workshops
--apprenticeship`` (version 2, source of this lane): sites operate from turn 22;
apprentices who live in a site's region outside its city box attend attached to
the crew, migrants transfer between sites, and the first completions come at
turns 66, 67 and 70, each with attended turns outside the city box
(docs/integration/apprenticeship.md, "RS1 rules version 2").
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

BASE = ["--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only"]


def _run(folder, *extra, seed=7, turns=72):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), *BASE,
        "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json"), *extra])
    execute_run(args)
    return load_bundle(folder / "chronicle_bundle.json")


def test_the_extension_is_the_compiled_build_with_the_v2_seams():
    import importlib
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    assert compiled.__file__.endswith((".so", ".pyd"))
    from chronicler_agents import AgentSimulator
    for name in ("plan_workshop_crews", "reserve_work", "work_reservations", "work_reservation_conflicts",
                 "extend_paid_work", "trip_agent_ids", "take_paid_work_receipt"):
        assert callable(getattr(AgentSimulator, name)), name


def test_v2_apprentices_living_outside_the_city_attend_and_complete(tmp_path, monkeypatch):
    """Every taught apprentice is a living adult farmer of the site's region; one
    on the crew holds only its crew reservation, one attached holds only an
    apprentice reservation of APPRENTICE_FRACTION, after the crew was planned;
    nobody holds two; and apprentices complete with attended turns spent living
    in the region outside the city box."""
    from chronicler import apprenticeship as A
    from chronicler import workshops as W
    outside = defaultdict(int)
    seen = {"attached": 0, "crew": 0, "turns": 0}
    finish = A.finish_phase2

    def checked_finish(world, economy_result, agent_bridge, acc):
        out = finish(world, economy_result, agent_bridge, acc)
        sim = agent_bridge._sim
        state = world.livelihoods.apprenticeship
        assert state.rules_version == 2
        p = state._pending
        reg = sim.work_reservations(world.turn)
        assert sim.work_reservation_conflicts(world.turn) == []
        held = {aid: (cat, f) for aid, cat, f in reg}
        assert len(held) == len(reg)
        snap = sim.get_snapshot()
        cols = {n: snap.column(n).to_pylist() for n in ("id", "age", "occupation", "settlement_id", "region")}
        row = {cols["id"][i]: i for i in range(len(cols["id"]))}
        crews = {r.site: set(r.crew) for r in world.livelihoods.workshops.frame}
        for st in p.sites.values():
            for aid in st.attending:
                i = row[aid]
                assert cols["age"][i] >= 20 and cols["occupation"][i] == 0 and cols["region"][i] == st.region
                if st.aboard[aid] == "crew":
                    assert aid in crews[st.site] and held[aid][0] == 0
                    seen["crew"] += 1
                else:
                    assert aid not in crews[st.site]
                    assert held[aid] == (A.CATEGORY_APPRENTICE, pytest.approx(A.APPRENTICE_FRACTION))
                    seen["attached"] += 1
                    if cols["settlement_id"][i] != st.settlement:
                        outside[aid] += 1
        seen["turns"] += 1
        return out

    monkeypatch.setattr(A, "finish_phase2", checked_finish)
    bundle = _run(tmp_path, "--workshops", "--apprenticeship")
    assert seen["turns"] == 72 and seen["attached"] > 0 and seen["crew"] > 0
    for snap in bundle["history"]:
        rec = snap["livelihoods"]["apprenticeship"]
        assert (rec["schema_version"], rec["rules_version"], rec["stage"]) == (2, 2, "RS1")
        assert rec["source_turn"] == snap["turn"] - 1
        assert "operating_wear" not in snap["livelihoods"]                    # implied, not recorded
        workshops = {r["site"]: r for r in snap["livelihoods"]["workshops"]["receipts"] or []}
        for r in rec["receipts"] or []:
            w = workshops[r["site"]]
            assert 0.0 <= r["upkeep_offset"] <= r["wear"] <= A.OPERATING_WEAR
            if r["operating"]:
                assert r["craft_work"] + r["upkeep_work"] + r["teaching_work"] == pytest.approx(r["crew_work"])
                assert w["craft_ceiling"] == pytest.approx(W.K_RAW_PER_WORK * r["craft_work"], rel=1e-5)
                assert r["covered"] == bool(r["qualified_on_crew"])
                assert r["full_offset"] == (r["upkeep_offset"] >= r["wear"])
                assert sum(r["offset_by_via"].values()) == pytest.approx(r["upkeep_offset"], abs=1e-12)
                assert set(r["graduates_on_crew"]) <= set(r["crew"])
            for s in r["seats"]:
                if s["outcome"] == "attended":
                    assert s["aboard"] in ("crew", "attached") and s["mentor"] in r["qualified_on_crew"]
                    assert (s["aboard"] == "crew") == (s["agent_id"] in r["crew"])
    final = bundle["history"][-1]["livelihoods"]["apprenticeship"]
    done = [a for a in final["archive"] if a["ended_reason"] == "completed"]
    assert done, "seed 7 completes version-2 apprenticeships by turn 72 (first at turn 66)"
    assert any(outside[a["agent_id"]] > 0 and a["attached"] > 0 for a in done)
    assert all(a["attended"] == A.COMPLETION_TURNS and a["granted"] for a in done)
    assert final["counters"]["transferred"] > 0 and final["counters"]["apprentice_turns_attached"] > 0
    assert {g["agent_id"] for g in final["graduates"]} <= {a["agent_id"] for a in done}


def test_v2_exact_checkpoint_resume_inside_live_apprenticeships(tmp_path, monkeypatch):
    import chronicler.main as main_mod
    from chronicler.bundle_codec import load_bundle

    def cli(folder, *argv):
        monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                          "--state", str(folder / "state.json")])
        main_mod.main()

    straight = tmp_path / "straight"
    cli(straight, "--seed", "7", "--turns", "72", *BASE, "--workshops", "--apprenticeship", "--operating-wear",
        "--checkpoint-turns", "62")
    ckpt = straight / "checkpoint_turn_62.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    cli(resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    live = a["history"][61]["livelihoods"]["apprenticeship"]
    assert live["rules_version"] == 2 and live["apprenticeships"] and live["qualifications"]
    assert any(x["attached"] for x in live["apprenticeships"]), "live attached apprenticeships at the checkpoint"
    assert a["history"][61]["livelihoods"]["operating_wear"]["receipts"]
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
    assert a["history"][-1]["livelihoods"]["apprenticeship"]["counters"]["completions"] >= 1


def _operating_turns(bundle):
    """(turn, receipt, condition before the turn) of every operating site-turn."""
    last, out = {}, []
    for snap in bundle["history"]:
        for r in snap["livelihoods"]["workshops"]["receipts"] or []:
            if r.get("allocated"):
                out.append((snap["turn"], r, last.get(r["site"], 1.0)))
            last[r["site"]] = r["condition_after"]
    return out


def test_w_wear_against_w_operate_shows_the_wear(tmp_path):
    """The reference arm with the maintenance assumption: every funded operating
    site-turn of ``--workshops --operating-wear`` loses exactly OPERATING_WEAR
    (no one is qualified without RS1), so sites need lump repairs that
    ``--workshops`` alone never needs; the two worlds are identical until the
    first operating turn (apart from the new record)."""
    from chronicler import operating_wear as OW
    from chronicler import workshops as W
    operate = _run(tmp_path / "operate", "--workshops", turns=72)
    wear = _run(tmp_path / "wear", "--workshops", "--operating-wear", turns=72)
    ops = _operating_turns(operate)
    # Without the switch an operating turn never wears a site (L1 wears it only
    # while unfunded); a repair restores it.
    assert ops and all(r["condition_after"] == (1.0 if "repair" in r["paid"] else before)
                       for _t, r, before in ops)
    first = min(t for t, _r, _b in ops)
    for x, y in zip(operate["history"], wear["history"], strict=True):
        if x["turn"] >= first:
            break
        y = json.loads(json.dumps(y))
        y["livelihoods"].pop("operating_wear")
        assert json.loads(json.dumps(x)) == y
    worn = 0
    for snap in wear["history"]:
        rec = snap["livelihoods"]["operating_wear"]
        assert (rec["schema_version"], rec["stage"], rec["with_apprenticeship"]) == (1, "PL2", False)
        workshops = {r["site"]: r for r in snap["livelihoods"]["workshops"]["receipts"] or []}
        for r in rec["receipts"] or []:
            assert (r["wear"], r["upkeep_offset"], r["net_wear"], r["qualified_on_crew"]) == (
                OW.OPERATING_WEAR, 0.0, OW.OPERATING_WEAR, [])
            assert workshops[r["site"]]["condition_after"] == pytest.approx(r["condition_after"], abs=1e-6)
            assert r["condition_after"] == pytest.approx(max(0.0, r["condition_before"] - OW.OPERATING_WEAR))
            worn += 1
        assert sorted(r["site"] for r in rec["receipts"] or []) == sorted(
            r["site"] for r in snap["livelihoods"]["workshops"]["receipts"] or [] if r.get("allocated"))
    counters = wear["history"][-1]["livelihoods"]["operating_wear"]["counters"]
    assert worn == counters["operating_site_turns"] > 0
    assert counters["wear"] == pytest.approx(worn * OW.OPERATING_WEAR)
    repairs_wear = wear["history"][-1]["livelihoods"]["workshops"]["counters"].get("paid_repair", 0)
    repairs_operate = operate["history"][-1]["livelihoods"]["workshops"]["counters"].get("paid_repair", 0)
    assert repairs_wear == counters["repairs"] * W.REPAIR_COST > repairs_operate == 0


def test_the_switch_adds_only_records_to_an_rs1_run(tmp_path):
    """RS1 implies the wear: adding --operating-wear changes nothing else."""
    rs1 = _run(tmp_path / "rs1", "--workshops", "--apprenticeship", turns=50)
    both = _run(tmp_path / "both", "--workshops", "--apprenticeship", "--operating-wear", turns=50)
    covered = 0
    for x, y in zip(rs1["history"], both["history"], strict=True):
        y = json.loads(json.dumps(y))
        rec = y["livelihoods"].pop("operating_wear")
        assert rec["with_apprenticeship"] is True
        assert json.loads(json.dumps(x)) == y
        appr = {r["site"]: r for r in x["livelihoods"]["apprenticeship"]["receipts"] or []}
        for r in rec["receipts"] or []:
            assert (r["upkeep_offset"], r["net_wear"]) == (appr[r["site"]]["upkeep_offset"],
                                                           appr[r["site"]]["net_wear"])
            covered += bool(r["qualified_on_crew"])
    assert covered > 0
    assert rs1["world_state"] == both["world_state"] or _same_but_record(rs1["world_state"], both["world_state"])


def _same_but_record(a, b):
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    b.get("livelihoods", {}).pop("operating_wear", None)
    return a == b
