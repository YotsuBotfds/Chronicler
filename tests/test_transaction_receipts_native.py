"""Fresh-wheel FFI controls; run against the receipt binary, not an older wheel."""
from __future__ import annotations
import pytest

pytestmark = pytest.mark.native


def _native():
    native = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(native, "AgentSimulator", None), type) or not hasattr(
            native.AgentSimulator, "configure_transaction_receipts"):
        pytest.skip("requires fresh transaction-receipt native build")
    return native


def _setup(mode="hybrid", enabled=True):
    _native()
    from chronicler.agent_bridge import AgentBridge
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=12, num_civs=4)
    world.agent_mode = mode
    # Controlled merchant market: stocked origins, a dear food destination and
    # connected intra-civ routes. This is an FFI observation fixture, not a run.
    owner = world.civilizations[0].name
    world.civilizations[0].regions = [r.name for r in world.regions]
    for civ in world.civilizations[1:]:
        civ.regions = []
    for region in world.regions:
        region.controller = owner
        region.stockpile.goods = {"grain": 50.0}
    if enabled:
        set_transaction_receipts_enabled(world, True)
    bridge = AgentBridge(world, mode=mode)
    from chronicler.economy import EconomyResult
    bridge._economy_result = EconomyResult(food_sufficiency={
        r.name: 0.25 if i == len(world.regions)-1 else 2.0 for i, r in enumerate(world.regions)},
        market_demand={r.name: (100.0, 0.0, 0.0, 0.0) for r in world.regions},
        market_supply={r.name: (25.0 if i == len(world.regions)-1 else 200.0, 0.0, 0.0, 0.0)
                       for i, r in enumerate(world.regions)})
    return world, bridge


def _tick(world, bridge, *, graph=True):
    from chronicler.agent_bridge import build_signals
    from chronicler.economy import build_merchant_route_graph
    from chronicler.transaction_receipts import prepare_transaction_receipts, capture_transaction_receipts
    bridge.sync_regions(world)
    if graph:
        # Replaces the graph every tick, like the real bridge.
        bridge._sim.set_merchant_route_graph(build_merchant_route_graph(world))
    prepare_transaction_receipts(world, bridge)
    events = bridge._sim.tick(world.turn, build_signals(world))
    capture_transaction_receipts(world, bridge)
    world.turn += 1
    return events


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
def test_enabled_receipts_preserve_native_events_pool_and_payload_every_tick(mode):
    a, ba = _setup(mode, enabled=False)
    b, bb = _setup(mode, enabled=True)
    seen = 0
    for _ in range(6):
        assert _tick(a, ba).equals(_tick(b, bb))
        assert ba._sim.checkpoint_state() == bb._sim.checkpoint_state()
        assert ba._sim.get_snapshot().equals(bb._sim.get_snapshot())
        source, limit, dropped, executed, rows = bb._sim.get_transaction_receipt_frame()
        again = bb._sim.get_transaction_receipt_frame()
        assert (source, limit, dropped, executed) == again[:4]
        assert rows.equals(again[4])
        assert source == b.turn - 1 and executed and dropped == 0
        from chronicler.columnar import pylist
        assert all(value == (mode == "hybrid") for value in pylist(rows.column("physical_stock")))
        seen += rows.num_rows
    assert seen > 0, "the native fixture must exercise actual merchant observations"
    assert "transaction_receipts_limit" not in ba._sim.checkpoint_schema()[2]
    assert "receipt_limit" not in ba._sim.checkpoint_schema()[2]
    assert "receipts:" not in ba._sim.checkpoint_schema()[2]


def test_enabled_native_resume_restores_python_identity_and_rebuilds_config_exactly(tmp_path):
    from chronicler.run_checkpoint import RunState, write_checkpoint, read_checkpoint
    world, bridge = _setup()
    _tick(world, bridge)
    path = tmp_path / "receipts.ckpt"
    write_checkpoint(path, RunState(world=world, memories={}, history=[], chronicle_entries=[],
        era_reflections={}, pending_injections=[], start_turn=0, seed=42, num_turns=5,
        agent_bridge=bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    restored, resumed = loaded.state.world, loaded.state.agent_bridge
    assert resumed._sim.get_transaction_receipt_frame()[0] is None
    for _ in range(4):
        assert _tick(world, bridge).equals(_tick(restored, resumed))
        assert world.model_dump_json() == restored.model_dump_json()
        assert bridge._sim.checkpoint_state() == resumed._sim.checkpoint_state()
    assert world.transaction_receipts.counters["observed_starts"] > 0


def test_missing_mobility_substrate_is_not_a_complete_empty_capture():
    world, bridge = _setup()
    _tick(world, bridge, graph=False)
    assert world.transaction_receipts.source_turn == world.turn - 1
    assert not world.transaction_receipts.mobility_executed
    assert not world.transaction_receipts.complete
    assert world.transaction_receipts.frame == []
    bridge._sim.configure_transaction_receipts(False)
    source, limit, dropped, executed, rows = bridge._sim.get_transaction_receipt_frame()
    assert (source, limit, dropped, executed, rows.num_rows) == (None, 0, 0, False, 0)
