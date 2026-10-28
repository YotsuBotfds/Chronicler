"""Per-turn real simulation/native identity for public purchase observation."""
from __future__ import annotations
import random
import pytest

pytestmark = pytest.mark.native


def _setup():
    from test_transaction_receipts_native import _native
    _native()
    from chronicler.agent_bridge import AgentBridge
    from chronicler.grain_reserves import set_grain_reserves_enabled, _ensure
    from chronicler.models import WorldState
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world
    plain = generate_world(seed=42, num_regions=8, num_civs=4)
    plain.agent_mode = "hybrid"
    set_grain_reserves_enabled(plain, True)
    state = _ensure(plain)
    for region, granary in zip(plain.regions, state.granaries):
        if region.controller is not None:
            granary.owner = plain.civ_index_map[region.controller]
            granary.observed, granary.harvest_mean, granary.harvest_sq = 12, 0.5, 0.5
            region.stockpile.goods = {"grain": 500.0}
    for civ in plain.civilizations:
        civ.treasury = 500
    recorded = WorldState.model_validate_json(plain.model_dump_json())
    set_transaction_receipts_enabled(recorded, True)
    return (plain, AgentBridge(plain, mode="hybrid")), (recorded, AgentBridge(recorded, mode="hybrid"))


def _advance(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    engine = ActionEngine(world)
    return run_turn(world, lambda c, w: engine.select_action(c, seed=w.seed),
                    lambda w, events: "", seed=world.seed+world.turn, agent_bridge=bridge)


def test_true_per_turn_economic_rng_events_and_native_payload_identity():
    (plain, a), (recorded, b) = _setup()
    purchases = 0
    for _ in range(5):
        rng = random.getstate()
        _advance(plain, a)
        after = random.getstate()
        random.setstate(rng)
        _advance(recorded, b)
        assert random.getstate() == after
        assert plain.model_dump(mode="json", exclude={"transaction_receipts"}) == recorded.model_dump(
            mode="json", exclude={"transaction_receipts"})
        assert a._sim.checkpoint_state() == b._sim.checkpoint_state()
        assert a._sim.get_snapshot().equals(b._sim.get_snapshot())
        frame = recorded.transaction_receipts.public_purchases
        assert frame.source_turn == recorded.turn-1 and frame.complete
        assert recorded.transaction_receipts.source_turn == frame.source_turn
        purchases += frame.observed_purchases
    assert purchases > 0, "the controlled native run must make actual public purchases"


def test_both_domains_resume_exactly_through_real_run_checkpoint(tmp_path):
    from chronicler.run_checkpoint import RunState, write_checkpoint, read_checkpoint
    (_, _), (world, bridge) = _setup()
    _advance(world, bridge)
    before = world.transaction_receipts.public_purchases.model_dump_json()
    path = tmp_path / "public-purchases.ckpt"
    write_checkpoint(path, RunState(world=world, memories={}, history=[], chronicle_entries=[],
        era_reflections={}, pending_injections=[], start_turn=0, seed=42, num_turns=4,
        agent_bridge=bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    resumed, rb = loaded.state.world, loaded.state.agent_bridge
    assert resumed.transaction_receipts.public_purchases.model_dump_json() == before
    assert rb._sim.get_transaction_receipt_frame()[0] is None
    for _ in range(2):
        rng = random.getstate()
        _advance(world, bridge)
        after = random.getstate()
        random.setstate(rng)
        _advance(resumed, rb)
        assert random.getstate() == after
        assert world.model_dump_json() == resumed.model_dump_json()
        assert bridge._sim.checkpoint_state() == rb._sim.checkpoint_state()
