"""Focused real-native Scholar work boundaries; no full-run qualification."""
from __future__ import annotations

import math

import pyarrow as pa
import pytest

pytest.importorskip("chronicler_agents")

from chronicler.agent_bridge import AgentBridge, build_signals
from chronicler.run_checkpoint import CheckpointError, RunState, read_checkpoint, write_checkpoint
from chronicler.world_gen import generate_world

pytestmark = pytest.mark.native


def _setup():
    import chronicler_agents as ca
    assert isinstance(ca.AgentSimulator, type)
    assert hasattr(ca.AgentSimulator, "prepare_teaching_work"), "fresh M5 extension required"
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
    scholars = [row for row in rows if row["occupation"] == 3 and row["age"] >= 20]
    assert scholars, "the declared seed-42 world needs an eligible adult Scholar"
    region = scholars[0]["region"]
    requests = [0.0] * len(world.regions)
    requests[region] = 0.5
    return world, bridge, region, requests


def _state(world, bridge):
    return RunState(world=world, agent_bridge=bridge, memories={}, history=[],
        chronicle_entries=[], era_reflections={}, pending_injections=[], start_turn=0,
        seed=world.seed, num_turns=4)


def test_real_pending_teaching_refuses_checkpoint_until_cancelled(tmp_path):
    world, bridge, region, requests = _setup()
    sim = bridge._sim
    native_before = bytes(sim.checkpoint_state())
    planned = sim.prepare_teaching_work(world.turn, requests, [])
    assert planned[0] == world.turn and planned[1][region][3] == 0.5
    assert sim.has_pending_teaching_work()
    assert bytes(sim.checkpoint_state()) == native_before  # plan is transient
    path = tmp_path / "pending.ckpt"
    with pytest.raises(CheckpointError, match="native teaching work is pending"):
        write_checkpoint(path, _state(world, bridge))
    assert not path.exists()
    assert sim.has_pending_teaching_work()
    assert sim.cancel_teaching_work(world.turn)
    assert not sim.has_pending_teaching_work()
    assert bytes(sim.checkpoint_state()) == native_before
    write_checkpoint(path, _state(world, bridge))
    restored = read_checkpoint(path)
    assert restored.exact
    assert bytes(restored.state.agent_bridge._sim.checkpoint_state()) == native_before
    assert not restored.state.agent_bridge._sim.has_pending_teaching_work()
    assert restored.state.world.model_dump_json() == world.model_dump_json()
    bridge.close()
    restored.state.agent_bridge.close()


def test_real_invalid_requests_and_paid_work_reduce_only_available_income():
    import chronicler_agents as ca
    world, bridge, region, requests = _setup()
    sim = bridge._sim
    before = bytes(sim.checkpoint_state())
    for bad in ([-1.0] + [0.0] * 7, [float("nan")] + [0.0] * 7,
                [float("inf")] + [0.0] * 7, [0.5]):
        with pytest.raises(ValueError):
            sim.prepare_teaching_work(world.turn, bad, [])
        assert bytes(sim.checkpoint_state()) == before
        assert not sim.has_pending_teaching_work()
    prepared = sim.prepare_teaching_work(world.turn, requests, [])
    assert prepared[1][region][3:] == (0.5, 0.0)  # reserved, not yet delivered
    teacher_id, teacher_region, reserved, delivered = prepared[2][0]
    assert (teacher_region, reserved, delivered) == (region, 0.5, 0.0)
    control = ca.AgentSimulator.from_checkpoint_state(before)
    signals = build_signals(world)
    sim.tick(world.turn, signals)
    control.tick(world.turn, signals)
    consumed = sim.get_teaching_work_result()
    assert consumed[0] == world.turn
    assert consumed[1][region][3:] == (0.5, 0.5)
    assert consumed[2][0] == (teacher_id, region, 0.5, 0.5)
    assert not sim.has_pending_teaching_work()
    def agents(native):
        return {row["id"]: row for row in pa.record_batch(native.get_snapshot()).to_pylist()}
    actual, baseline = agents(sim), agents(control)
    assert teacher_id in actual and teacher_id in baseline
    # 0.5 of a Scholar's 0.2 ordinary income, after the model's 0.98 decay.
    difference = baseline[teacher_id]["wealth"] - actual[teacher_id]["wealth"]
    assert math.isclose(difference, 0.098, abs_tol=1e-6)
    after = bytes(sim.checkpoint_state())
    assert sim.get_teaching_work_result() == consumed
    assert bytes(sim.checkpoint_state()) == after
    bridge.close()


