"""Real-native read-only observations; separate from the bounded offline lane."""
import pickle
import random

import pytest

from chronicler import regional_population as R
from chronicler.turn_artifacts import TurnObservation


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_actual_native_observation_changes_no_persisted_state_rng_or_snapshot_cache(make_agent_bridge_world, mode):
    world, bridge = make_agent_bridge_world(mode=mode)
    # Capture the already-obtained Phase 2 Arrow rows; the observer does not ask
    # for another snapshot, consume an event stream or mutate any cache.
    rows = bridge.get_snapshot()
    weights = R.capture_food_weights(world, rows)
    observation = TurnObservation(world.turn, world.turn + 1, None, weights,
                                  R.capture_population_sources(world))
    world.turn += 1
    before = bytes(bridge._sim.checkpoint_state())
    cached = bridge._sim.snapshot_is_cached()
    before_world, rng = world.model_dump_json(), random.getstate()
    bridge_members = dict(bridge.__dict__)
    first = R.snapshot_fields(world, bridge, observation)
    second = R.snapshot_fields(world, bridge, observation)
    value = first["regional_population"]
    actual = bridge._sim.get_region_populations()
    assert value["agent_counts"] == actual.column("alive_count").to_pylist()
    assert value["food_weights"]["counts"] == value["agent_counts"]
    assert sum(value["agent_counts"]) == rows.num_rows
    assert value["counts"] == [r.population for r in world.regions]
    assert first == second == pickle.loads(pickle.dumps(first))
    assert bytes(bridge._sim.checkpoint_state()) == before
    assert bridge._sim.snapshot_is_cached() == cached
    assert world.model_dump_json() == before_world and random.getstate() == rng
    assert set(bridge.__dict__) == set(bridge_members)
    assert all(value is bridge.__dict__[name] for name, value in bridge_members.items())
    bridge.close()
