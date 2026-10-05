"""Deterministic policy fixtures and focused economy integration."""
from __future__ import annotations

import math

import pyarrow as pa
import pytest

from chronicler.accumulator import StatAccumulator
from chronicler.economy import (
    EconomyResult, FIXED_GOODS, FOOD_GOODS, build_economy_region_input_batch,
    build_economy_trade_route_batch, compute_economy, reconstruct_economy_result,
)
from chronicler.models import MutualAidState, Region, WorldState
from chronicler.mutual_aid import dispatch_mutual_aid, observe_mutual_aid, read_stockpile_commitments


@pytest.fixture
def aid_world(make_world):
    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    world.mutual_aid_enabled = True
    world.agent_mode = "demographics-only"
    donor = world.regions[0]
    donor.name = "Granary"
    donor.population = 20
    donor.adjacencies = ["Mine"]
    donor.resource_types = [0, 255, 255]
    donor.resource_effective_yields = [1.0, 0.0, 0.0]
    donor.stockpile.goods = {"grain": 100.0, "fish": 20.0, "salt": 5.0, "ore": 7.0}
    mine = Region(name="Mine", terrain="hills", carrying_capacity=60,
                  population=20, resources="mineral", controller=civ.name,
                  adjacencies=["Granary"], resource_types=[5, 255, 255],
                  resource_effective_yields=[0.5, 0, 0])
    world.regions.append(mine)
    civ.regions = ["Granary", "Mine"]
    civ.population = 40
    world.invalidate_region_map()
    return world


def snapshot(world, counts=None):
    counts = counts or {r.name: 20 for r in world.regions}
    ids = [i for i, r in enumerate(world.regions) for _ in range(counts.get(r.name, 0))]
    return pa.record_batch({
        "region": pa.array(ids, type=pa.uint16()),
        "occupation": pa.array([0] * len(ids), type=pa.uint8()),
        "wealth": pa.array([0.0] * len(ids), type=pa.float32()),
        "civ_affinity": pa.array([0] * len(ids), type=pa.uint8()),
    })


def prime(world, suff=0.2, turns=3):
    snap = snapshot(world)
    for turn in range(turns):
        world.turn = turn
        result = EconomyResult(food_sufficiency={r.name: 1.5 for r in world.regions})
        result.food_sufficiency["Mine"] = suff
        observe_mutual_aid(world, result, snap)
    world.turn = turns
    return snap


def total_food(world):
    return math.fsum(r.stockpile.goods.get(g, 0) for r in world.regions for g in FOOD_GOODS)


def total_goods(world):
    return math.fsum(v for r in world.regions for v in r.stockpile.goods.values())


def test_activation_requires_three_consecutive_observations(aid_world):
    snap = prime(aid_world, turns=2)
    assert dispatch_mutual_aid(aid_world, snap) == []
    observe_mutual_aid(aid_world, EconomyResult(food_sufficiency={"Granary": 1.5, "Mine": 0.2}), snap)
    aid_world.turn += 1
    assert len(dispatch_mutual_aid(aid_world, snap)) == 1


def test_cost_composition_and_resource_conservation(aid_world):
    snap = prime(aid_world)
    before = total_food(aid_world)
    treasury = aid_world.civilizations[0].treasury
    nonfood = aid_world.regions[0].stockpile.goods["ore"]
    acc = StatAccumulator()
    events = dispatch_mutual_aid(aid_world, snap, acc=acc)
    assert len(events) == 1
    transfer = aid_world.mutual_aid_last_transfers[0]
    assert sum(transfer.sent.values()) == pytest.approx(2.5)
    assert transfer.sent["grain"] / transfer.sent["fish"] == pytest.approx(5.0)
    assert transfer.received["salt"] == transfer.sent["salt"]
    assert transfer.received["fish"] == pytest.approx(transfer.sent["fish"] * .92)
    assert before == pytest.approx(total_food(aid_world) + transfer.transit_loss)
    assert aid_world.regions[0].stockpile.goods["ore"] == nonfood
    assert treasury == aid_world.civilizations[0].treasury
    assert transfer.treasury_cost == 1
    acc.apply_keep(aid_world)
    assert aid_world.civilizations[0].treasury == treasury - 1
    acc.apply_keep(aid_world)
    assert aid_world.civilizations[0].treasury == treasury - 1
    assert dispatch_mutual_aid(aid_world, snap, acc=acc) == []
    assert len(aid_world.mutual_aid_last_transfers) == 1