def _paid_service_setup():
    """One fixed finite seed-42 world with a pre-existing academy and market.

    City markets make native craft demand and prices real. Initial market
    inventory and treasury are scenario endowments, not fabricated purchases.
    Native scholars, service work, transfers and receipts are not mocked.
    """
    from chronicler.cities import set_cities_enabled
    from chronicler.learning_services import set_learning_services_enabled
    from chronicler.scholarship_state import ACADEMY, ScholarshipState, Seat

    world = generate_world(seed=42, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    set_cities_enabled(world, True)
    bridge = AgentBridge(world, mode="hybrid")
    rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
    person = next(row for row in rows if row["occupation"] == 3 and row["age"] >= 20
                  and world.regions[row["region"]].controller is not None)
    region = person["region"]
    owner = world.civ_index_map[world.regions[region].controller]
    for r in world.regions:
        r.stockpile.goods = {"grain": 100.0}
    world.regions[region].stockpile.goods["crafts"] = 100.0
    world.civilizations[owner].treasury = 500
    world.scholarship = ScholarshipState(seats=[Seat(region=region, kind=ACADEMY,
        name="Declared Academy", founded_turn=world.turn, founder=owner, lord=owner)])
    set_learning_services_enabled(world, True)
    return world, bridge, region, owner


def _service_turn(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(world)
    return run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed),
        lambda w, events: "", seed=world.seed + world.turn, agent_bridge=bridge)


def test_paid_supplies_become_actual_native_teaching_after_exact_resume(tmp_path):
    import random
    world, bridge, region, owner = _paid_service_setup()
    _service_turn(world, bridge)
    services = world.scholarship.learning_services
    purchase = next(row for row in services.procurement_receipts if row.seat_id == 0)
    assert purchase.source_turn == 0 and purchase.region == region
    assert purchase.upkeep_satisfied is True
    assert purchase.craft_price > 0 and purchase.market_stock > 0
    assert purchase.purchased > 0 and purchase.paid > 0
    assert purchase.paid == math.ceil(purchase.purchased * purchase.craft_price)
    assert purchase.held_after == pytest.approx(purchase.held_before + purchase.purchased)
    # Actual same-boundary purchase moves stock from market into custody once.
    assert purchase.market_stock - world.regions[region].stockpile.goods["crafts"] == pytest.approx(purchase.purchased)
    balance = services.material_balance
    assert balance["source_turn"] == 0 and balance["available_turn"] == 1
    assert balance["purchased"] == pytest.approx(purchase.purchased)
    assert abs(balance["residual"]) <= balance["absolute_tolerance"]
    asset = next(a for a in services.inventories if not a.retired and a.seat_id == 0)
    assert (asset.seat_id, asset.region, asset.founder, asset.founded_turn, asset.seat_name) == (
        purchase.seat_id, purchase.region, purchase.founder, purchase.founded_turn, purchase.seat_name)
    assert asset.held == pytest.approx(purchase.held_after)
    assert asset.purchased_total == pytest.approx(purchase.purchased)
    assert not bridge._sim.has_pending_teaching_work()
    path = tmp_path / "paid-held.ckpt"
    write_checkpoint(path, _state(world, bridge))
    loaded = read_checkpoint(path)
    assert loaded.exact
    restored, resumed = loaded.state.world, loaded.state.agent_bridge
    assert restored.scholarship.learning_services.inventories == services.inventories
    rng = random.getstate()
    _service_turn(world, bridge)
    after = random.getstate()
    random.setstate(rng)
    _service_turn(restored, resumed)
    assert random.getstate() == after
    assert world.model_dump_json() == restored.model_dump_json()
    assert bridge._sim.checkpoint_state() == resumed._sim.checkpoint_state()
    teaching = next(row for row in world.scholarship.learning_services.teaching_receipts if row.seat_id == 0)
    assert teaching.source_turn == 1 and teaching.available_turn == 2
    assert (teaching.seat_id, teaching.region, teaching.founder, teaching.founded_turn, teaching.seat_name) == (
        purchase.seat_id, purchase.region, purchase.founder, purchase.founded_turn, purchase.seat_name)
    assert teaching.upkeep_satisfied is True
    assert teaching.work_requested > 0 and teaching.work_delivered > 0
    assert 0 < teaching.work_delivered <= teaching.work_reserved <= teaching.work_available
    assert teaching.crafts_used == pytest.approx(teaching.work_delivered * 8.0)
    assert teaching.held_before - teaching.held_after == pytest.approx(teaching.crafts_used)
    balance = world.scholarship.learning_services.material_balance
    assert balance["source_turn"] == 1 and balance["used"] == pytest.approx(teaching.crafts_used)
    assert abs(balance["residual"]) <= balance["absolute_tolerance"]
    assert not bridge._sim.has_pending_teaching_work()
    assert not resumed._sim.has_pending_teaching_work()
    bridge.close()
    resumed.close()


