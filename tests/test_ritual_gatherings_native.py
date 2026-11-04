"""Real native attendance/relationship operations and turn-boundary persistence."""
from __future__ import annotations

import pytest

from chronicler import ritual_gatherings as R
from chronicler.contact_ledger import ContactLedgerState, update_contact_ledger
from chronicler.economy import EconomyResult
from chronicler.ffi_constants import BOND_FRIEND, BOND_MARRIAGE
from chronicler.models import AgentEventRecord
from chronicler.world_gen import generate_world

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(ca, "AgentSimulator", None), type):
        pytest.skip("requires the compiled chronicler_agents AgentSimulator")
    return ca


def _world_bridge():
    _native()
    from chronicler.agent_bridge import AgentBridge
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    R.set_ritual_gatherings_enabled(world, True)
    world.contact_ledger = ContactLedgerState()
    for region in world.regions:
        region.stockpile.goods["grain"] = 10000.0
    for civ in world.civilizations:
        civ.treasury = 100
    bridge = AgentBridge(world, mode="hybrid")
    return world, bridge


def _economy(world):
    result = EconomyResult()
    for region in world.regions:
        result.food_sufficiency[region.name] = 1.0
        result.market_demand[region.name] = (max(1, region.population) * 0.5, 0, 0, 0)
    return result


def _gather(world, bridge):
    return R.tick_ritual_gatherings(world, agent_bridge=bridge, economy_result=_economy(world))


def test_real_native_friendship_creation_refresh_and_protected_slots():
    world, bridge = _world_bridge()
    world.turn = 8
    buckets = R._presence(world, bridge)
    rid, attendees = next((rid, rows) for rid, rows in buckets.items()
                          if len(rows) >= 12 and world.regions[rid].controller is not None)
    a, b = attendees[0][0], attendees[1][0]
    # A protected different-type edge between the selected pair survives, and
    # an existing strong friend retains its original date and sentiment.
    bridge.apply_relationship_ops([
        {"op_type": 1, "agent_a": a, "agent_b": b, "bond_type": BOND_MARRIAGE,
         "sentiment": 70, "formed_turn": 2},
        {"op_type": 1, "agent_a": a, "agent_b": b, "bond_type": BOND_FRIEND,
         "sentiment": 60, "formed_turn": 3},
    ])
    # Fill another pair's first endpoint with protected directed marriage
    # records; this fixture tests the native substrate's capacity boundary.
    full = attendees[2][0]
    targets = [row[0] for row in attendees[4:12]]
    bridge.apply_relationship_ops([
        {"op_type": 0, "agent_a": full, "agent_b": target, "bond_type": BOND_MARRIAGE,
         "sentiment": 70, "formed_turn": 2} for target in targets
    ])
    protected_before = bridge._sim.get_agent_relationships(full)
    _gather(world, bridge)
    outcome = next(o for o in world.ritual_gatherings.outcomes if o.region == rid)
    assert outcome.status == "held" and 0 < outcome.bond_ops <= 8
    assert bridge._sim.get_agent_relationships(full) == protected_before
    actual = bridge._sim.get_agent_relationships(a)
    assert (b, 70, BOND_MARRIAGE, 2) in actual
    assert (b, 60, BOND_FRIEND, 3) in actual
    fresh_a, fresh_b = attendees[4][0], attendees[5][0]
    assert (fresh_b, R.FRIEND_SENTIMENT, BOND_FRIEND, 8) in bridge._sim.get_agent_relationships(fresh_a)
    # Refresh at a second occurrence never resets the native formation date.
    world.turn = 20
    _gather(world, bridge)
    assert (fresh_b, R.FRIEND_SENTIMENT, BOND_FRIEND, 8) in bridge._sim.get_agent_relationships(fresh_a)


def test_real_native_exact_checkpoint_does_not_replay_contact_or_costs(tmp_path):
    import chronicler.run_checkpoint as rc
    world, bridge = _world_bridge()
    world.turn = 8
    rid, attendees = next((rid, rows) for rid, rows in R._presence(world, bridge).items()
                          if rows and world.regions[rid].controller is not None)
    source = next(i for i in range(len(world.regions)) if i != rid)
    world.agent_events_raw.append(AgentEventRecord(turn=8, agent_id=attendees[0][0],
        event_type="migration", region=source, target_region=rid, civ_affinity=0, occupation=0))
    _gather(world, bridge)
    assert next(o for o in world.ritual_gatherings.outcomes if o.region == rid).contact_units == 1
    update_contact_ledger(world)
    assert world._contact_pending is None
    world.turn = 9
    state = rc.RunState(world=world, agent_bridge=bridge, memories={}, history=[], chronicle_entries=[],
                        era_reflections={}, pending_injections=[], start_turn=0, seed=world.seed,
                        num_turns=22, run_config={"agent_mode": "hybrid"})
    path = tmp_path / "gathering-turn9.ckpt"
    rc.write_checkpoint(path, state)
    loaded = rc.read_checkpoint(path)
    assert loaded.exact
    restored_world, restored_bridge = loaded.state.world, loaded.state.agent_bridge
    for turn in range(9, 22):
        world.turn = restored_world.turn = turn
        assert _gather(world, bridge) == _gather(restored_world, restored_bridge)
        update_contact_ledger(world)
        update_contact_ledger(restored_world)
        assert restored_world.model_dump() == world.model_dump()
        assert restored_world._contact_pending is world._contact_pending is None
        from chronicler.columnar import pylist
        left = restored_bridge._sim.get_all_relationships()
        right = bridge._sim.get_all_relationships()
        assert {k: pylist(left.column(k)) for k in left.schema.names} == {
            k: pylist(right.column(k)) for k in right.schema.names}
        if turn != 20:
            assert world.ritual_gatherings.outcomes == []
            assert world.contact_ledger.last_inflow[3] == 0


def test_production_turn_hook_uses_existing_native_pipeline_and_clears_pending(monkeypatch):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    world, bridge = _world_bridge()
    # A controlled native economy observation isolates hook wiring; the real
    # coordinator, native agent tick and relationship store still execute.
    called = []
    original = R.tick_ritual_gatherings

    def record(*args, **kwargs):
        called.append((args[0].turn, kwargs["phase10"].source_turn, kwargs["economy_result"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(R, "tick_ritual_gatherings", record)
    for _ in range(10):
        engine = ActionEngine(world)
        run_turn(world, lambda civ, w: engine.select_action(civ, seed=w.seed), lambda w, ev: "",
                 seed=world.seed + world.turn, agent_bridge=bridge)
        assert world._contact_pending is None
    assert [turn for turn, stamp, _e in called] == list(range(10))
    assert all(turn == stamp and economy is not None for turn, stamp, economy in called)
    assert world.ritual_gatherings.last_tick_turn == 9
    assert all(s.last_turn == 8 and s.next_turn == 20 for s in world.ritual_gatherings.schedules)
    assert world.ritual_gatherings.outcomes == []