@pytest.mark.parametrize("stock,expected", [(20, 0), (21, 1), (100, 2.5)])
def test_donor_reserve_and_capacity(aid_world, stock, expected):
    snap = prime(aid_world)
    aid_world.regions[0].stockpile.goods = {"grain": stock}
    dispatch_mutual_aid(aid_world, snap)
    assert aid_world.regions[0].stockpile.goods["grain"] == pytest.approx(stock - expected)
    assert aid_world.regions[0].stockpile.goods["grain"] >= 20


def test_recipient_delivered_need_limits_dispatch(aid_world):
    snap = prime(aid_world, suff=.75)
    aid_world.regions[1].stockpile.goods = {"grain": 9.0}
    dispatch_mutual_aid(aid_world, snap)
    assert total_food(aid_world) < 135
    assert sum(aid_world.mutual_aid_last_transfers[0].received.values()) == pytest.approx(1.0)
    assert aid_world.regions[1].stockpile.goods["grain"] < 10.0  # mixed composition
    assert math.fsum(aid_world.regions[1].stockpile.goods.values()) == pytest.approx(10.0)


@pytest.mark.parametrize("case", ["no_treasury", "foreign", "one_way", "not_adjacent",
    "zero_agents", "stale", "changed_controller", "bad_stock", "unlisted_owner", "donor_stressed"])
def test_ineligible_no_transfer(aid_world, case):
    snap = prime(aid_world)
    donor, recipient = aid_world.regions
    if case == "no_treasury":
        aid_world.civilizations[0].treasury = 0
    elif case == "foreign":
        donor.controller = "Other"
    elif case == "one_way":
        donor.adjacencies = []
    elif case == "not_adjacent":
        recipient.adjacencies = []
        donor.adjacencies = []
    elif case == "zero_agents":
        snap = snapshot(aid_world, {"Granary": 20, "Mine": 0})
    elif case == "stale":
        aid_world.turn += 1
    elif case == "changed_controller":
        aid_world.mutual_aid_state["Mine"].controller = "Former"
    elif case == "bad_stock":
        donor.stockpile.goods["grain"] = float("nan")
    elif case == "unlisted_owner":
        aid_world.civilizations[0].regions.remove("Mine")
    elif case == "donor_stressed":
        aid_world.mutual_aid_state["Granary"].food_sufficiency = .5
    before = [r.stockpile.model_dump_json() for r in aid_world.regions]
    treasury = aid_world.civilizations[0].treasury
    assert dispatch_mutual_aid(aid_world, snap) == []
    assert [r.stockpile.model_dump_json() for r in aid_world.regions] == before
    assert aid_world.civilizations[0].treasury == treasury


def test_pending_treasury_costs_are_respected(aid_world):
    snap = prime(aid_world)
    acc = StatAccumulator()
    civ = aid_world.civilizations[0]
    acc.add(0, civ, "treasury", -civ.treasury, "keep")
    assert dispatch_mutual_aid(aid_world, snap, acc) == []


def test_previously_applied_cost_not_counted_twice(aid_world):
    snap = prime(aid_world)
    civ = aid_world.civilizations[0]
    civ.treasury = 2
    acc = StatAccumulator()
    acc.add(0, civ, "treasury", -1, "keep")
    acc.apply_keep(aid_world)
    assert len(dispatch_mutual_aid(aid_world, snap, acc)) == 1
    acc.apply_keep(aid_world)
    assert civ.treasury == 0


