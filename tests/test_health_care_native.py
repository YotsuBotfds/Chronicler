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