def test_empty_market_cannot_fabricate_paid_supplies_or_teaching():
    world, bridge, region, owner = _paid_service_setup()
    world.regions[region].stockpile.goods["crafts"] = 0.0
    _service_turn(world, bridge)
    services = world.scholarship.learning_services
    purchase = next(row for row in services.procurement_receipts if row.seat_id == 0)
    assert purchase.purchased == 0 and purchase.paid == 0 and purchase.held_after == 0
    _service_turn(world, bridge)
    teaching = next(row for row in world.scholarship.learning_services.teaching_receipts if row.seat_id == 0)
    assert teaching.work_requested == 0
    assert teaching.crafts_used in (None, 0)
    assert teaching.held_before == teaching.held_after == 0
    assert not bridge._sim.has_pending_teaching_work()
    bridge.close()


def test_common_paid_holdings_active_vs_paused_real_scholar_income(tmp_path):
    import random
    from chronicler.learning_services import set_learning_services_enabled
    world, bridge, region, owner = _paid_service_setup()
    _service_turn(world, bridge)
    held = world.scholarship.learning_services.inventories[0].held
    assert held > 0
    path = tmp_path / "paired-paid.ckpt"
    write_checkpoint(path, _state(world, bridge))
    active, paused = read_checkpoint(path).state, read_checkpoint(path).state
    set_learning_services_enabled(paused.world, False)
    assert active.agent_bridge._sim.checkpoint_state() == paused.agent_bridge._sim.checkpoint_state()
    rng = random.getstate()
    _service_turn(active.world, active.agent_bridge)
    after = random.getstate()
    random.setstate(rng)
    _service_turn(paused.world, paused.agent_bridge)
    assert random.getstate() == after
    native = active.agent_bridge._sim.get_teaching_work_result()
    assert native is not None and native[0] == 1
    rows = [row for row in native[2] if row[1] == region and row[3] > 0]
    assert rows
    assert paused.agent_bridge._sim.get_teaching_work_result() is None
    def agents(sim):
        return {row["id"]: row for row in pa.record_batch(sim.get_snapshot()).to_pylist()}
    a, b = agents(active.agent_bridge._sim), agents(paused.agent_bridge._sim)
    # A surviving real Scholar's ordinary income is reduced by the fraction
    # delivered; no synthetic instructor, wage or wealth is introduced.
    matched = [(r, b[r[0]]["wealth"] - a[r[0]]["wealth"]) for r in rows if r[0] in a and r[0] in b]
    assert any(math.isclose(diff, 0.2 * row[3] * 0.98, abs_tol=1e-6) for row, diff in matched)
    assert paused.world.scholarship.learning_services.inventories[0].held == pytest.approx(held)
    assert active.world.scholarship.learning_services.teaching_receipts[0].work_delivered > 0
    for obj in (bridge, active.agent_bridge, paused.agent_bridge):
        obj.close()


