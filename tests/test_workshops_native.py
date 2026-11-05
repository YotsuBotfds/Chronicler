"""L1A workshop contract on the real compiled extension (no funded operation)."""
import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def _run(tmp_path, *extra, seed=7, turns=40):
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import _build_parser, execute_run
    args = _build_parser().parse_args([
        "--seed", str(seed), "--turns", str(turns), "--civs", "4", "--regions", "8",
        "--agents", "hybrid", "--simulate-only",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json"), *extra])
    execute_run(args)
    return load_bundle(tmp_path / "chronicle_bundle.json")


def test_crews_are_live_eligible_farmers_and_inputs_match_native_output(tmp_path, monkeypatch):
    from chronicler import workshops as W
    checked = {"crew": 0, "receipts": 0}
    original = W.finish_phase2

    def checked_finish(world, economy_result, agent_bridge, acc):
        plan = world.livelihoods.workshops._plan
        snap = agent_bridge._sim.get_snapshot()
        cols = {name: snap.column(name).to_pylist() for name in
                ("id", "age", "occupation", "settlement_id", "region")}
        rows = {cols["id"][i]: i for i in range(len(cols["id"]))}
        seen = set()
        for row in (site_plan.row for site_plan in plan.sites):
            assert len(row["crew"]) <= 8 and row["eligible"] >= len(row["crew"])
            assert row["crew"] == sorted(row["crew"])
            for aid in row["crew"]:
                i = rows[aid]
                assert cols["age"][i] >= 20 and cols["occupation"][i] == 0   # Farmer
                assert cols["settlement_id"][i] == row["settlement_id"] and cols["region"][i] == row["region"]
                assert aid not in seen
                seen.add(aid)
                checked["crew"] += 1
        return original(world, economy_result, agent_bridge, acc)

    monkeypatch.setattr(W, "finish_phase2", checked_finish)
    bundle = _run(tmp_path, "--workshops", "--workshop-mode", "observe")
    for snap in bundle["history"]:
        for r in snap["livelihoods"]["workshops"]["receipts"] or []:
            checked["receipts"] += 1
            inputs = r["region_craft_input"]
            assert inputs is not None and r["region_craft_output"] is not None
            # Native conservation: the crafted wares equal the raw inputs consumed.
            assert sum(inputs.values()) == pytest.approx(r["region_craft_output"], rel=1e-4, abs=1e-5)
            assert r["allocated"] == 0.0 and r["realized"] == 0.0
            assert r["work_available"] == pytest.approx(len(r["crew"]) * r["diverted_fraction"], rel=1e-5)
    assert checked["crew"] > 0 and checked["receipts"] > 0


def test_observe_mode_leaves_the_trajectory_unchanged(tmp_path):
    off = _run(tmp_path / "off")
    observe = _run(tmp_path / "observe", "--workshops", "--workshop-mode", "observe")
    assert len(off["history"]) == len(observe["history"])
    for a, b in zip(off["history"], observe["history"], strict=True):
        b = dict(b)
        assert b.pop("livelihoods")["workshops"]["stage"] == "L1A"
        assert a == b
    ws = dict(observe["world_state"])
    assert ws.pop("livelihoods")["workshops"]["mode"] == "observe"
    assert ws == off["world_state"]


def test_craft_inputs_are_taken_once_per_tick():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 42)
    assert sim.take_craft_inputs() is None
    with pytest.raises(ValueError, match="initialized"):
        sim.plan_workshop_crews([(0, 0, 1, 0.2, 8)], [])


def test_operate_mode_pays_once_and_bounds_output_by_crew_work(tmp_path):
    from chronicler import workshops as W
    bundle = _run(tmp_path, "--workshops", turns=60)
    off = _run(tmp_path / "off", turns=60)
    operating = paid = 0
    for snap in bundle["history"]:
        record = snap["livelihoods"]["workshops"]
        assert record["mode"] == "operate" and record["stage"] == "L1B"
        for r in record["receipts"] or []:
            assert r["realized"] <= r["allocated"] + 1e-6 and r["allocated"] <= r["work_available"] + 1e-6
            assert r["affected_ordinary_income_share"] == 0.0
            if r["craft_ceiling"]:                      # a funded, built site with crew operated
                operating += 1
                assert r["funded"]
                assert r["craft_ceiling"] == pytest.approx(W.K_RAW_PER_WORK * r["work_available"], rel=1e-5)
                assert r["region_craft_output"] <= r["craft_ceiling"] * (1 + 1e-5) + 1e-6
                assert r["realized"] == pytest.approx(min(r["allocated"], r["region_craft_output"] / W.K_RAW_PER_WORK), rel=1e-5, abs=1e-7)
            elif r["craft_ceiling"] is not None:
                assert r["craft_ceiling"] == 0.0 and r["region_craft_output"] == pytest.approx(0.0, abs=1e-6)
            paid += sum((r["paid"] or {}).values())
    assert operating > 0 and paid > 0
    final = bundle["history"][-1]["livelihoods"]["workshops"]["counters"]
    assert final["paid_construction"] > 0
    # The run is a real intervention: its trajectory differs from the off arm.
    assert any({k: v for k, v in b.items() if k != "livelihoods"} != a
               for a, b in zip(off["history"], bundle["history"]))


def test_cost_only_charges_like_operate_without_replacing_the_ceiling(tmp_path):
    bundle = _run(tmp_path, "--workshops", "--workshop-mode", "cost_only", turns=40)
    paid = 0
    for snap in bundle["history"]:
        for r in snap["livelihoods"]["workshops"]["receipts"] or []:
            assert r["craft_ceiling"] is None and r["allocated"] == 0.0 and r["realized"] == 0.0
            paid += sum((r["paid"] or {}).values())
    assert paid > 0


def test_one_work_commitment_per_person_alongside_health_care_and_teaching(tmp_path, monkeypatch):
    """Real path: crews are planned after this turn's health work and become
    the turn's registry; teaching excludes registry holders; grain storage
    spends from the same treasury; the native tick (which refuses any work
    overlap) and workshop settlement (which refuses an unfunded bill)
    complete every turn."""
    from chronicler import workshops as W
    seen = {"turns": 0, "crew": 0}
    original = W.finish_phase2

    def checked_finish(world, economy_result, agent_bridge, acc):
        sim = agent_bridge._sim
        plan = world.livelihoods.workshops._plan
        crew = {aid for site_plan in plan.sites for aid in site_plan.row["crew"]}
        held = sim.work_reservations(world.turn)
        assert {row[0] for row in held} == crew and len(held) == len(crew)
        assert all(category == 0 and 0.0 < fraction <= 1.0 for _, category, fraction in held)
        assert sim.work_reservation_conflicts(world.turn) == []
        seen["turns"] += 1
        seen["crew"] += len(crew)
        return original(world, economy_result, agent_bridge, acc)

    monkeypatch.setattr(W, "finish_phase2", checked_finish)
    bundle = _run(tmp_path, "--workshops", "--health-care", "--scholarship", "--techniques",
                  "--academy-services", "--grain-reserves", "--grain-storage",
                  "--grain-storage-policy", "maintain", "--grain-storage-work-budget", "4", turns=60)
    assert seen["crew"] > 0 and seen["turns"] > 0
    assert len(bundle["history"]) == 60
