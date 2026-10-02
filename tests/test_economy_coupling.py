"""Regressions for realized harvests, accessible inventory, and real goods flow.

Native cases are genuine Rust/Python parity checks, skipped only if the optional
extension is absent. They do not label Python-only runs as Rust validation.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import random

import pytest

from chronicler.ecology import refresh_resource_yields
from chronicler.economy import (
    FIXED_GOODS, compute_allocated_production,
    compute_economy, build_economy_region_input_batch,
)
from chronicler.models import ClimatePhase


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "economy_coupling_experiment.py"
_SPEC = importlib.util.spec_from_file_location("economy_coupling_experiment", _SCRIPT)
experiment = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(experiment)


def _oracle(world, snapshot=None, routes=()):
    return compute_economy(
        world, snapshot if snapshot is not None else experiment.controlled_snapshot(),
        {r.name: r for r in world.regions}, agent_mode=True, active_trade_routes=list(routes),
    )


def _native_available():
    native = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(native, "AgentSimulator", None), type):
        pytest.skip("chronicler_agents is not a real native extension")


def test_paired_drought_reserve_and_trade_interventions():
    report = experiment.run_experiment("python")
    assert report["checks_passed"]
    cases = report["paired_cases"]
    wet = cases["temperate_no_reserve"]["regions"][experiment.TARGET]
    dry = cases["drought_no_reserve"]["regions"][experiment.TARGET]
    reserved = cases["drought_with_reserve"]["regions"][experiment.TARGET]
    imported = cases["drought_route_open"]["regions"][experiment.TARGET]
    assert dry["expected_harvest_by_good"]["grain"] == pytest.approx(wet["expected_harvest_by_good"]["grain"] * 0.5)
    assert dry["food_price"] > wet["food_price"]
    assert reserved["food_price"] < dry["food_price"]
    assert imported["food_price"] < dry["food_price"]
    assert reserved["expected_harvest_by_good"] == dry["expected_harvest_by_good"]
    assert dry["famine_event"] and not reserved["famine_event"] and not imported["famine_event"]


def test_native_paired_drought_reserve_trade_and_actual_python_parity():
    _native_available()
    report = experiment.run_experiment("rust")
    assert report["backend"] == "native-rust-abstract-trade"
    for case in report["paired_cases"].values():
        assert max(case["python_parity"].values()) < 0.002


@pytest.mark.parametrize("types,yields,expected", [
    ([0, 4, 6], [1.0, 2.0, 3.0], {"grain": 20.0, "salt": 40.0, "precious": 60.0}),
    ([255, 4, 6], [99.0, 2.0, 3.0], {"salt": 60.0, "precious": 90.0}),
    ([0, 0, 6], [1.0, 2.0, 3.0], {"grain": 60.0, "precious": 60.0}),
    ([0, 4, 6], [1.0, 0.0, 3.0], {"grain": 20.0, "salt": 0.0, "precious": 60.0}),
    ([255, 255, 255], [100.0, 100.0, 100.0], {}),
])
def test_all_slots_share_finite_farmer_labor(types, yields, expected):
    produced = compute_allocated_production(types, yields, 60)
    assert produced == expected
    assert sum(produced.values()) <= 60 * max(yields)


def test_secondary_salt_and_precious_reach_real_stockpiles():
    world = experiment.make_world()
    target = world.regions[0]
    target.resource_types = [255, 4, 6]
    target.resource_current_yields = [0.0, 2.0, 3.0]
    # Twelve farmers split between two slots, with no phantom primary output.
    result = _oracle(world)
    assert result.region_goods[target.name].production["food"] == pytest.approx(12.0)
    assert result.region_goods[target.name].production["luxury"] == pytest.approx(18.0)
    assert target.stockpile.goods["salt"] == pytest.approx(2.0)  # 12 harvest - 10 meals
    assert target.stockpile.goods["precious"] == pytest.approx(18.0)
    assert target.stockpile.goods.get("grain", 0.0) == 0.0


def test_reserve_exhaustion_affects_harvest_without_preview_depletion():
    full = experiment.make_world()
    empty = experiment.make_world()
    for world, reserve in ((full, 1.0), (empty, 0.001)):
        target = world.regions[0]
        target.resource_types = [5, 255, 255]
        target.resource_base_yields = [2.0, 0.0, 0.0]
        target.resource_reserves = [reserve, 0.0, 0.0]
        refresh_resource_yields(world, ClimatePhase.TEMPERATE)
        assert target.resource_reserves[0] == reserve
    full_result = _oracle(full)
    empty_result = _oracle(empty)
    assert 0 < empty_result.region_goods[experiment.TARGET].production["raw_material"] < full_result.region_goods[experiment.TARGET].production["raw_material"]


def test_ffi_transmits_realized_all_slot_yields_not_potential():
    world = experiment.make_world()
    r = world.regions[0]
    r.resource_types = [0, 4, 6]
    r.resource_current_yields = [0.01, 0.2, 0.03]
    r.resource_effective_yields = [9.0, 8.0, 7.0]
    row = build_economy_region_input_batch(world).to_pylist()[0]
    for i in range(3):
        assert row[f"resource_type_{i}"] == r.resource_types[i]
        assert row[f"resource_yield_{i}"] == pytest.approx(r.resource_current_yields[i])
    assert "resource_effective_yield_0" not in row


def test_inventory_alone_changes_price_and_import_demand():
    poor = experiment.make_world()
    rich = experiment.make_world(reserve=20)
    for world in (poor, rich):
        refresh_resource_yields(world, ClimatePhase.DROUGHT)
    result_poor, result_rich = _oracle(poor), _oracle(rich)
    assert result_poor.region_goods[experiment.TARGET].production == result_rich.region_goods[experiment.TARGET].production
    assert result_poor.region_goods[experiment.TARGET].prices["food"] > result_rich.region_goods[experiment.TARGET].prices["food"]
    assert result_poor.food_sufficiency[experiment.TARGET] < 1 <= result_rich.food_sufficiency[experiment.TARGET]


def test_trade_delivers_actual_mixed_inventory_without_phantom_primary_goods():
    world = experiment.make_world()
    target, donor = world.regions
    # Source primary is ore, but its exportable FOOD is fish + salt inventory.
    # A primary-good-only decomposition would erase or fabricate this shipment.
    donor.resource_types = [5, 255, 255]
    donor.resource_current_yields = [0.0, 0.0, 0.0]
    donor.stockpile.goods = {"fish": 80.0, "salt": 20.0}
    target.resource_current_yields = [0.0, 0.0, 0.0]
    initial = experiment.stock_total(world)
    result = _oracle(world, routes=[("Valley Folk", "Coast Folk")])
    exported = result.region_goods[donor.name].exports["food"]
    delivered = result.region_goods[target.name].imports["food"]
    assert 0 < exported <= 40.0  # source has 100 stock - 60 food demand
    assert delivered == pytest.approx(exported * (0.8 * 0.92 + 0.2))
    assert result.conservation["transit_loss"] == pytest.approx(exported - delivered)
    assert result.inbound_sources[target.name] == [donor.name]
    assert target.stockpile.goods.get("ore", 0.0) == 0.0
    assert target.stockpile.goods.get("grain", 0.0) == 0.0
    assert target.stockpile.goods["salt"] > 0.0
    assert result.conservation["clamp_floor_loss"] == 0.0
    assert abs(experiment.conservation_error(initial, world, result)) < 1e-9


@pytest.mark.parametrize("seed", range(12))
def test_randomized_slot_and_stock_trade_conservation(seed):
    rng = random.Random(seed)
    world = experiment.make_world(seed=seed)
    for region in world.regions:
        region.resource_types = rng.sample(list(range(8)) + [255], 3)
        region.resource_current_yields = [rng.uniform(0.0, 3.0) for _ in range(3)]
        region.stockpile.goods = {g: rng.uniform(0.0, 80.0) for g in FIXED_GOODS}
    initial = experiment.stock_total(world)
    result = _oracle(world, routes=[("Valley Folk", "Coast Folk")])
    assert abs(experiment.conservation_error(initial, world, result)) < 1e-8
    assert result.conservation["clamp_floor_loss"] == 0.0
    assert all(math.isfinite(v) and v >= 0 for r in world.regions for v in r.stockpile.goods.values())
    exported = sum(sum(r.exports.values()) for r in result.region_goods.values())
    imported = sum(sum(r.imports.values()) for r in result.region_goods.values())
    assert exported - imported == pytest.approx(result.conservation["transit_loss"])


def test_route_and_surplus_absence_cannot_create_imports():
    for route_open in (False, True):
        world = experiment.make_world()
        for r in world.regions:
            r.resource_current_yields = [0.0, 0.0, 0.0]
            r.stockpile.goods = {}
        result = _oracle(world, routes=[("Valley Folk", "Coast Folk")] if route_open else [])
        assert all(sum(g.imports.values()) == 0 for g in result.region_goods.values())
        assert all(sum(g.exports.values()) == 0 for g in result.region_goods.values())
        assert result.conservation["production"] == 0.0
        assert result.conservation["transit_loss"] == 0.0
        assert result.inbound_sources == {}


@pytest.mark.parametrize("scenario", ["secondary_slots", "mixed_inventory", "mineral_exhaustion"])
def test_native_multislot_and_mixed_stock_trade_parity(scenario):
    _native_available()
    world = experiment.make_world()
    target, donor = world.regions
    if scenario == "secondary_slots":
        target.resource_types = [255, 4, 6]
        target.resource_base_yields = [0.0, 2.0, 3.0]
        donor.resource_types = [5, 3, 4]
        donor.resource_base_yields = [0.6, 4.0, 0.4]
    elif scenario == "mixed_inventory":
        target.resource_base_yields = [0.0, 0.0, 0.0]
        donor.resource_types = [5, 255, 255]
        donor.resource_base_yields = [0.0, 0.0, 0.0]
        donor.stockpile.goods = {"fish": 80.0, "salt": 20.0}
    else:
        target.resource_types = [5, 4, 6]
        target.resource_base_yields = [2.0, 0.8, 1.0]
        target.resource_reserves = [0.001, 1.0, 0.001]
    sim = experiment.new_native_simulator(world)
    report = experiment.run_phase(world, ClimatePhase.DROUGHT, True, backend="rust", sim=sim)
    assert max(report["python_parity"].values()) < 0.002
    if scenario == "secondary_slots":
        assert report["regions"][target.name]["stocks_after"]["precious"] > 0
    if scenario == "mixed_inventory":
        assert report["regions"][target.name]["delivered_imports"]["food"] > 0
        assert report["regions"][target.name]["stocks_after"]["grain"] == 0
        assert report["regions"][target.name]["stocks_after"]["ore"] == 0


def test_native_hybrid_cold_start_does_not_fall_back_to_abstract_imports():
    """First Phase 2 has no physical deliveries, even when routes are profitable.

    The FFI must pass an empty physical-delivery input to the core. Passing None
    incorrectly selects abstract trade and materializes goods before a trip.
    """
    _native_available()
    import pyarrow as pa
    from chronicler.economy import (
        build_economy_trade_route_batch, reconstruct_economy_result,
    )

    world = experiment.make_world()
    sim = experiment.new_native_simulator(world)
    sim.set_hybrid_economy_mode(True)
    refresh_resource_yields(world, ClimatePhase.DROUGHT)
    # Deliberately no route-graph setup or agent tick: exercise the initial FFI
    # state, where the internal merchant delivery buffer has not been allocated.
    batches = sim.tick_economy(
        build_economy_region_input_batch(world),
        build_economy_trade_route_batch(world, active_trade_routes=[("Valley Folk", "Coast Folk")]),
        0, False, 1.0,
    )
    result = reconstruct_economy_result(
        *(pa.record_batch(b) for b in batches), world, require_oracle_shadow=True,
    )
    assert all(sum(imports.values()) == 0.0 for imports in result.imports_by_region.values())
    assert result.conservation["in_transit_delta"] == 0.0
    assert result.oracle_imports[experiment.TARGET]["food"] > 0.0
    assert result.food_sufficiency[experiment.TARGET] < result.oracle_imports[experiment.TARGET]["food_sufficiency"]
    assert result.food_sufficiency[experiment.TARGET] < 1.0
    assert result.oracle_imports[experiment.TARGET]["food_sufficiency"] >= 1.0