def test_fractional_pending_credits_cannot_subsidize_aid(aid_world):
    snap = prime(aid_world)
    civ = aid_world.civilizations[0]
    civ.treasury = 0
    acc = StatAccumulator()
    acc.add(0, civ, "treasury", .6, "keep")
    acc.add(0, civ, "treasury", .6, "keep")
    assert dispatch_mutual_aid(aid_world, snap, acc) == []
    acc.apply_keep(aid_world)
    assert civ.treasury == 0


def test_demand_tuning_protects_two_actual_turns(aid_world):
    snap = prime(aid_world)
    aid_world.tuning_overrides["economy.per_capita_food"] = 1.0
    aid_world.regions[0].stockpile.goods = {"grain": 42.0}
    dispatch_mutual_aid(aid_world, snap)
    assert aid_world.regions[0].stockpile.goods["grain"] == pytest.approx(40.0)


def test_commitments_protect_per_good_cargo_and_donor_reserve(aid_world):
    snap = prime(aid_world)
    aid_world.agent_mode = "hybrid"
    commitments = {r.name: dict.fromkeys(FIXED_GOODS, 0.0) for r in aid_world.regions}
    commitments["Granary"]["grain"] = 100.0  # fully merchant-committed, cannot donate
    commitments["Granary"]["fish"] = 3.0
    dispatch_mutual_aid(aid_world, snap, commitments=commitments)
    transfer = aid_world.mutual_aid_last_transfers[0]
    assert "grain" not in transfer.sent
    assert sum(transfer.sent.values()) == pytest.approx(2.0)  # free22 - reserve20
    assert aid_world.regions[0].stockpile.goods["grain"] == 100.0
    free = sum(aid_world.regions[0].stockpile.goods.get(g, 0) - commitments["Granary"][g]
               for g in FOOD_GOODS)
    assert free == pytest.approx(20.0)


def test_hybrid_missing_commitments_fails_before_mutation(aid_world):
    snap = prime(aid_world)
    aid_world.agent_mode = "hybrid"
    before = aid_world.model_dump_json()
    with pytest.raises(RuntimeError, match="accounting"):
        dispatch_mutual_aid(aid_world, snap)
    assert aid_world.model_dump_json() == before
    with pytest.raises(ValueError, match="complete"):
        dispatch_mutual_aid(aid_world, snap, commitments={})
    assert aid_world.model_dump_json() == before


def test_multiple_donors_share_recipient_capacity_and_civ_budget(aid_world):
    for name in ("B_Granary", "C_Granary"):
        donor = aid_world.regions[0].model_copy(deep=True)
        donor.name = name
        aid_world.regions.append(donor)
        aid_world.regions[1].adjacencies.append(name)
        aid_world.civilizations[0].regions.append(name)
    aid_world.invalidate_region_map()
    snap = prime(aid_world, suff=0.0)
    dispatch_mutual_aid(aid_world, snap)
    assert sum(sum(t.received.values()) for t in aid_world.mutual_aid_last_transfers) == pytest.approx(5.0)
    assert len(aid_world.mutual_aid_last_transfers) == 3
    assert aid_world.civilizations[0].treasury == 47


def test_exhausted_budget_blocks_later_recipients(aid_world):
    other = aid_world.regions[1].model_copy(deep=True)
    other.name = "Other_Mine"
    donor = aid_world.regions[0].model_copy(deep=True)
    donor.name = "Other_Granary"
    donor.adjacencies = [other.name]
    other.adjacencies = [donor.name]
    aid_world.regions.extend([other, donor])
    aid_world.civilizations[0].regions.extend([other.name, donor.name])
    aid_world.civilizations[0].treasury = 1
    aid_world.invalidate_region_map()
    snap = prime(aid_world)
    aid_world.mutual_aid_state[other.name] = aid_world.mutual_aid_state["Mine"].model_copy(deep=True)
    dispatch_mutual_aid(aid_world, snap)
    assert len(aid_world.mutual_aid_last_transfers) == 1
    assert aid_world.mutual_aid_last_transfers[0].recipient == "Mine"
    assert aid_world.civilizations[0].treasury == 0
    assert other.stockpile.goods == {}


