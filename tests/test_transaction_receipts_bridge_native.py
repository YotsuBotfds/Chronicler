"""Actual bridge boundaries with the fresh receipt binary (one worker)."""
from __future__ import annotations
import pytest

import chronicler.transaction_receipts as T
from test_transaction_receipts_native import _setup

pytestmark = pytest.mark.native


def _bridge_tick(world, bridge, method="tick"):
    if method == "tick_agents":
        bridge.sync_regions(world)
    events = getattr(bridge, method)(world)
    world.turn += 1
    return events


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only"])
@pytest.mark.parametrize("method", ["tick", "tick_agents"])
def test_real_bridge_captures_before_postprocessing_and_clears_on_disable(mode, method, monkeypatch):
    world, bridge = _setup(mode)
    original = bridge._process_tick_results
    observed = []
    def process(events, current, **kwargs):
        assert current.transaction_receipts.source_turn == current.turn
        observed.append(current.turn)
        return original(events, current, **kwargs)
    monkeypatch.setattr(bridge, "_process_tick_results", process)
    _bridge_tick(world, bridge, method)
    assert observed == [0]
    assert T.snapshot_summary(world)["source_turn"] == 0
    assert world.transaction_receipts.frame, "controlled market must emit observations"
    # Undo only the observer wrapper; all later calls still use real bridge hooks.
    monkeypatch.setattr(bridge, "_process_tick_results", original)
    T.set_transaction_receipts_enabled(world, False)
    _bridge_tick(world, bridge, method)
    assert bridge._sim.get_transaction_receipt_frame()[0] is None
    assert T.snapshot_summary(world) == {}
    assert "transaction_receipts" not in world.model_dump_json()


def test_raw_world_restart_rejected_before_loading_any_new_native_pool(monkeypatch):
    from chronicler.agent_bridge import AgentBridge
    from chronicler.models import WorldState
    world, bridge = _setup()
    _bridge_tick(world, bridge)
    raw = WorldState.model_validate_json(world.model_dump_json())
    def forbidden():
        raise AssertionError("raw receipt identities must be rejected before native loading")
    monkeypatch.setattr("chronicler.agent_bridge._load_agent_simulator_class", forbidden)
    with pytest.raises(ValueError, match="exact native checkpoint"):
        AgentBridge(raw, mode="hybrid")


def test_exact_checkpoint_keeps_frame_then_rebuilds_recorder_and_continues_real_bridge(tmp_path):
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    world, bridge = _setup()
    _bridge_tick(world, bridge)
    before = world.transaction_receipts.model_dump_json()
    path = tmp_path / "actual-bridge.ckpt"
    write_checkpoint(path, RunState(world=world, memories={}, history=[], chronicle_entries=[],
        era_reflections={}, pending_injections=[], start_turn=0, seed=42, num_turns=4,
        agent_bridge=bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    resumed, rb = loaded.state.world, loaded.state.agent_bridge
    assert resumed.transaction_receipts.model_dump_json() == before
    assert rb._sim.get_transaction_receipt_frame()[0] is None
    assert T.snapshot_summary(resumed) == T.snapshot_summary(world)
    for method in ("tick_agents", "tick", "tick_agents"):
        assert _bridge_tick(world, bridge, method) == _bridge_tick(resumed, rb, method)
        assert world.model_dump_json() == resumed.model_dump_json()
        assert bridge._sim.checkpoint_state() == rb._sim.checkpoint_state()
        assert resumed.transaction_receipts.source_turn == resumed.turn - 1
    assert resumed.transaction_receipts.counters["observed_starts"] > 0


def test_dormant_saved_flag_clears_native_without_mutating_journal_and_gap_loses_continuity():
    world, bridge = _setup()
    _bridge_tick(world, bridge)
    before = world.transaction_receipts.model_dump_json()
    world.agent_mode = "off"
    _bridge_tick(world, bridge)
    assert world.transaction_receipts.model_dump_json() == before
    assert bridge._sim.get_transaction_receipt_frame()[0] is None
    assert T.snapshot_summary(world) == {}
    world.agent_mode = "hybrid"
    _bridge_tick(world, bridge)
    assert world.transaction_receipts.source_turn == world.turn - 1
    # A recorder gap cannot silently retain a voyage known before dormancy.
    for row in world.transaction_receipts.frame:
        if row.operation in ("departed", "arrived", "sea_crossing"):
            assert row.voyage_id is None
