"""Real M4 native, one declared seed/initial world; not a distributional gate."""
import random

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")

from chronicler.action_engine import ActionEngine
from chronicler.agent_bridge import AgentBridge
from chronicler.household_mobility_state import snapshot_fields
from chronicler.models import TurnSnapshot
from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
from chronicler.simulation import run_turn_result
from chronicler.world_gen import generate_world

pytestmark = pytest.mark.native


def _setup():
    # Fixed, declared scenario: the ordinary seed-42 five-region world begins
    # with grain in region 0 and empty markets elsewhere. Wealth is native,
    # accrued by the simulation; no agent wealth or decisions are fabricated.
    world = generate_world(seed=42, num_regions=5, num_civs=2)
    world.agent_mode = "hybrid"
    for i, region in enumerate(world.regions):
        region.stockpile.goods = {"grain": 100.0 if i == 0 else 0.0}
    world.household_mobility_liquid_requirement = 1.0
    return world, AgentBridge(world, mode="hybrid")


def _advance(world, bridge):
    source = world.turn
    start = len(world.agent_events_raw)
    engine = ActionEngine(world)
    result = run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
             seed=world.seed + source, agent_bridge=bridge)
    observation = result.observation.household_mobility
    events = world.agent_events_raw[start:]
    return observation, events


def _checkpoint(path, world, bridge, history):
    write_checkpoint(path, RunState(world=world, agent_bridge=bridge, history=history,
        memories={}, chronicle_entries=[], era_reflections={}, pending_injections=[],
        start_turn=0, seed=world.seed, num_turns=8))


def _native_agents(bridge):
    rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
    return {row["id"]: row for row in rows}


def _history_snapshot(observation, completed_turn):
    return TurnSnapshot(turn=completed_turn, civ_stats={}, region_control={}, relationships={},
                        **snapshot_fields(observation, completed_turn))


def test_native_paired_gate_distinguishes_real_wealth_and_actual_moves(tmp_path):
    world, bridge = _setup()
    first, _ = _advance(world, bridge)
    assert first.source_turn == 0
    path = tmp_path / "common.ckpt"
    _checkpoint(path, world, bridge, [_history_snapshot(first, 1)])
    enabled = read_checkpoint(path).state
    disabled = read_checkpoint(path).state
    disabled.world.household_mobility_liquid_requirement = 0.0
    # Both arms start with identical native bytes and enter the same seeded turn.
    assert enabled.agent_bridge._sim.checkpoint_state() == disabled.agent_bridge._sim.checkpoint_state()
    rng = random.getstate()
    gated, gated_events = _advance(enabled.world, enabled.agent_bridge)
    rng_after = random.getstate()
    random.setstate(rng)
    no_gate, plain_events = _advance(disabled.world, disabled.agent_bridge)
    assert random.getstate() == rng_after
    assert no_gate is None
    assert gated.source_turn == 1
    blocked = [s for s in gated.samples if s.reason == "insufficient" and s.native_persons == 1]
    passed = [s for s in gated.samples if s.reason == "sufficient" and s.native_persons == 1]
    assert blocked and passed
    assert all(s.native_adult_liquid_wealth < s.required_liquid == 1.0 for s in blocked)
    assert all(s.native_adult_liquid_wealth >= s.required_liquid == 1.0 for s in passed)
    assert all(s.local_food_sufficiency < 1.0 for s in blocked)
    plain_moves = {e.agent_id: e for e in plain_events if e.event_type == "migration"}
    gated_moves = {e.agent_id: e for e in gated_events if e.event_type == "migration"}
    gated_agents = _native_agents(enabled.agent_bridge)
    plain_agents = _native_agents(disabled.agent_bridge)
    # For a singleton blocked proposal, no fabricated follower mapping is needed.
    blocked_that_stayed = [s for s in blocked if s.group_id in plain_moves
                           and s.group_id not in gated_moves
                           and s.group_id in gated_agents and s.group_id in plain_agents
                           and gated_agents[s.group_id]["region"] == s.origin_region_id]
    assert blocked_that_stayed, "the paired arm must show an observed blocked mover remaining"
    # A singleton's observed gate balance is its own; the two paired final
    # balances substantiate that the gate itself did not debit this agent.
    assert any(gated_agents[s.group_id]["wealth"] == plain_agents[s.group_id]["wealth"]
               == pytest.approx(s.native_adult_liquid_wealth) for s in blocked_that_stayed)
    assert any(s.group_id in gated_moves for s in passed), "observe an eligible singleton actually moving"
    suff = enabled.world._economy_result.food_sufficiency
    assert any(suff[enabled.world.regions[s.destination_region_id].name] > s.local_food_sufficiency
               for s in blocked_that_stayed), "at least one chosen neighbor has better recorded food"
    # Counts are proposals that passed the gate; actual events are separate.
    assert gated.passed_native_persons >= len([s for s in passed if s.group_id in gated_moves])
    assert gated.blocked_native_persons > 0
    for owner in (bridge, enabled.agent_bridge, disabled.agent_bridge):
        owner.close()


def test_native_exact_checkpoint_resume_retains_recorded_history_and_future(tmp_path):
    world, bridge = _setup()
    first, _ = _advance(world, bridge)
    before = [_history_snapshot(first, 1)]
    path = tmp_path / "distress.ckpt"
    _checkpoint(path, world, bridge, before)
    loaded = read_checkpoint(path)
    assert loaded.exact
    restored, resumed = loaded.state.world, loaded.state.agent_bridge
    assert getattr(restored, "household_mobility_liquid_requirement") == 1.0
    assert loaded.state.history == before
    rng = random.getstate()
    straight, events_a = _advance(world, bridge)
    after = random.getstate()
    random.setstate(rng)
    continued, events_b = _advance(restored, resumed)
    assert random.getstate() == after
    assert snapshot_fields(straight, 2) == snapshot_fields(continued, 2)
    assert events_a == events_b
    assert world.model_dump_json() == restored.model_dump_json()
    assert bridge._sim.checkpoint_state() == resumed._sim.checkpoint_state()
    assert loaded.state.history + [_history_snapshot(continued, 2)] == before + [_history_snapshot(straight, 2)]
    bridge.close()
    resumed.close()