@pytest.mark.parametrize("suff", [.8, 1.0, 2.0])
def test_recovery_resets_memory(aid_world, suff):
    snap = prime(aid_world)
    observe_mutual_aid(aid_world, EconomyResult(food_sufficiency={"Granary": 1.5, "Mine": suff}), snap)
    assert aid_world.mutual_aid_state["Mine"].stress_streak == 0
    aid_world.turn += 1
    assert dispatch_mutual_aid(aid_world, snap) == []


def test_observation_is_idempotent_and_discontinuity_restarts_memory(aid_world):
    snap = prime(aid_world, turns=1)
    result = EconomyResult(food_sufficiency={"Granary": 1.5, "Mine": .2})
    aid_world.turn = 0
    observe_mutual_aid(aid_world, result, snap)
    assert aid_world.mutual_aid_state["Mine"].stress_streak == 1
    aid_world.turn = 3
    observe_mutual_aid(aid_world, result, snap)
    assert aid_world.mutual_aid_state["Mine"].stress_streak == 1
    aid_world.turn += 1
    aid_world.mutual_aid_state["Mine"].controller = "Former"
    observe_mutual_aid(aid_world, result, snap)
    assert aid_world.mutual_aid_state["Mine"].stress_streak == 1


@pytest.mark.parametrize("suff", [None, float("nan"), float("inf"), -1, 3])
def test_missing_or_invalid_observation_clears_memory(aid_world, suff):
    snap = prime(aid_world)
    observe_mutual_aid(aid_world, EconomyResult(food_sufficiency={"Mine": suff}), snap)
    assert "Mine" not in aid_world.mutual_aid_state


def test_no_runtime_clears_memory(aid_world):
    prime(aid_world)
    observe_mutual_aid(aid_world, None, None)
    assert aid_world.mutual_aid_state == {}


def test_disabled_is_complete_noop_even_with_saved_state(aid_world):
    snap = prime(aid_world)
    aid_world.mutual_aid_enabled = False
    before = aid_world.model_dump_json()
    observe_mutual_aid(aid_world, EconomyResult(food_sufficiency={"Mine": 0}), snap)
    assert dispatch_mutual_aid(aid_world, snap) == []
    assert aid_world.model_dump_json() == before


def test_default_off_and_cli_tristate(make_world):
    from chronicler.main import _build_parser
    assert make_world().mutual_aid_enabled is False
    parser = _build_parser()
    assert parser.parse_args([]).mutual_aid is None
    assert parser.parse_args(["--mutual-aid"]).mutual_aid is True
    assert parser.parse_args(["--no-mutual-aid"]).mutual_aid is False


def test_save_resume_preserves_dispatch_and_memory(aid_world, tmp_path):
    snap = prime(aid_world)
    path = tmp_path / "state.json"
    aid_world.save(path)
    restored = WorldState.load(path)
    dispatch_mutual_aid(aid_world, snap)
    dispatch_mutual_aid(restored, snap)
    assert restored.model_dump() == aid_world.model_dump()
    restored.save(path)
    restored = WorldState.load(path)
    assert dispatch_mutual_aid(restored, snap) == []


def test_shared_donor_capacity_and_deterministic_recipient_priority(aid_world):
    other = aid_world.regions[1].model_copy(deep=True)
    other.name = "A_Mine"
    aid_world.regions.append(other)
    aid_world.regions[0].adjacencies.append(other.name)
    aid_world.civilizations[0].regions.append(other.name)
    aid_world.invalidate_region_map()
    snap = prime(aid_world)
    aid_world.mutual_aid_state[other.name] = MutualAidState(
        controller=other.controller, stress_streak=3, food_sufficiency=.2,
        last_observed_turn=2,
    )
    reversed_world = aid_world.model_copy(deep=True)
    reversed_world.regions.reverse()
    reversed_world.invalidate_region_map()
    dispatch_mutual_aid(aid_world, snap)
    dispatch_mutual_aid(reversed_world, snapshot(reversed_world))
    assert aid_world.mutual_aid_last_transfers == reversed_world.mutual_aid_last_transfers
    assert len(aid_world.mutual_aid_last_transfers) == 1
    assert aid_world.mutual_aid_last_transfers[0].recipient == "A_Mine"
    assert sum(aid_world.mutual_aid_last_transfers[0].sent.values()) == pytest.approx(2.5)


