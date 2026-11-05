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
        for row in plan.rows:
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
