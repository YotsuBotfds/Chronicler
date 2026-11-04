"""Fresh compiled bridge contracts. Authored for remote native CI only."""
import io

import pytest

from chronicler.agent_bridge import AgentBridge
from chronicler.decision_delivery import DecisionDeliveryObserver
from tests.test_decision_delivery_native import _native

pytestmark = pytest.mark.native


def world_fixture(make_world, mode):
    world = make_world(num_civs=2)
    world.seed, world.agent_mode = 42, mode
    owner = world.civilizations[0]
    for index, region in enumerate(world.regions):
        region.controller = owner.name
        region.adjacencies = [world.regions[1-index].name]
        region.population = 32 if index == 0 else 8
        region.carrying_capacity = 20 if index == 0 else 100
        region.ecology.soil = region.ecology.water = 0.2 if index == 0 else 1.0
    owner.regions = [region.name for region in world.regions]
    owner.population = 40
    world.civilizations[1].regions = []
    world.civilizations[1].population = 0
    return world


@pytest.mark.parametrize("method", ["tick", "tick_agents"])
@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_actual_bridge_observer_preserves_native_future_state_and_normal_writeback(make_world, method, mode):
    native = _native()
    assert callable(getattr(native.AgentSimulator, "get_decision_delivery_move_frame", None))
    left_world, right_world = world_fixture(make_world, mode), world_fixture(make_world, mode)
    left, right = AgentBridge(left_world, mode=mode), AgentBridge(right_world, mode=mode)
    observer = DecisionDeliveryObserver.attach(right)
    assert "_decision_delivery_observer" not in left.__dict__
    applied = 0
    for turn in range(4):
        left_world.turn = right_world.turn = turn
        if method == "tick_agents":
            left.sync_regions(left_world); right.sync_regions(right_world)
        a = getattr(left, method)(left_world)
        b = getattr(right, method)(right_world)
        assert a == b
        assert left_world.model_dump() == right_world.model_dump()
        assert bytes(left._sim.checkpoint_state()) == bytes(right._sim.checkpoint_state())
        assert left.get_snapshot().equals(right.get_snapshot())
        result = observer.read_latest(expected_source_turn=turn)
        assert result.status == "captured", result.reason
        assert result.source_turn == turn and result.bridge_mode == mode
        assert result.native_event_count >= result.applied_event_links_checked
        applied += result.applied_event_links_checked
        assert observer.read_latest(expected_source_turn=turn) is result
    if mode == "hybrid":
        assert applied > 0, "the controlled crowded bridge fixture must exercise actual native move joins"
    observer.close(); left.close(); right.close()


def test_actual_bridge_pickle_payload_omits_configuration_and_captured_arrow(make_world):
    native = _native()
    assert callable(getattr(native.AgentSimulator, "get_decision_delivery_move_frame", None))
    from chronicler.run_checkpoint import _Pickler

    world = world_fixture(make_world, "hybrid")
    bridge = AgentBridge(world, mode="hybrid")
    observer = DecisionDeliveryObserver.attach(bridge)
    bridge.tick(world)
    assert observer.read_latest(expected_source_turn=0).status == "captured"
    def payload():
        stream = io.BytesIO()
        pickler = _Pickler(stream)
        pickler.dump(bridge)
        return stream.getvalue(), pickler.natives
    enabled = payload()
    assert "_decision_delivery_observer" not in bridge.__getstate__()
    assert observer.close().reason == "closed"
    assert payload() == enabled
    blob = next(iter(enabled[1].values()))
    restored = native.AgentSimulator.from_checkpoint_state(blob)
    import pyarrow as pa
    header = pa.record_batch(restored.get_decision_delivery_move_frame()[0]).to_pylist()[0]
    assert not header["enabled"] and header["source_turn"] is None
    assert restored.checkpoint_schema()[1] == "dcf0c34097c88451"
    bridge.close()
