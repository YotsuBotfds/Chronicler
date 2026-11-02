"""Bounded, real hybrid merchant interruption and same-source continuation.

This uses the production turn coordinator and physical delivery buffer. Receipt
rows are observations of native actions, not an independent source of stock.
"""
from __future__ import annotations

import random

import pytest

pytestmark = pytest.mark.native


def _setup(num_civs=1, receipts=True):
    native = pytest.importorskip("chronicler_agents")
    assert isinstance(getattr(native, "AgentSimulator", None), type), "compiled native simulator required"
    from chronicler.agent_bridge import AgentBridge
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=3, num_civs=num_civs)
    world.agent_mode = "hybrid"
    civ = world.civilizations[0]
    for other in world.civilizations[1:]:
        other.regions = []
    civ.regions = [r.name for r in world.regions]
    civ.capital_region = world.regions[0].name
    for i, region in enumerate(world.regions):
        region.controller = civ.name
        region.population = (400, 20, 400)[i]
        region.carrying_capacity = 400
        region.stockpile.goods = {"grain": (2000.0, 300.0, 0.0)[i]}
        region.adjacencies = [world.regions[j].name for j in ((1,), (0, 2), (1,))[i]]
        region.route_suspensions.clear()
        region.resource_types = ([0, 255, 255] if i != 2 else [255, 255, 255])
        region.resource_base_yields = ([1.0, 0.0, 0.0] if i != 2 else [0.0, 0.0, 0.0])
    civ.population = sum(r.population for r in world.regions)
    if receipts:
        set_transaction_receipts_enabled(world, True)
    return world, AgentBridge(world, mode="hybrid")


def _advance(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(world)
    previous = list(world.transaction_receipts.frame)
    from chronicler.columnar import pylist
    pending = bridge._sim.get_pending_arrivals()
    cols = {name: pylist(pending.column(name)) for name in
            ("dest_region", "good_slot", "qty")}
    from chronicler.economy import TRANSIT_DECAY
    food_goods = {0: "grain", 1: "fish", 2: "salt", 5: "botanicals", 7: "exotic"}
    pending_food = sum(q * (1 - TRANSIT_DECAY[food_goods[good]])
                       for dest, good, q in zip(cols["dest_region"], cols["good_slot"], cols["qty"])
                       if dest == 2 and good in food_goods)
    result = run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed),
                             lambda w, events: "", seed=world.seed + world.turn,
                             agent_bridge=bridge)
    economy = world._economy_result
    assert economy is not None
    # The prior mobility frame queues gross cargo for this turn's economy.
    # No sea lanes occur in this fixture. This equality checks the actual
    # physical in-flight balance, including all merchants and goods.
    expected = sum(r.quantity * {"departed": 1, "returned": -1, "arrived": -1}.get(r.operation, 0)
                   for r in previous)
    assert economy.conservation["in_transit_delta"] == pytest.approx(expected, abs=2e-4)
    if pending_food:
        destination = world.regions[2].name
        assert economy.imports_by_region[destination]["food"] == pytest.approx(pending_food, abs=2e-4)
        # Food present at the destination includes the imported food, less
        # any prior queued departures; production/returns only add to it.
        outbound = sum(r.quantity for r in previous if r.operation == "departed"
                       and r.origin_region == 2 and r.good_slot in food_goods)
        demand = economy.market_demand[destination][0]
        lower_bound = min(2.0, max(0.0, pending_food - outbound) / max(demand, 0.1))
        assert economy.food_sufficiency[destination] >= lower_bound - 2e-5
    frame = world.transaction_receipts
    assert frame.complete and frame.mobility_executed and frame.dropped_rows == 0
    return result, list(frame.frame)


def _rows(rows, operation, voyage=None):
    return [r for r in rows if r.operation == operation and (voyage is None or r.voyage_id == voyage)]


def _commitment(bridge, region, good):
    from chronicler.columnar import pylist
    batch = bridge._sim.get_stockpile_commitments()
    cols = {name: pylist(batch.column(name)) for name in
            ("region_id", "good_slot", "reserved", "pending_departure")}
    for i, (rid, slot) in enumerate(zip(cols["region_id"], cols["good_slot"])):
        if (rid, slot) == (region, good):
            return cols["reserved"][i], cols["pending_departure"][i]
    raise AssertionError("native commitment row missing")


