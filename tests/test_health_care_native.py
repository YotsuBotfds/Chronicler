"""Fresh native execution of the health phase boundary and exact inputs."""
from __future__ import annotations
import pytest

pytestmark = pytest.mark.native


def native():
    ca = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(ca, "AgentSimulator", None), type) or not hasattr(ca.AgentSimulator, "prepare_health_work"):
        pytest.skip("requires the fresh health-care native build")
    return ca


def setup(seed=42):
    native()
    from chronicler.agent_bridge import AgentBridge
    from chronicler.world_gen import generate_world
    from chronicler.health_care import set_health_care_enabled
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    set_health_care_enabled(world, True)
    world.health_care.injury_rate = 0.25
    return world, AgentBridge(world, mode="hybrid")


def test_hybrid_phases_injure_actual_workers_then_consume_once():
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    from chronicler.health_care import snapshot_summary
    world, bridge = setup()
    totals = []
    for _ in range(12):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed),
                 lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)
        summary = snapshot_summary(world)
        assert summary["source_turn"] == world.turn - 1
        assert summary["impaired_work"] >= 0 and summary["care_work"] >= 0
        assert len({e.agent_id for e in world.health_care.episodes}) == len(world.health_care.episodes)
        assert bridge._sim.finish_health_work(world.turn, 0.25) == ([], [], [])
        totals.append(summary)
    assert sum(s["new_injuries"] for s in totals) > 0
    assert sum(s["impaired_work"] for s in totals[1:]) > 0
    assert totals[0]["impaired_work"] == 0.0, "onsets cannot remove earlier work"
    assert sum(s["recoveries"] for s in totals) > 0


def test_native_schema_and_checkpoint_omit_prepared_inputs():
    native()
    world, bridge = setup()
    sim = bridge._sim
    schema = sim.checkpoint_schema()[2]
    assert "health_work" not in schema
    before = sim.checkpoint_state()
    sim.prepare_health_work([], [], [], .5, .2)
    assert sim.checkpoint_state() == before
    restored = type(sim).from_checkpoint_state(before)
    assert restored.finish_health_work(0, .25) == ([], [], [])


def test_exact_resume_rebuilds_health_work_from_python_episodes(tmp_path):
    native()
    import argparse
    import json
    from chronicler.main import execute_run
    from chronicler.world_gen import generate_world
    from chronicler.health_care import set_health_care_enabled
    from chronicler import run_checkpoint as rc
    from chronicler.bundle_codec import load_bundle

    def args(folder, checkpoint=False):
        return argparse.Namespace(seed=42, turns=20, regions=8, civs=4,
            output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
            resume=None, reflection_interval=10, llm_actions=False, scenario=None,
            simulate_only=True, agents="hybrid", tuning_overrides={},
            health_care=True if checkpoint else None,
            checkpoint_every=6 if checkpoint else None,
            checkpoint=str(folder / "c{turn}.ckpt") if checkpoint else None)

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    set_health_care_enabled(world, True)
    world.health_care.injury_rate = .25
    straight, resumed = tmp_path / "straight", tmp_path / "resumed"
    execute_run(args(straight, True), world=world)
    saved = rc.read_checkpoint(straight / "c6.ckpt")
    assert saved.state.world.health_care.episodes, "resume an active cohort, not an empty switch"
    assert saved.state.world.health_care._prepared is None
    execute_run(args(resumed), checkpoint_resume=saved)

    def outputs(folder):
        out = {}
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix == ".ckpt":
                continue
            content = path.read_bytes()
            if path.name == "chronicle_bundle.json":
                bundle = load_bundle(path)
                bundle["metadata"].pop("generated_at", None)
                content = json.dumps(bundle, sort_keys=True).encode()
            out[path.relative_to(folder).as_posix()] = content
        return out
    expected, got = outputs(straight), outputs(resumed)
    assert got.keys() == expected.keys()
    assert [name for name in expected if expected[name] != got[name]] == []
