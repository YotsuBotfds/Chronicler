"""Mines and forests on their own curves (2026-10).

The farm curve (``economy.farm_labor_curve``) applies to the food labour only;
each non-food slot's labour saturates on its own capacity: a mine's deposit
(potential capacity x reserves left), a forest's woodland (potential capacity
x forest cover over the healthy cover). See
``docs/integration/bulk-trade-crafts.md``. Native tests run the real extension.
"""
from __future__ import annotations

import pytest

from chronicler.ecology import potential_capacity
from chronicler.economy import (
    MINE_RESERVE_FLOOR, RAW_REFERENCE_DENSITY, build_economy_region_input_batch,
    compute_allocated_production, effective_farm_labor, farm_labor, farm_labor_curve,
    farm_labor_for_effective, slot_curve_labor, slot_labor_curves,
)
from chronicler.models import ResourceType
from chronicler.tuning import K_FARM_REFERENCE_DENSITY, K_RAW_REFERENCE_DENSITY, KNOWN_OVERRIDES
from chronicler.world_gen import generate_world

GRAIN, TIMBER, ORE, BOTANICALS = (int(ResourceType.GRAIN), int(ResourceType.TIMBER),
                                  int(ResourceType.ORE), int(ResourceType.BOTANICALS))
SLOT_COLUMNS = [f"slot_labor_{kind}_{slot}" for kind in ("ref", "half") for slot in range(3)]


def _require_native():
    chronicler_agents = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(chronicler_agents, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")


def _region(world, types):
    region = world.regions[0]
    region.resource_types = list(types)
    return region


def test_raw_density_key_is_known():
    assert K_RAW_REFERENCE_DENSITY in KNOWN_OVERRIDES


def test_slot_curves_follow_woodland_and_deposits():
    world = generate_world(seed=42)
    region = _region(world, [TIMBER, ORE, GRAIN])
    region.ecology.forest_cover = 0.45
    region.resource_reserves = [1.0, 0.5, 1.0]
    land = potential_capacity(region)
    (t_ref, t_half), (o_ref, o_half), food = slot_labor_curves(world, region)
    assert t_ref == pytest.approx(RAW_REFERENCE_DENSITY * land * 0.45 / 0.9)
    assert o_ref == pytest.approx(RAW_REFERENCE_DENSITY * land * 0.5)
    assert (t_half, o_half) == pytest.approx((t_ref, o_ref)), "elasticity 0.5: L_h = L_ref"
    assert food == (0.0, 0.0), "food labour is on the farm curve"
    # An exhausted deposit keeps its floor of workings.
    region.resource_reserves = [1.0, 0.0, 1.0]
    assert slot_labor_curves(world, region)[1][0] == pytest.approx(RAW_REFERENCE_DENSITY * land * MINE_RESERVE_FLOOR)


def test_slot_curves_off_with_either_key_at_zero():
    world = generate_world(seed=42)
    region = _region(world, [GRAIN, ORE, 255])
    world.tuning_overrides[K_RAW_REFERENCE_DENSITY] = 0.0
    assert slot_labor_curves(world, region) is None
    world.tuning_overrides[K_RAW_REFERENCE_DENSITY] = RAW_REFERENCE_DENSITY
    world.tuning_overrides[K_FARM_REFERENCE_DENSITY] = 0.0
    assert slot_labor_curves(world, region) is None, "constant returns everywhere"


def test_economy_batch_carries_the_slot_columns_only_when_on():
    world = generate_world(seed=42)
    names = build_economy_region_input_batch(world).schema.names
    assert all(c in names for c in SLOT_COLUMNS)
    world.tuning_overrides[K_RAW_REFERENCE_DENSITY] = 0.0
    names = build_economy_region_input_batch(world).schema.names
    assert not any(c in names for c in SLOT_COLUMNS)
    assert "farm_labor_ref" in names


def test_slot_curve_labor_mines_do_not_crowd_the_fields():
    """Grain and ore, 40 farmers, small demand: the 20 field hands work the
    farmland at its reference and the 20 miners a deposit of reference 40
    (the Rust kernel's test case)."""
    types, yields = [GRAIN, ORE, 255], [1.0, 1.0, 0.0]
    labor, forage, _, productivity = slot_curve_labor(
        types, yields, 40, 5.0, 0.0, (20.0, 20.0), [(0.0, 0.0), (40.0, 40.0), (0.0, 0.0)])
    assert labor[0] == pytest.approx(20.0)
    assert labor[1] == pytest.approx(80.0 / 3.0)
    assert forage == 0.0
    assert productivity == pytest.approx((20.0 + 80.0 / 3.0) / 40.0)
    goods = compute_allocated_production(types, yields, 40, food_demand=5.0,
                                         slot_labor=(labor, forage, 0.0))
    assert goods == pytest.approx({"grain": 20.0, "ore": 80.0 / 3.0})
    # One curve for all farm labour (before): 26.7 effective, half each.
    one = effective_farm_labor(40, 20.0, 20.0)
    assert compute_allocated_production(types, yields, one) == pytest.approx({"grain": one / 2, "ore": one / 2})


def test_food_first_reads_the_food_need_through_the_farm_curve():
    types, yields = [GRAIN, ORE, 255], [1.0, 1.0, 0.0]
    flat, _, _ = farm_labor(types, yields, 40, 25.0)
    curved, _, _ = farm_labor(types, yields, 40, 25.0, food_curve=(20.0, 20.0))
    assert flat[0] == pytest.approx(25.0)
    assert curved[0] == pytest.approx(100.0 / 3.0)
    assert effective_farm_labor(curved[0], 20.0, 20.0) == pytest.approx(25.0)
    assert farm_labor_for_effective(40.0, 20.0, 20.0) == float("inf")
    assert farm_labor_for_effective(7.5, 0.0, 0.0) == 7.5


@pytest.mark.native
def test_native_kernel_reads_the_slot_curves_and_rejects_a_partial_set(make_world):
    """The same pool and inputs: the slot columns raise a crowded mine's ore
    (its miners no longer share the farmland's curve); a partial set is an
    error."""
    _require_native()
    import pyarrow as pa

    from chronicler.agent_bridge import AgentBridge
    from chronicler.columnar import pylist

    def ore_after(drop: list[str]):
        world = make_world(num_civs=2)
        world.agent_mode = "hybrid"
        for region in world.regions:
            region.population = 50
            region.resource_types = [GRAIN, ORE, 255]
            region.resource_reserves = [1.0, 1.0, 1.0]
            region.resource_current_yields = [0.5, 1.0, 0.0]
        bridge = AgentBridge(world, mode="hybrid")
        batch = build_economy_region_input_batch(world)
        keep = [n for n in batch.schema.names if n not in drop]
        batch = pa.record_batch({n: batch.column(n) for n in keep})
        routes = pa.record_batch({
            "origin_region_id": pa.array([], type=pa.uint16()),
            "dest_region_id": pa.array([], type=pa.uint16()),
            "is_river": pa.array([], type=pa.bool_()),
        })
        out = bridge._sim.tick_economy(batch, routes, 0, False, 1.0)
        return sum(pylist(out[0].column("stockpile_ore")))

    with_curves = ore_after([])
    one_curve = ore_after(SLOT_COLUMNS)
    assert with_curves > one_curve
    with pytest.raises(ValueError):
        ore_after(SLOT_COLUMNS[:3])