def test_restored_market_supplies_recover_after_a_real_shortage():
    world, bridge, region, owner = _paid_service_setup()
    world.regions[region].stockpile.goods["crafts"] = 0.0
    _service_turn(world, bridge)
    first = world.scholarship.learning_services.procurement_receipts[0]
    assert first.purchased == first.paid == 0
    assert world.scholarship.seats[0].fallen_turn is None
    # Explicit exogenous finite restock at a turn boundary; it is a 100-unit
    # source addition, not production, an academy purchase, or a shipment.
    stock_before = world.regions[region].stockpile.goods.get("crafts", 0.0)
    world.regions[region].stockpile.goods["crafts"] = stock_before + 100.0
    assert world.regions[region].stockpile.goods["crafts"] - stock_before == 100.0
    _service_turn(world, bridge)
    second = world.scholarship.learning_services.procurement_receipts[0]
    blocked = world.scholarship.learning_services.teaching_receipts[0]
    assert blocked.work_requested == 0 and blocked.crafts_used in (None, 0)
    assert second.purchased > 0 and second.paid > 0 and second.held_after > 0
    _service_turn(world, bridge)
    recovered = world.scholarship.learning_services.teaching_receipts[0]
    assert recovered.work_delivered > 0 and recovered.crafts_used > 0
    assert recovered.held_before - recovered.held_after == pytest.approx(recovered.crafts_used)
    bridge.close()


def test_controller_change_preserves_held_material_and_needs_new_upkeep():
    world, bridge, region, owner = _paid_service_setup()
    _service_turn(world, bridge)
    previous = world.scholarship.learning_services.inventories[0]
    held = previous.held
    assert held > 0 and previous.upkeep_lord == owner
    new_owner = next(i for i, civ in enumerate(world.civilizations) if i != owner
        and (civ.name, world.civilizations[owner].name) not in world.active_wars
        and (world.civilizations[owner].name, civ.name) not in world.active_wars)
    old_civ, new_civ = world.civilizations[owner], world.civilizations[new_owner]
    name = world.regions[region].name
    old_civ.regions = [r for r in old_civ.regions if r != name]
    if name not in new_civ.regions:
        new_civ.regions.append(name)
    world.regions[region].controller = new_civ.name
    new_civ.treasury = 500
    # This is a declared controller transition, not a simulated battle.
    _service_turn(world, bridge)
    blocked = world.scholarship.learning_services.teaching_receipts[0]
    assert blocked.source_turn == 1 and blocked.work_requested == 0
    assert blocked.upkeep_lord == owner
    assert blocked.crafts_used in (None, 0)
    assert blocked.held_before == pytest.approx(held)
    assert blocked.held_after == pytest.approx(held)
    asset = next(a for a in world.scholarship.learning_services.inventories if not a.retired)
    assert asset.upkeep_lord == new_owner and asset.upkeep_source_turn == 1
    _service_turn(world, bridge)
    recovered = world.scholarship.learning_services.teaching_receipts[0]
    assert recovered.upkeep_lord == new_owner and recovered.upkeep_applies is True
    assert recovered.work_delivered is not None and recovered.work_delivered > 0
    bridge.close()


def test_hostile_controller_transition_records_destroyed_holdings_once():
    world, bridge, region, owner = _paid_service_setup()
    _service_turn(world, bridge)
    held = world.scholarship.learning_services.inventories[0].held
    old_civ = world.civilizations[owner]
    hostile = next(c for c in world.civilizations if c.name != old_civ.name
        and ((c.name, old_civ.name) in world.active_wars or (old_civ.name, c.name) in world.active_wars))
    name = world.regions[region].name
    old_civ.regions = [r for r in old_civ.regions if r != name]
    if name not in hostile.regions:
        hostile.regions.append(name)
    world.regions[region].controller = hostile.name
    # Controlled transfer while the named rulers are at war; the simulated
    # scholarship phase, not this test, decides whether the academy falls.
    _service_turn(world, bridge)
    seat = world.scholarship.seats[0]
    asset = world.scholarship.learning_services.inventories[0]
    assert seat.fallen_turn == 1 and asset.retired
    assert asset.held == 0 and asset.lost_total == pytest.approx(held)
    losses = world.scholarship.learning_services.supply_losses
    assert len(losses) == 1 and losses[0].lost == pytest.approx(held)
    balance = world.scholarship.learning_services.material_balance
    assert balance["lost"] == pytest.approx(held)
    assert abs(balance["residual"]) <= balance["absolute_tolerance"]
    _service_turn(world, bridge)
    assert world.scholarship.learning_services.inventories[0].lost_total == pytest.approx(held)
    assert world.scholarship.learning_services.material_balance["lost"] == 0
    bridge.close()