def _checkpoint(tmp_path, world, bridge):
    from chronicler.run_checkpoint import RunState, read_checkpoint, write_checkpoint
    path = tmp_path / "in-transit.ckpt"
    write_checkpoint(path, RunState(world=world, memories={}, history=[], chronicle_entries=[],
                     era_reflections={}, pending_injections=[], start_turn=0, seed=42,
                     num_turns=10, agent_bridge=bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    return loaded.state.world, loaded.state.agent_bridge


def _paired_turn(world, bridge, restored, resumed):
    before = random.getstate()
    result, rows = _advance(world, bridge)
    after = random.getstate()
    random.setstate(before)
    other_result, other_rows = _advance(restored, resumed)
    assert random.getstate() == after
    assert world.model_dump_json() == restored.model_dump_json()
    assert bridge._sim.checkpoint_state() == resumed._sim.checkpoint_state()
    assert [r.model_dump() for r in rows] == [r.model_dump() for r in other_rows]
    assert result.observation.source_turn == other_result.observation.source_turn
    return result, rows


def test_backed_transit_route_closure_return_reopen_and_exact_resume(tmp_path):
    world, bridge = _setup()
    # Region ingress precedes Phase 2: the planner first sees the previous
    # turn's economy. Allow that ordinary one-turn signal lag.
    first = []
    candidates = []
    for _ in range(3):
        _, first = _advance(world, bridge)
        candidates = [r for r in _rows(first, "reserved") if
                      (r.origin_region, r.dest_region, r.good_slot) == (0, 2, 0)]
        if candidates:
            break
    assert candidates, f"fixture must reserve a real 0→2 grain trip: {first!r}"
    reserved = candidates[0]
    assert reserved.quantity > 0 and reserved.cargo_basis == "regional_stock"
    committed, _ = _commitment(bridge, 0, 0)
    assert committed >= reserved.quantity - 1e-5

    _, second = _advance(world, bridge)
    departed = _rows(second, "departed", reserved.voyage_id)
    assert len(departed) == 1, f"reserved voyage must depart: {second!r}"
    qty = departed[0].quantity
    assert 0 < qty <= reserved.quantity + 1e-5
    assert not _rows(second, "arrived", reserved.voyage_id), "trip must be mid-transit"
    _, pending_debit = _commitment(bridge, 0, 0)
    assert pending_debit >= qty - 1e-5
    restored, resumed = _checkpoint(tmp_path, world, bridge)
    control, control_bridge = _checkpoint(tmp_path, world, bridge)

    # Close the destination's incident edge before the next native mobility.
    for w in (world, restored):
        w.regions[2].route_suspensions["trade_route"] = 2
    before_shock = random.getstate()
    _, interrupted = _paired_turn(world, bridge, restored, resumed)
    after_shock = random.getstate()
    random.setstate(before_shock)
    _, uninterrupted = _advance(control, control_bridge)
    assert random.getstate() == after_shock
    normal_arrival = _rows(uninterrupted, "arrived", reserved.voyage_id)
    assert len(normal_arrival) == 1
    assert normal_arrival[0].quantity == pytest.approx(qty)
    returned = _rows(interrupted, "returned", reserved.voyage_id)
    assert len(returned) == 1, f"in-flight trip must unwind: {interrupted!r}"
    assert returned[0].quantity == pytest.approx(qty)
    assert returned[0].return_reason is None  # ordinary route failure has no inferred cause
    assert "return_reason" not in returned[0].model_dump(mode="json")
    assert not _rows(interrupted, "arrived", reserved.voyage_id)

    # The next economy phase consumes the queued return.  Open the route and
    # require a new, observed voyage before claiming recovery.
    for w in (world, restored):
        w.regions[2].route_suspensions.pop("trade_route", None)
    # Consume the admitted control arrival and observe its decayed food import.
    from chronicler.columnar import pylist
    batch = control_bridge._sim.get_pending_arrivals()
    pending = [tuple(row) for row in zip(*(pylist(batch.column(c)) for c in
               ("source_region", "dest_region", "good_slot", "qty")))]
    assert any((src, dst, good) == (0, 2, 0) and q >= qty - 1e-5
               for src, dst, good, q in pending)
    assert not [r for r in uninterrupted if r.operation == "departed"
                and r.origin_region == 2 and r.good_slot in (0, 1, 2, 5, 7)]
    _advance(control, control_bridge)
    destination = control.regions[2].name
    economy = control._economy_result
    assert economy.imports_by_region[destination]["food"] >= qty * 0.95 - 2e-4
    demand = economy.market_demand[destination][0]
    assert demand > 0
    assert economy.food_sufficiency[destination] >= min(2.0, qty * 0.95 / demand) - 2e-5
    recovery = []
    for _ in range(5):
        _, rows = _paired_turn(world, bridge, restored, resumed)
        recovery.extend(rows)
    arrivals = [r for r in _rows(recovery, "arrived") if r.dest_region == 2 and r.good_slot == 0]
    assert arrivals, f"fixture must show a new grain delivery after reopening: {recovery!r}"
    complete = [r for r in arrivals if _rows(recovery, "reserved", r.voyage_id)
                and _rows(recovery, "departed", r.voyage_id)]
    assert complete, "recovery must include a newly reserved and departed voyage"
    # Ensure the chosen arrival is consumed by Phase 2, even if it occurred
    # on the last recovery tick. Later arrivals may also contribute to food.
    pending = bridge._sim.get_pending_arrivals()
    if pending.num_rows:
        _paired_turn(world, bridge, restored, resumed)


def _alternate_setup():
    """Two equal-length land paths, with one removable interior region."""
    native = pytest.importorskip("chronicler_agents")
    assert isinstance(getattr(native, "AgentSimulator", None), type)
    from chronicler.agent_bridge import AgentBridge
    from chronicler.transaction_receipts import set_transaction_receipts_enabled
    from chronicler.world_gen import generate_world
    world = generate_world(seed=42, num_regions=5, num_civs=1)
    world.agent_mode = "hybrid"
    civ = world.civilizations[0]
    civ.regions = [r.name for r in world.regions]
    civ.capital_region = world.regions[0].name
    # 0-1-2-3 is the deterministic shortest path; 1-4-3 is the detour.
    adjacency = ((1,), (0, 2, 4), (1, 3), (2, 4), (1, 3))
    for i, region in enumerate(world.regions):
        region.controller = civ.name
        region.population = (400, 20, 20, 400, 20)[i]
        region.carrying_capacity = 400
        region.stockpile.goods = {"grain": (2000.0, 300.0, 300.0, 0.0, 300.0)[i]}
        region.adjacencies = [world.regions[j].name for j in adjacency[i]]
        region.route_suspensions.clear()
        region.resource_types = ([0, 255, 255] if i != 3 else [255, 255, 255])
        region.resource_base_yields = ([1.0, 0.0, 0.0] if i != 3 else [0.0, 0.0, 0.0])
    civ.population = sum(r.population for r in world.regions)
    set_transaction_receipts_enabled(world, True)
    return world, AgentBridge(world, mode="hybrid")


def test_interrupted_transit_replans_alternate_path_and_delivers(tmp_path):
    world, bridge = _alternate_setup()
    reserved = None
    for _ in range(3):
        _, rows = _advance(world, bridge)
        candidates = [r for r in _rows(rows, "reserved") if
                      (r.origin_region, r.dest_region, r.good_slot) == (0, 3, 0)]
        if candidates:
            reserved = candidates[0]
            break
    assert reserved is not None, "alternate-path fixture must reserve 0→3 grain"
    _, rows = _advance(world, bridge)
    departures = _rows(rows, "departed", reserved.voyage_id)
    assert len(departures) == 1
    qty = departures[0].quantity
    assert qty > 0 and not _rows(rows, "arrived", reserved.voyage_id)
    restored, resumed = _checkpoint(tmp_path, world, bridge)
    for w in (world, restored):
        w.regions[2].route_suspensions["trade_route"] = 2
    _, rows = _paired_turn(world, bridge, restored, resumed)
    assert len(_rows(rows, "replanned", reserved.voyage_id)) == 1, "detour must be chosen"
    assert not _rows(rows, "returned", reserved.voyage_id)
    assert not _rows(rows, "arrived", reserved.voyage_id)
    _, rows = _paired_turn(world, bridge, restored, resumed)
    arrived = _rows(rows, "arrived", reserved.voyage_id)
    assert len(arrived) == 1 and arrived[0].quantity == pytest.approx(qty)
    _paired_turn(world, bridge, restored, resumed)
    destination = world.regions[3].name
    assert bridge._economy_result.imports_by_region[destination]["food"] >= qty * 0.95 - 2e-4


def _native_total_returns(bridge):
    from chronicler.columnar import pylist
    batch = bridge._sim.get_delivery_diagnostics()
    return sum(pylist(batch.column("total_returns")))


def test_controller_loss_unwinds_inflight_cargo_before_mobility(tmp_path):
    world, bridge = _setup(num_civs=2)
    reserved = None
    for _ in range(3):
        _, rows = _advance(world, bridge)
        choices = [r for r in _rows(rows, "reserved") if
                   (r.origin_region, r.dest_region, r.good_slot) == (0, 2, 0)]
        if choices:
            reserved = choices[0]
            break
    assert reserved is not None, "ownership fixture must reserve 0→2 grain"
    _, rows = _advance(world, bridge)
    departures = _rows(rows, "departed", reserved.voyage_id)
    assert len(departures) == 1 and departures[0].quantity > 0
    qty = departures[0].quantity
    assert not _rows(rows, "arrived", reserved.voyage_id)
    before = _native_total_returns(bridge)
    control, control_bridge = _checkpoint(tmp_path, world, bridge)

    # Apply the same owner-change marker as the production ownership path.
    old_owner, new_owner = world.civilizations[:2]
    region = world.regions[2]
    assert region.name in old_owner.regions and region.controller == old_owner.name
    old_owner.regions.remove(region.name)
    new_owner.regions.append(region.name)
    region.controller = new_owner.name
    region._controller_changed_this_turn = True
    before_tick = random.getstate()
    _, rows = _advance(world, bridge)
    after_tick = random.getstate()
    random.setstate(before_tick)
    _, control_rows = _advance(control, control_bridge)
    assert random.getstate() == after_tick
    arrival = _rows(control_rows, "arrived", reserved.voyage_id)
    assert len(arrival) == 1 and arrival[0].quantity == pytest.approx(qty)
    assert region.controller == new_owner.name
    returned = _native_total_returns(bridge) - before
    assert returned >= qty - 1e-5, "controller-change unwind must queue physical return"
    assert bridge._sim.get_merchant_trip_stats()["unwind_count"] > 0
    assert not _rows(rows, "arrived", reserved.voyage_id)
    traced = _rows(rows, "returned", reserved.voyage_id)
    assert len(traced) == 1 and traced[0].quantity == pytest.approx(qty)
    assert traced[0].return_reason == "controller_change"
    assert traced[0].loss_reason is None and traced[0].cargo_basis == "regional_stock"
    # Old pickle state predates the optional field and must remain readable.
    from copy import deepcopy
    from pydantic import ValidationError
    from chronicler.transaction_receipts_state import TransactionObservation
    old = deepcopy(traced[0].__getstate__())
    old["__dict__"].pop("return_reason")
    legacy = TransactionObservation.__new__(TransactionObservation)
    legacy.__setstate__(old)
    assert legacy.return_reason is None
    assert "return_reason" not in legacy.model_dump(mode="json")
    with pytest.raises(ValidationError):
        TransactionObservation.model_validate(traced[0].model_dump(mode="json") | {"return_reason": "invented"})
    # Complete receipt quantities equal the native cumulative return delta;
    # the next Phase 2 checks their physical in-transit balance.
    observed_returns = sum(r.quantity for r in _rows(rows, "returned"))
    assert returned == pytest.approx(observed_returns, abs=2e-4)
    _advance(world, bridge)


def test_reopening_restores_delivery_but_draws_food_from_another_region(tmp_path):
    # Closed path to region 2; region 1 receives grain from region 0.
    # Its deliberately empty opening market is shared by both continuations.
    closed, cb = _setup()
    closed.regions[2].route_suspensions["trade_route"] = 20
    for _ in range(2):
        _advance(closed, cb)
    closed.regions[1].stockpile.goods.clear()
    _advance(closed, cb)
    opened, ob = _checkpoint(tmp_path, closed, cb)
    opened.regions[2].route_suspensions.pop("trade_route", None)
    histories = []
    for _ in range(3):
        state = random.getstate()
        _, closed_rows = _advance(closed, cb)
        after = random.getstate()
        random.setstate(state)
        _, open_rows = _advance(opened, ob)
        # Both arms receive the same starting global RNG on every turn.
        random.setstate(after)
        histories.append((closed_rows, open_rows, cb._economy_result, ob._economy_result))

    def grain(rows, operation, origin, dest):
        return sum(r.quantity for r in rows if r.operation == operation
                   and (r.origin_region, r.dest_region, r.good_slot) == (origin, dest, 0))

    # Reopening induces a new shipment from the other food market (1) to 2.
    planned = grain(histories[0][1], "reserved", 1, 2)
    dispatched = grain(histories[1][1], "departed", 1, 2)
    arrived = grain(histories[1][1], "arrived", 1, 2)
    assert planned > 0 and dispatched == pytest.approx(planned)
    assert arrived == pytest.approx(dispatched)
    assert grain(histories[0][0], "reserved", 1, 2) == 0
    assert grain(histories[1][0], "departed", 1, 2) == 0
    # Phase 2 consumes the queued departure/arrival on the following turn.
    closed_economy, open_economy = histories[2][2:]
    harmed = closed.regions[1].name
    recipient = closed.regions[2].name
    demand = closed_economy.market_demand[harmed][0]
    assert demand > 0 and open_economy.market_demand[harmed][0] == pytest.approx(demand)
    assert open_economy.imports_by_region[recipient]["food"] >= dispatched * 0.95 - 2e-4
    assert open_economy.food_sufficiency[harmed] < closed_economy.food_sufficiency[harmed]
    assert (closed_economy.food_sufficiency[harmed] - open_economy.food_sufficiency[harmed]
            == pytest.approx(dispatched / demand, abs=2e-5))


def test_controller_receipt_observation_preserves_events_world_rng_and_native_state():
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result

    observed, ob = _setup(num_civs=2)
    plain, pb = _setup(num_civs=2, receipts=False)

    def step_pair():
        before = random.getstate()
        result, rows = _advance(observed, ob)
        after = random.getstate()
        random.setstate(before)
        engine = ActionEngine(plain)
        control = run_turn_result(plain, lambda c, w: engine.select_action(c, seed=w.seed),
                                  lambda w, events: "", seed=plain.seed + plain.turn,
                                  agent_bridge=pb)
        assert random.getstate() == after
        assert result.chronicle_text == control.chronicle_text
        assert observed.model_dump(mode="json", exclude={"transaction_receipts"}) == plain.model_dump(
            mode="json", exclude={"transaction_receipts"})
        assert ob._sim.get_snapshot().equals(pb._sim.get_snapshot())
        assert ob._sim.checkpoint_state() == pb._sim.checkpoint_state()
        return rows

    voyage = None
    for _ in range(4):
        rows = step_pair()
        departures = [r for r in _rows(rows, "departed") if
                      (r.origin_region, r.dest_region, r.good_slot) == (0, 2, 0)]
        if departures:
            voyage = departures[0].voyage_id
            assert not _rows(rows, "arrived", voyage)
            break
    assert voyage is not None, "observer-neutrality fixture needs actual in-flight grain"
    for w in (observed, plain):
        old, new = w.civilizations[:2]
        region = w.regions[2]
        old.regions.remove(region.name)
        new.regions.append(region.name)
        region.controller = new.name
        region._controller_changed_this_turn = True
    rows = step_pair()
    returned = _rows(rows, "returned", voyage)
    assert len(returned) == 1 and returned[0].return_reason == "controller_change"
    step_pair()  # consume the return in the economy in both modes


def test_controller_return_and_mobility_share_one_bounded_receipt_frame():
    from chronicler.action_engine import ActionEngine
    from chronicler.columnar import pylist
    from chronicler.simulation import run_turn_result

    world, bridge = _setup(num_civs=2)
    world.transaction_receipts.max_rows = 1
    def turn():
        engine = ActionEngine(world)
        run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed),
                        lambda w, events: "", seed=world.seed + world.turn,
                        agent_bridge=bridge)

    turn()  # actual reservations
    turn()  # actual departures
    old, new = world.civilizations[:2]
    region = world.regions[2]
    old.regions.remove(region.name)
    new.regions.append(region.name)
    region.controller = new.name
    region._controller_changed_this_turn = True
    turn()
    unwinds = int(bridge._sim.get_merchant_trip_stats()["unwind_count"])
    source, limit, dropped, executed, batch = bridge._sim.get_transaction_receipt_frame()
    assert unwinds > 1, "fixture must actually overflow the pre-mobility frame"
    assert source == world.turn - 1 and limit == 1 and executed
    assert batch.num_rows == 1 and pylist(batch.column("operation")) == [8]
    assert dropped >= unwinds - 1
    assert not world.transaction_receipts.complete
    assert world.transaction_receipts.dropped_rows == dropped
