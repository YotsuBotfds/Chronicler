"""CONSTRUCTED native cases for L4 grain convoys (real hybrid turns).

Natural template runs (seeds 1-3, 150 turns) never hold a sellable foreign
surplus two steps from a granary in deficit, so no convoy is dispatched
there (docs/integration/grain-convoys.md, "Activation"). These cases give
one foreign market a constructed opening stock and only the buyer's granary
an observed harvest swing; everything after that is the real simulation:
native economy, merchants, granary pass, payments and the convoy pass.
"""
from __future__ import annotations

import random

import pytest

pytestmark = pytest.mark.native

SOURCE, OWN, DEST, BUYER, SELLER = 7, 4, 2, 2, 0


def _setup(policy: str):
    pytest.importorskip("chronicler_agents")
    from chronicler import grain_convoys as C
    from chronicler import grain_reserves as G
    from chronicler import public_grain_shipments as S
    from chronicler.agent_bridge import AgentBridge
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.models import Disposition
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    for relations in world.relationships.values():
        for relation in relations.values():
            relation.disposition = Disposition.NEUTRAL
    G.set_grain_reserves_enabled(world, True)
    state = G._ensure(world)
    for region, granary in zip(world.regions, state.granaries):
        if region.controller is not None:
            granary.owner = world.civ_index_map[region.controller]
            if region.controller == world.civilizations[BUYER].name:
                granary.observed, granary.harvest_mean, granary.harvest_sq = 12, 0.5, 0.5
    world.regions[SOURCE].stockpile.goods["grain"] = 1500.0  # constructed opening stock
    for civ in world.civilizations:
        civ.treasury = 500
    S.set_public_grain_shipments_enabled(world, True)
    world.livelihoods = LivelihoodsState()
    args = type("Args", (), {"convoy_route_policy": policy})()
    C.set_grain_convoys_enabled(world, True, args=args, agent_mode="hybrid")
    return world, AgentBridge(world, mode="hybrid")


def _advance(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn
    engine = ActionEngine(world)
    return run_turn(world, lambda c, w: engine.select_action(c, seed=w.seed),
                    lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)


def _convoys(world):
    return world.livelihoods.grain_convoys


def test_constructed_native_convoy_pays_once_travels_and_delivers(monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    from chronicler.grain_reserves_state import CONVOY_ARRIVED
    world, bridge = _setup("adaptive")
    dispatched = arrived = None
    for _ in range(6):
        _advance(world, bridge)
        frame = _convoys(world).frame
        dispatched = dispatched or next((row for row in frame if row.operation == "dispatched"), None)
        if dispatched is not None and any(row.operation == "arrived" and row.convoy == dispatched.convoy
                                          for row in frame):
            arrived = next(row for row in frame if row.operation == "arrived")
            break
    assert dispatched is not None, "the constructed stock must lead to a real convoy dispatch"
    assert dispatched.route == [SOURCE, OWN, DEST] and dispatched.paid > 0
    assert arrived is not None and arrived.turn == dispatched.turn + 2 and arrived.keeper == BUYER
    flows = [f for f in world.grain_reserves.flows if f.kind == CONVOY_ARRIVED]
    assert len(flows) == 1 and flows[0].amount == pytest.approx(dispatched.cargo) and flows[0].cost == 0
    k = _convoys(world).counters
    assert k["paid"] == dispatched.paid and k["delivered"] == pytest.approx(dispatched.cargo)
    assert k["committed_net"] == pytest.approx(k["delivered"] + sum(c.cargo for c in _convoys(world).convoys))


def test_constructed_native_mid_leg_checkpoint_resumes_exactly(tmp_path):
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    world, bridge = _setup("safest")
    for _ in range(6):
        _advance(world, bridge)
        if any(c.progress > 0 for c in _convoys(world).convoys):
            break
    convoy = next(c for c in _convoys(world).convoys if c.progress > 0)
    assert convoy.escorted and convoy.progress < convoy.leg_turns  # the escort is mustering
    path = tmp_path / "convoy.ckpt"
    write_checkpoint(path, RunState(world=world, memories={}, history=[], chronicle_entries=[],
                                    era_reflections={}, pending_injections=[], start_turn=0, seed=42,
                                    num_turns=12, agent_bridge=bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    resumed, resumed_bridge = loaded.state.world, loaded.state.agent_bridge
    assert resumed.model_dump_json() == world.model_dump_json()
    for _ in range(3):
        rng = random.getstate()
        _advance(world, bridge)
        after = random.getstate()
        random.setstate(rng)
        _advance(resumed, resumed_bridge)
        assert random.getstate() == after
        assert resumed.model_dump_json() == world.model_dump_json()
        assert resumed_bridge._sim.checkpoint_state() == bridge._sim.checkpoint_state()
    assert _convoys(world).counters["arrived"] >= 1
    assert _convoys(world).counters["escort_paid"] >= convoy.escort_fee