def test_real_python_economy_consumes_aid_and_accounts_for_loss(aid_world):
    snap = prime(aid_world)
    control = aid_world.model_copy(deep=True)
    control.mutual_aid_enabled = False
    before = total_goods(aid_world)
    dispatch_mutual_aid(aid_world, snap)
    result = compute_economy(aid_world, snap, aid_world.region_map, True, active_trade_routes=[])
    baseline = compute_economy(control, snap, control.region_map, True, active_trade_routes=[])
    assert result.food_sufficiency["Mine"] > baseline.food_sufficiency["Mine"]
    assert result.food_sufficiency["Granary"] >= 1
    c = result.conservation
    aid_loss = sum(t.transit_loss for t in aid_world.mutual_aid_last_transfers)
    assert before + c["production"] + c["clamp_floor_loss"] == pytest.approx(
        total_goods(aid_world) + aid_loss + c["consumption"] + c["transit_loss"]
        + c["storage_loss"] + c["cap_overflow"] + (c["in_transit_delta"] or 0))
    observe_mutual_aid(aid_world, result, snap)
    assert aid_world.mutual_aid_state["Mine"].last_observed_turn == aid_world.turn


@pytest.mark.native
def test_native_economy_receives_aid_before_input_packing(aid_world):
    native = pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import build_region_batch, configure_economy_runtime
    prime(aid_world)
    sim = native.AgentSimulator(num_regions=2, seed=42)
    aid_world.agent_mode = "hybrid"
    configure_economy_runtime(sim, aid_world)
    sim.set_hybrid_economy_mode(True)
    sim.set_region_state(build_region_batch(aid_world))
    snap = sim.get_snapshot()
    before = total_goods(aid_world)
    events = dispatch_mutual_aid(aid_world, snap, commitments=read_stockpile_commitments(aid_world, sim))
    assert len(events) == 1
    donated = sum(aid_world.mutual_aid_last_transfers[0].received.values())
    inputs = build_economy_region_input_batch(aid_world)
    assert sum(inputs.column(f"stockpile_{g}")[1].as_py() for g in FOOD_GOODS) == pytest.approx(donated)
    returns = sim.tick_economy(inputs, build_economy_trade_route_batch(aid_world, []), 0, False, 1.0)
    result = reconstruct_economy_result(*returns, aid_world, require_oracle_shadow=True)
    assert result.food_sufficiency["Mine"] > 0
    c = result.conservation
    aid_loss = sum(t.transit_loss for t in aid_world.mutual_aid_last_transfers)
    assert before + c["production"] + c["clamp_floor_loss"] == pytest.approx(
        total_goods(aid_world) + aid_loss + c["consumption"] + c["transit_loss"]
        + c["storage_loss"] + c["cap_overflow"] + (c["in_transit_delta"] or 0), abs=2e-5)


@pytest.mark.native
def test_full_turn_loop_routes_aid_to_native_economy(aid_world):
    pytest.importorskip("chronicler_agents")
    from chronicler.agent_bridge import AgentBridge
    from chronicler.models import ActionType
    from chronicler.simulation import run_turn
    prime(aid_world)
    aid_world.agent_mode = "hybrid"
    bridge = AgentBridge(aid_world, mode="hybrid")
    try:
        run_turn(aid_world, lambda civ, w: ActionType.DEVELOP, lambda w, events: "",
                 seed=42, agent_bridge=bridge)
        assert len(aid_world.mutual_aid_last_transfers) == 1
        assert aid_world.mutual_aid_last_transfers[0].turn == 3
        assert aid_world.mutual_aid_last_transfers[0].treasury_cost == 1
        assert bridge._economy_result.food_sufficiency["Mine"] > 0
        assert any(e.event_type == "mutual_aid" and e.turn == 3 for e in aid_world.events_timeline)
        assert aid_world.mutual_aid_state["Mine"].last_observed_turn == 3
    finally:
        bridge.close()
